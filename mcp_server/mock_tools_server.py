from mcp.server.fastmcp import FastMCP

mcp = FastMCP("python-mcp-flow-demo")

@mcp.tool()
def greet(name: str) -> str:
    """Greet a user (proof tool)."""
    return f"Hello {name}! This result came from an MCP tool."

@mcp.tool()
def get_defect_details(defectId: str) -> dict:
    """Mock defect details (placeholder for future ADO integration)."""
    return {
        "defectId": defectId,
        "title": "Demo defect title",
        "category": "Functional",
        "priority": "High",
        "severity": "S2",
        "status": "Open",
        "assignedTo": "Demo Owner",
        "createdDate": "2026-03-12"
    }

# For stdio servers spawned by a client, this should run in foreground.
mcp.run()