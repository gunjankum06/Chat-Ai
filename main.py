import argparse
import asyncio
import sys
from dotenv import load_dotenv

from agent.orchestrator import AgentOrchestrator

def parse_args():
    p = argparse.ArgumentParser(description="CLI → LLM → MCP → LLM → CLI agent")
    p.add_argument(
        "--server",
        nargs="+",
        required=True,
        help="MCP server command to spawn via stdio. Example: --server python mcp_server/mock_tools_server.py",
    )
    return p.parse_args()

async def main():
    load_dotenv()
    args = parse_args()

    orchestrator = AgentOrchestrator(server_command=args.server)
    await orchestrator.run_cli()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!", file=sys.stderr)