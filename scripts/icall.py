"""Call any mc-iclone8-mcp tool from the shell (for probing, scripts and live verification). Stdlib only.

  python icall.py <tool> ['{"json": "args"}']
  python icall.py exec < snippet.py        # python_exec with code from stdin; prints _result
"""
import json
import sys
import urllib.request

import os
URL = os.environ.get("MC_ICLONE8_MCP_URL", "http://127.0.0.1:8766/mcp")
TOKEN = os.environ.get("MC_ICLONE8_MCP_TOKEN")


def call(tool, args, timeout=600):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}).encode()
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    r = json.load(urllib.request.urlopen(urllib.request.Request(URL, body, headers), timeout=timeout))
    if "error" in r:
        return {"rpc_error": r["error"]}
    blocks = r["result"]["content"]
    text = next((b["text"] for b in blocks if b.get("type") == "text"), "")
    try:
        out = json.loads(text)
    except ValueError:
        out = text
    if r["result"].get("isError"):
        return {"isError": True, "content": out}
    return out


if __name__ == "__main__":
    tool = sys.argv[1]
    if tool == "exec":
        res = call("python_exec", {"code": sys.stdin.read()})
    else:
        res = call(tool, json.loads(sys.argv[2]) if len(sys.argv) > 2 else {})
    sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
    print(json.dumps(res, indent=1, ensure_ascii=False)[:20000])
