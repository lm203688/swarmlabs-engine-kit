"""Reference MCP server for SwarmLabs Engine.

Exposes engine calls as standard MCP tools so any MCP-aware agent runtime can
use SwarmLabs as a trusted scientific-compute tool. This is a reference
implementation; wire it into your MCP framework of choice (the tool
definitions below follow the MCP schema).

Run:
    python -m mcp.server --base-url https://your-swarmlabs-engine.example.com
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict

from swarmlabs_engine import SwarmLabsClient, SwarmLabsError


def build_tools(client: SwarmLabsClient) -> list:
    """Return MCP tool definitions backed by the SwarmLabs client."""

    def run_tool(args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return client.run(args["engine"], args.get("params", {}))
        except SwarmLabsError as e:
            return {"error": str(e), "status": e.status}

    def list_tool(args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return client.list_engines()
        except SwarmLabsError as e:
            return {"error": str(e), "status": e.status}

    def sweep_tool(args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return client.sweep(args["engine"], args.get("params", {}), int(args.get("n", 20)))
        except SwarmLabsError as e:
            return {"error": str(e), "status": e.status}

    tools = [
        {
            "name": "swarmlabs_run",
            "description": "Run a real physics-informed prediction for a SwarmLabs engine.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "engine": {"type": "string", "description": "Engine id, e.g. vqe_h2"},
                    "params": {"type": "object", "description": "Physics parameters"},
                },
                "required": ["engine"],
            },
            "handler": run_tool,
        },
        {
            "name": "swarmlabs_list",
            "description": "List available engines and physics-model coverage.",
            "input_schema": {"type": "object", "properties": {}},
            "handler": list_tool,
        },
        {
            "name": "swarmlabs_sweep",
            "description": "Parameter sweep for trend analysis (free tier).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "engine": {"type": "string"},
                    "params": {"type": "object"},
                    "n": {"type": "integer", "default": 20},
                },
                "required": ["engine"],
            },
            "handler": sweep_tool,
        },
    ]
    return tools


def main() -> None:
    parser = argparse.ArgumentParser(description="SwarmLabs Engine MCP server (reference)")
    parser.add_argument("--base-url", required=True, help="Your SwarmLabs engine endpoint")
    parser.add_argument("--api-key", default=None, help="Optional bearer token")
    args = parser.parse_args()

    client = SwarmLabsClient(base_url=args.base_url, api_key=args.api_key)
    tools = build_tools(client)

    # Print the tool manifest (replace this with your MCP transport binding).
    manifest = [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["input_schema"],
        }
        for t in tools
    ]
    print(json.dumps({"mcp_server": "swarmlabs-engine", "tools": manifest}, indent=2))


if __name__ == "__main__":
    main()
