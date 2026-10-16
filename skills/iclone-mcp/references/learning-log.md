# Learning log

Newest first. Each entry: what happened, the rule it produced, evidence. Promote durable rules into SKILL.md /
gotchas.md / recipes.md; keep this file as the history.

## 2026-10-16 - park-bench scene (first full scene built purely through MCP)
- `new_project(save_current=false)` blocked on the discard prompt -> fresh scene via silent `LoadFile(default project)`.
  Answered the live prompt out-of-process (Tab to "No", Space) after reading it from a capture.
- Second avatar load replaced the selected first one -> clear selection before every avatar load.
- Late walkers stood inside the bench until their start -> fixed in `walk_to` (wait at `from`), mc-iclone8-mcp d0124a2.
- Walks past the project end silently produced 12-clip garbage (playhead clamps) -> `walk_to` now refuses.
- Hot reload forgot the project path -> `current_project_path` asks `RApplication.GetCurrentProjectPath()`.
- `set_material_color` keys at the current frame (path faded white -> grey mid-shot) -> colour at frame 0.
- `.iSky` via `load_object` errors; `RFileIO.LoadFile` works. Black render background = no sky loaded.
- Sit Talk hip heights (F 56 / M 49 cm) -> lift male 7 cm on a 46 cm seat. Clip lengths 19.65 / 23.3 s -> chain.
- TTS (David/Zira) + `load_vocal` gives correct lip-sync; verified by jaw rotation spread.
- Foot bones read pinned while walking; 1 s sampling aliases the walk cycle -> judge gait from frames.
- Evidence: ReverseEngineerMCP `targets/iclone8/evidence.jsonl`, renders in `Documents\Reallusion\ParkBench\renders`.

## 2026-10-16 - RLPy2 discovery and first tools
- Live dump found RLPy2 (pybind11, inside iClone.exe). Undo/redo, silent mode, crowd_scatter, list_scene_nodes added
  (mc-iclone8-mcp 25188da). AccuPOSE API blocked without the plug-in.
- In-process dialog tools freeze with the main thread -> out-of-process `retk` window tools.
- `hot_reload.py` never reloaded `main.py`; `importlib.reload` cannot re-find it (file-path module) -> re-exec spec.
- Launch popups (registration nag, late post-crash prompt) now auto-answered.
