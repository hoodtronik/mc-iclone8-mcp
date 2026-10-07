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
- New iClone projects default to 60 fps — call `set_project_fps` 24 for film previz (Qt-tier tool; RLPy has no setter).


## Capability-expansion strategy

When the requested iClone operation is not already supported, **do not immediately guess a new RLPy call and do not broadly reverse engineer iClone**.

Read, in this order:

0. `docs/hoodtronik/ICLONE_DOCS_CORPUS.md` — how iClone itself does it: query the NotebookLM docs notebook or grep the
   local manual/wiki scrape BEFORE probing RLPy (the UI often has the feature, e.g. Convert External Motion presets).
1. `docs/hoodtronik/ICLONE_AUTOMATION_ARCHAEOLOGY_STRATEGY.md`
2. `docs/hoodtronik/ICLONE_CAPABILITY_GAP_MATRIX.md`
3. `docs/hoodtronik/ICLONE8_AGENT_REFERENCE.md`
4. `docs/hoodtronik/automation-entry-points.md`
5. `docs/hoodtronik/HANDOFF_iCloneMCP_research.md`

Use the escalation ladder:

`OFFICIAL RLPy -> OBSERVED/local-stub -> Qt/UI surface -> targeted native bridge -> unsafe experimental`.

Before deep native archaeology, complete or update the capability-gap audit by comparing the installed `RLPy.py`, official docs/samples, and the current MCP registry. Work **one creator-visible capability at a time**.

For capabilities the creator can perform manually in iClone but RLPy does not expose, observe the manual operation, identify the smallest owning subsystem, and attempt the least invasive safe automation route first.

Any native/internal capability must be version-aware, fail closed on unknown iClone builds, checkpoint before destructive work, and include runtime evidence. Do not expose arbitrary raw memory writes or arbitrary native function-call endpoints as normal MCP tools.

Hard rule: **code that looks correct is not runtime proof**. Verify actual scene/timeline/render effects.

Do not assume iClone is Unity-based. Treat its internal architecture as unknown until proven by installed-runtime evidence.
