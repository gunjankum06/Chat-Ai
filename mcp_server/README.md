# Mock MCP Tool Server

This MCP server exposes two tools:
- greet(name: str) -> str
- get_defect_details(defectId: str) -> dict

It is designed for stdio transport and should be spawned by the CLI agent.

Important:
- Do NOT print to stdout.
- If you must log, use stderr.