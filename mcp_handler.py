import json


class MCPHandler:
    def __init__(self, tools):
        self.tools = tools

    def __call__(self, body):
        try:
            request = json.loads(body)
            method = request.get("method")
            if method == "initialize":
                result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "mc-iclone8-mcp", "version": "0.1.0"}}
            elif method == "tools/list":
                result = {"tools": [{"name": name, "description": meta["description"], "inputSchema": meta["inputSchema"]} for name, meta in self.tools.items()]}
            elif method == "tools/call":
                params = request.get("params", {})
                name = params.get("name")
                if name not in self.tools:
                    raise ValueError("Unknown tool: %s" % name)
                tool = self.tools[name]
                arguments = params.get("arguments", {})
                if tool.get("main_thread"):
                    from dispatch import run
                    response = run(lambda: tool["handler"](arguments))
                else:
                    response = tool["handler"](arguments)
                # CLAUDE-NOTE (2026-09-26, hoodtronik fork): a tool may return "_image_png_b64" -> emitted as an MCP image block
                # (viewport_capture "eyes"), so the agent SEES the picture instead of getting a path.
                image = response.pop("_image_png_b64", None) if isinstance(response, dict) else None
                result = {"content": [{"type": "text", "text": json.dumps(response, ensure_ascii=False)}]}
                if image:
                    result["content"].append({"type": "image", "data": image, "mimeType": "image/png"})
            elif method == "ping":
                result = {}
            else:
                raise ValueError("Unsupported method: %s" % method)
            return json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": result}, ensure_ascii=False)
        except Exception as error:
            return json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(error)}}, ensure_ascii=False)
