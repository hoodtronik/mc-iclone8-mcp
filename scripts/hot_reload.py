"""Hot-reload the fork's tool code inside a running iClone (no iClone restart, scene untouched).

  python scripts/hot_reload.py            # reload + restart the MCP server, then wait for /health and list the tool count

How: python_exec schedules (QTimer, 300 ms) a stop -> reload(common, dialog_watch, exr_zip, mcp_handler, main) -> start on
iClone's main thread, AFTER the current request has answered (stopping the server inside the request would kill the reply).
"""
# CLAUDE-NOTE (2026-09-26): the manual recipe lived only in memory; this makes it one command so every fork edit gets
# exercised live the same minute it is written.
import json, sys, time, urllib.request

URL = "http://127.0.0.1:8766"

SNIPPET = r'''
import sys, importlib, importlib.util
from PySide2 import QtCore
def _icmcp_reload():
    m = sys.modules["mc_iclone8_main"]
    m.stop_server()
    for name in ("tools.common", "tools.dialog_watch", "tools.exr_zip", "tools.native_ui", "mcp_handler"):
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    # CLAUDE-NOTE (2026-10-16): main.py owns _tool_registry, so a new tool module registered there never appeared until
    # main itself was reloaded too (server already stopped above, so dropping its old _server global is safe). main is
    # loaded by file path under a custom name, so importlib.reload cannot re-find it (that killed the server): re-exec.
    spec = importlib.util.spec_from_file_location("mc_iclone8_main", m.__file__)
    m = importlib.util.module_from_spec(spec)
    sys.modules["mc_iclone8_main"] = m
    spec.loader.exec_module(m)
    m.start_server()
QtCore.QTimer.singleShot(300, _icmcp_reload)
_result = "scheduled"
'''


def post(payload, timeout=60):
    req = urllib.request.Request(URL + "/mcp", json.dumps(payload).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def precheck():
    """Parse every module the server loads, as Python 3.8 (iClone's interpreter), before touching the live server.
    # CLAUDE-NOTE (2026-10-17): a raw newline inside a string in tools/acting.py killed the server on reload (it stops,
    # then cannot re-import); recovery needed an iClone restart. Refuse to reload broken code instead."""
    import ast
    import glob
    import os
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bad = []
    for path in [os.path.join(repo, f) for f in ("main.py", "mcp_handler.py", "dispatch.py", "load_python_start.py")] + \
            sorted(glob.glob(os.path.join(repo, "tools", "*.py"))):
        if not os.path.isfile(path):
            continue
        try:
            ast.parse(open(path, encoding="utf-8").read(), filename=path, feature_version=(3, 8))
        except SyntaxError as e:
            bad.append(f"{os.path.relpath(path, repo)}:{e.lineno}: {e.msg}")
    if bad:
        sys.exit("NOT reloading - fix these first (the server would die):\n  " + "\n  ".join(bad))


def main():
    precheck()
    r = post({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "python_exec", "arguments": {"code": SNIPPET}}})
    if "error" in r:
        sys.exit("reload not scheduled: %s" % r["error"])
    time.sleep(1.5)
    for _ in range(40):
        try:
            if json.load(urllib.request.urlopen(URL + "/health", timeout=2)).get("status") == "ok":
                n = len(post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"])
                print("reloaded; %d tools live" % n)
                return
        except Exception:
            pass
        time.sleep(0.5)
    sys.exit("server did not come back on %s — check iClone" % URL)


if __name__ == "__main__":
    main()
