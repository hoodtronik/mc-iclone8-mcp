r"""iCloneMCP_Autostart — tiny OpenPlugin that iClone runs at startup (installed once into
<iClone 8>\Bin64\OpenPlugin\iCloneMCP_Autostart\main.py). It only bootstraps code that lives in the fork on G:, so updates
never need admin again.
# CLAUDE-NOTE (2026-09-26, hoodtronik fork): Ilyas wants iClone usable while he's away — iClone must come up with the MCP
# running and no human clicks. Keep this file minimal; all logic lives in load_python_start.py / tools/dialog_watch.py.
"""
import os, sys, traceback

rl_plugin_info = {"ap": "iClone", "ap_version": "8.0"}
FORK = os.environ.get("MC_ICLONE8_MCP_DIR", r"G:\_AI_Agents\mc-iclone8-mcp")


def initialize_plugin():
    try:
        if FORK not in sys.path:
            sys.path.insert(0, FORK)
        import importlib.util
        spec = importlib.util.spec_from_file_location("icmcp_load_python_start", os.path.join(FORK, "load_python_start.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)          # starts the MCP server (idempotent)
        from tools import dialog_watch
        dialog_watch.start()
    except Exception:
        with open(os.path.join(os.path.expanduser("~"), "Desktop", "icmcp_loader_log.txt"), "a", encoding="utf-8") as f:
            f.write("AUTOSTART FAILED:\n" + traceback.format_exc() + "\n")
