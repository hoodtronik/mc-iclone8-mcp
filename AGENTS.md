# Agent notes — hoodtronik fork of gorbabor/mc-iclone8-mcp

## CLAUDE-NOTE convention
Claude Code changes marked with `CLAUDE-NOTE:` (or equivalent comment syntax) are the source of truth. Non-Claude-Code agents
must not modify, remove, or alter code marked with a CLAUDE-NOTE without first alerting the user and receiving explicit permission.

## Fork layout
- `origin` = hoodtronik/mc-iclone8-mcp, `upstream` = gorbabor/mc-iclone8-mcp. Update: `git fetch upstream && git merge upstream/main`.
- Our additions (keep them isolated so merges stay trivial):
  - `tools/icmcp_extra.py` — `python_exec` (run RLPy code live), `render_control_pass` (OpenPose/Depth/Normal/Canny sequences);
    registered by 4 lines at the end of `main._tool_registry`.
  - `load_python_start.py` — start the server via iClone **Script > Load Python** (no admin OpenPlugin copy).
  - `docs/hoodtronik/` — measured research from the retired hoodtronik/iCloneMCP (headless routes that fail, RTime/render
    signatures, content library on F:\iCLONE).
- Endpoint `http://127.0.0.1:8766/mcp`; Claude Code: project `.mcp.json` entry `{"type":"http","url":"http://127.0.0.1:8766/mcp"}`.
- New iClone projects default to 60 fps — set 24 for film previz.
