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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--project")
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args()
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
        if healthy():
            print(f"MCP healthy after {time.time() - t0:.0f}s"); print(json.dumps(dialogs())); sys.exit(0)
        time.sleep(5)
    print("TIMEOUT: MCP not healthy"); sys.exit(1)
