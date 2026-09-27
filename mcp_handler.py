import json


class _ToolError(Exception):
    pass


class MCPHandler:
    def __init__(self, tools):
        self.tools = tools

    def __call__(self, body):
        request = {}
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
                arguments = params.get("arguments", {}) or {}
                # CLAUDE-NOTE (2026-09-26, hoodtronik fork): reject argument names the schema doesn't declare. Without this,
                # get_animation_clips({"name": "Eli"}) silently ignored "name" and answered for the FIRST avatar (Scarab) —
                # a wrong-object read that looks like success. Tools whose schema sets additionalProperties=true opt out.
                schema = tool.get("inputSchema") or {}
                declared = schema.get("properties")
                if declared is not None and not schema.get("additionalProperties", False):
                    unknown = sorted(set(arguments) - set(declared) - ({"checkpoint"} if tool.get("checkpoint") else set()))
                    if unknown:
                        raise _ToolError("%s: unknown argument(s) %s; accepted: %s" % (name, unknown, sorted(declared)))
                missing = [k for k in schema.get("required", []) if k not in arguments]
                if missing:
                    raise _ToolError("%s: missing required argument(s) %s" % (name, missing))
                # CLAUDE-NOTE (2026-09-26, hoodtronik fork): per MCP spec a failing TOOL is a normal result with isError=true.
                # Upstream raised it as a JSON-RPC error with id=null, which Claude Code rejects as a malformed response —
                # the real message (e.g. "unknown argument") never reached the agent.
                # CLAUDE-NOTE (2026-09-26): tools flagged "checkpoint" (crash-prone: first-use APIs, renders, reach IK) save
                # the CURRENT project in place first — AddReachKey's first live call killed iClone and took ~20 min of
                # unsaved blocking with it. Pass {"checkpoint": false} in arguments to skip (e.g. tight loops).
                if tool.get("checkpoint") and arguments.pop("checkpoint", True):
                    from dispatch import run as _run
                    from tools.project import save_project as _save
                    _run(lambda: _save({}))
                else:
                    arguments.pop("checkpoint", None)
                try:
                    if tool.get("main_thread"):
                        from dispatch import run
                        response = run(lambda: tool["handler"](arguments))
                    else:
                        response = tool["handler"](arguments)
                except Exception as tool_error:
                    raise _ToolError("%s: %s" % (type(tool_error).__name__, tool_error))
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
        except _ToolError as error:
            result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
            return json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": result}, ensure_ascii=False)
        except Exception as error:
            rid = request.get("id") if isinstance(request, dict) else None
            return json.dumps({"jsonrpc": "2.0", "id": rid if rid is not None else 0, "error": {"code": -32603, "message": str(error)}}, ensure_ascii=False)
