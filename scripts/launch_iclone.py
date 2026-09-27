r"""Unattended iClone start: launch iClone 8 (optionally with a project), wait for the auto-started MCP, report popups.
  python scripts/launch_iclone.py [--project X.iProject] [--timeout 300]
Needs the autostart plugin installed once (autostart/main.py -> <iClone 8>\Bin64\OpenPlugin\iCloneMCP_Autostart\main.py).
Exit 0 = MCP healthy; 1 = timed out (read ~/Desktop/icmcp_loader_log.txt and icmcp_dialogs.log).
"""
import argparse, json, os, subprocess, sys, time, urllib.request

EXE = os.environ.get("ICLONE_EXE", r"C:\Program Files\Reallusion\iClone 8\Bin64\iClone.exe")
URL = "http://127.0.0.1:8766"


def healthy():
    try:
        return json.load(urllib.request.urlopen(URL + "/health", timeout=3)).get("status") == "ok"
    except Exception:
        return False


def running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq iClone.exe"], capture_output=True, text=True).stdout
    return "iClone.exe" in out


def dialogs():
    try:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_dialogs", "arguments": {}}}).encode()
        r = json.load(urllib.request.urlopen(urllib.request.Request(URL + "/mcp", body, {"Content-Type": "application/json"}), timeout=20))
        return json.loads(r["result"]["content"][0]["text"])
    except Exception as e:
        return {"error": repr(e)}


def project_loaded():
    # CLAUDE-NOTE (2026-09-26): the MCP comes up ~30 s before a big .iProject finishes loading, and a modal (e.g. "Unsaved
    # project data found") can hold the load forever. "Healthy" for a --project launch = scene has objects.
    try:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "python_exec", "arguments": {
            "code": "import RLPy; _result = len(RLPy.RScene.GetAvatars()) + len(RLPy.RScene.GetProps())"}}}).encode()
        req = urllib.request.Request("http://127.0.0.1:8766/mcp", body, {"Content-Type": "application/json"})
        txt = json.load(urllib.request.urlopen(req, timeout=10))["result"]["content"][0]["text"]
        return json.loads(txt).get("result", 0) > 0
    except Exception:
        return False


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--project")
    ap.add_argument("--timeout", type=int, default=300)
    # CLAUDE-NOTE (2026-09-26): --restart = iClone is up but the MCP server is dead (e.g. a bad hot-reload) -> force-close
    # and relaunch the project. Only safe after a save; the caller must have saved.
    ap.add_argument("--restart", action="store_true", help="kill a running-but-unhealthy iClone and relaunch --project")
    a = ap.parse_args()
    if a.restart and running() and not healthy():
        subprocess.run(["taskkill", "/IM", "iClone.exe", "/F"], capture_output=True)
        for _ in range(30):
            if not running():
                break
            time.sleep(1)
        print("killed unhealthy iClone")
    if healthy():
        print("MCP already healthy"); print(json.dumps(dialogs())); sys.exit(0)
    if not running():
        cmd = [EXE] + ([a.project] if a.project else [])
        subprocess.Popen(cmd, cwd=os.path.dirname(EXE), creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        print("launched", cmd)
    else:
        print("iClone running but MCP not healthy yet — waiting (is the autostart plugin installed?)")
    t0 = time.time()
    while time.time() - t0 < a.timeout:
        if healthy() and (not a.project or project_loaded()):
            print(f"MCP healthy{' + project loaded' if a.project else ''} after {time.time() - t0:.0f}s"); print(json.dumps(dialogs())); sys.exit(0)
        if healthy() and a.project and int(time.time() - t0) % 30 < 5:
            d = dialogs()
            if d.get("dialogs"):
                print("waiting on project load; modal dialog(s) open — answer with dismiss_dialog:", json.dumps(d))
        time.sleep(5)
    print("TIMEOUT: MCP not healthy"); sys.exit(1)
