"""
Azure DevOps MCP tool server.

Exposes ADO work-item tools over stdio so the orchestrator can call them
as MCP tools.  Spawned as a subprocess by the CLI agent:

    python main.py --server python mcp_server/ado_tools_server.py

Required environment variables (set in .env):
    ADO_ORG       — Azure DevOps organisation slug, e.g. "myorg"
    ADO_PROJECT   — Project name, e.g. "MyProject"
    ADO_PAT       — Personal Access Token with Work Items (read) scope

Do NOT print to stdout — it is used for MCP stdio transport.
Log to stderr only.
"""

import base64
import logging
import os
import re
import sys

import requests
from mcp.server.fastmcp import FastMCP

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP("ado-tools")

# ---------------------------------------------------------------------------
# ADO helpers
# ---------------------------------------------------------------------------

def _base_url() -> str:
    org     = os.environ["ADO_ORG"]
    project = os.environ["ADO_PROJECT"]
    return f"https://dev.azure.com/{org}/{project}/_apis"


def _headers() -> dict:
    pat    = os.environ["ADO_PAT"]
    token  = base64.b64encode(f":{pat}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type":  "application/json",
    }


def _validate_wiql(wiql: str) -> str:
    """
    Basic server-side WIQL policy checks to reduce data-overreach and abuse.
    """
    query = (wiql or "").strip()
    max_len = int(os.getenv("ADO_MAX_WIQL_LENGTH", "1000"))
    if not query:
        raise ValueError("WIQL query cannot be empty.")
    if len(query) > max_len:
        raise ValueError(f"WIQL query exceeds max length of {max_len} characters.")

    lowered = query.lower()
    if "from workitems" not in lowered or "select" not in lowered:
        raise ValueError("Only SELECT ... FROM WorkItems queries are allowed.")

    # Disallow obvious unsafe/broadening patterns.
    forbidden = [";", "drop ", "delete ", "update ", "insert ", "exec ", "union "]
    if any(token in lowered for token in forbidden):
        raise ValueError("WIQL query contains forbidden tokens.")

    # Keep queries project-scoped.
    if "@project" not in lowered and "system.teamproject" not in lowered:
        raise ValueError("WIQL must be scoped to project (use @project or System.TeamProject).")

    return query


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_work_item(id: int) -> dict:
    """
    Fetch a single work item (bug / task / user story) by its numeric ID
    from Azure DevOps and return the most useful fields.
    """
    fields = [
        "System.Id",
        "System.WorkItemType",
        "System.Title",
        "System.State",
        "System.AssignedTo",
        "Microsoft.VSTS.Common.Priority",
        "Microsoft.VSTS.Common.Severity",
        "System.AreaPath",
        "System.IterationPath",
        "System.CreatedDate",
        "System.ChangedDate",
        "System.Tags",
    ]
    if (os.getenv("ADO_INCLUDE_DESCRIPTION") or "false").strip().lower() == "true":
        fields.append("System.Description")

    url  = f"{_base_url()}/wit/workitems/{id}?api-version=7.1&fields={','.join(fields)}"
    resp = requests.get(url, headers=_headers(), timeout=15)
    resp.raise_for_status()

    fields = resp.json().get("fields", {})
    assigned = fields.get("System.AssignedTo") or {}

    return {
        "id":            id,
        "type":          fields.get("System.WorkItemType"),
        "title":         fields.get("System.Title"),
        "state":         fields.get("System.State"),
        "assignedTo":    assigned.get("displayName") if isinstance(assigned, dict) else assigned,
        "priority":      fields.get("Microsoft.VSTS.Common.Priority"),
        "severity":      fields.get("Microsoft.VSTS.Common.Severity"),
        "areaPath":      fields.get("System.AreaPath"),
        "iterationPath": fields.get("System.IterationPath"),
        "createdDate":   fields.get("System.CreatedDate"),
        "changedDate":   fields.get("System.ChangedDate"),
        "description":   fields.get("System.Description"),
        "tags":          fields.get("System.Tags"),
    }


@mcp.tool()
def list_work_items(wiql: str) -> list:
    """
    Execute a WIQL (Work Item Query Language) query against Azure DevOps and
    return a list of matching work items with id, title, state, and type.

    Example WIQL:
        SELECT [System.Id],[System.Title],[System.State]
        FROM WorkItems
        WHERE [System.TeamProject] = @project
          AND [System.State] = 'Active'
        ORDER BY [System.ChangedDate] DESC
    """
    safe_wiql = _validate_wiql(wiql)

    query_url = f"{_base_url()}/wit/wiql?api-version=7.1"
    resp = requests.post(query_url, headers=_headers(),
                         json={"query": safe_wiql}, timeout=15)
    resp.raise_for_status()

    items = resp.json().get("workItems", [])
    if not items:
        return []

    # Batch-fetch titles/states for the returned IDs (max 200 per API call)
    max_results = min(int(os.getenv("ADO_MAX_RESULTS", "100")), 200)
    ids = [str(i["id"]) for i in items[:max_results]]
    batch_url = (
        f"https://dev.azure.com/{os.environ['ADO_ORG']}"
        f"/_apis/wit/workitems?ids={','.join(ids)}"
        f"&fields=System.Id,System.Title,System.State,System.WorkItemType"
        f"&api-version=7.1"
    )
    detail_resp = requests.get(batch_url, headers=_headers(), timeout=15)
    detail_resp.raise_for_status()

    results = []
    for item in detail_resp.json().get("value", []):
        f = item.get("fields", {})
        results.append({
            "id":    item["id"],
            "type":  f.get("System.WorkItemType"),
            "title": f.get("System.Title"),
            "state": f.get("System.State"),
        })
    return results


@mcp.tool()
def get_work_item_comments(id: int) -> list:
    """
    Retrieve the discussion comments for a work item by its numeric ID.
    Returns a list of comments with author, date, and text.
    """
    url  = f"{_base_url()}/wit/workitems/{id}/comments?api-version=7.1-preview.4"
    resp = requests.get(url, headers=_headers(), timeout=15)
    resp.raise_for_status()

    max_comments = int(os.getenv("ADO_MAX_COMMENTS", "50"))
    max_comment_len = int(os.getenv("ADO_MAX_COMMENT_LENGTH", "2000"))

    comments = []
    for c in resp.json().get("comments", [])[:max_comments]:
        author = c.get("createdBy") or {}
        text = c.get("text")
        if isinstance(text, str) and len(text) > max_comment_len:
            text = text[:max_comment_len] + "\n[comment truncated]"
        comments.append({
            "author": author.get("displayName") if isinstance(author, dict) else author,
            "date":   c.get("createdDate"),
            "text":   text,
        })
    return comments


# ---------------------------------------------------------------------------
# Entry point — must run in stdio foreground for MCP subprocess transport
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info(
        "ADO MCP server starting — org=%s project=%s",
        os.environ.get("ADO_ORG", "(not set)"),
        os.environ.get("ADO_PROJECT", "(not set)"),
    )
    mcp.run()
