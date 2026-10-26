"""Small JSON-lines MCP server used only by the local protocol test."""
import json
import sys


for raw in sys.stdin:
    request = json.loads(raw)
    method = request.get("method")
    if "id" not in request:
        continue
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "stub", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "echo", "description": "Echoes text", "inputSchema": {"type": "object"}}]}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": str((request.get("params") or {}).get("arguments", {}).get("text", ""))}]}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
