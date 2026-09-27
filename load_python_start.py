"""Start this MCP server from iClone WITHOUT the admin OpenPlugin install:
iClone 8: Script > Load Python > this file.  Endpoint http://127.0.0.1:8766/mcp (health: /health).
Log: ~/Desktop/icmcp_loader_log.txt
# CLAUDE-NOTE (2026-09-26, hoodtronik fork): measured on iClone 8.74 — Load Python executes the file under a module name
# (not __main__) and never calls run_script(), and it prompts "not compatible" unless rl_plugin_info is declared. So this
# runs on import and declares it. main.py is loaded under a unique name because other OpenPlugins also ship a `main`.
"""
import datetime, importlib.util, os, sys, traceback

rl_plugin_info = {"ap": "iClone", "ap_version": "8.0"}
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(os.path.expanduser("~"), "Desktop", "icmcp_loader_log.txt")


def _log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def run_script():
    old = sys.modules.get("mc_iclone8_main")
    if old is not None and getattr(getattr(old, "_server", None), "running", False):
        _log("already running — skipped")
        return
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        spec = importlib.util.spec_from_file_location("mc_iclone8_main", os.path.join(HERE, "main.py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules["mc_iclone8_main"] = m
        spec.loader.exec_module(m)
        _log("started " + m.start_server())
    except Exception:
        _log("FAILED:\n" + traceback.format_exc())
        raise


run_script()
