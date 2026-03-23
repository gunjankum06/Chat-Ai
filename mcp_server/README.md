# MCP Tool Servers

## mock_tools_server.py

Deterministic stub for local development — no API keys required.

Exposes:
- `greet(name: str) -> str`
- `get_defect_details(defectId: str) -> dict`

Run with:
```
python main.py --server python mcp_server/mock_tools_server.py
```

---

## ado_tools_server.py

Real Azure DevOps integration. Calls the ADO REST API using a Personal Access Token.

Exposes:
- `get_work_item(id: int) -> dict` — fetch a single work item by ID
- `list_work_items(wiql: str) -> list` — run a WIQL query and return matching items
- `get_work_item_comments(id: int) -> list` — fetch discussion comments for a work item

Required `.env` variables:
```
ADO_ORG=your-ado-org
ADO_PROJECT=your-project
ADO_PAT=your-personal-access-token
LLM_PROVIDER=azure_openai
```

Run with:
```
python main.py --server python mcp_server/ado_tools_server.py
```

Important:
- Do NOT print to stdout — it is used for MCP stdio transport.
- Log to stderr only.