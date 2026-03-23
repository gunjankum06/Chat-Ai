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
import json
import logging
import os
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


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_work_item(id: int) -> dict:
    """
    Fetch a single work item (bug / task / user story) by its numeric ID
    from Azure DevOps and return the most useful fields.
    """
    url  = f"{_base_url()}/wit/workitems/{id}?api-version=7.1&$expand=all"
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
    query_url = f"{_base_url()}/wit/wiql?api-version=7.1"
    resp = requests.post(query_url, headers=_headers(),
                         json={"query": wiql}, timeout=15)
    resp.raise_for_status()

    items = resp.json().get("workItems", [])
    if not items:
        return []

    # Batch-fetch titles/states for the returned IDs (max 200 per API call)
    ids = [str(i["id"]) for i in items[:200]]
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

    comments = []
    for c in resp.json().get("comments", []):
        author = c.get("createdBy") or {}
        comments.append({
            "author": author.get("displayName") if isinstance(author, dict) else author,
            "date":   c.get("createdDate"),
            "text":   c.get("text"),
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
