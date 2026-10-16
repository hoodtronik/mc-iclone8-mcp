---
name: iclone-mcp
description: Operating skill for driving Reallusion iClone 8 through the hoodtronik mc-iclone8-mcp server (136+ tools, RLPy + the hidden RLPy2 API, Qt/UI automation). Use for any iClone task through MCP - building scenes from primitives or content, placing/animating avatars (sit, talk, walk, crowds), lip-sync dialog, cameras, materials, skies, renders, undo - and for launching iClone, recovering from popups or a frozen main thread, or extending the MCP server itself. Encodes live-measured gotchas; read references before improvising.
---

# iClone MCP operator

Endpoint `http://127.0.0.1:8766/mcp` (local only). Repo: hoodtronik/mc-iclone8-mcp. Measured on iClone 8.75.5630.1.
Every rule here was learned live; `references/learning-log.md` says when and why. Update this skill as you learn
(see "Maintaining this skill").

## 1. Start / health

1. `curl -s http://127.0.0.1:8766/health`. If down: `python scripts/launch_iclone.py` (autostart plugin installed;
   `--restart` kills a hung iClone, only after a save). It answers known startup prompts for 20 s after healthy.
2. `scripts/hot_reload.py` reloads tool code (including `main.py`) without restarting iClone. New tool modules must be
   registered in `main._tool_registry`.
3. Keep **eyes outside the process**: in-process tools (`list_dialogs`, `viewport_capture`) run on iClone's main
   thread and freeze with it. Use the ReverseEngineerMCP `retk` window tools (MCP `retk_window_watch` /
   `retk_window_capture` / `retk_window_send`, or CLI `retk windows iClone.exe`, `retk capture <hwnd>`,
   `retk send <hwnd> tab|space|enter|escape|close`). After any call that may pop a dialog, watch for new windows.

## 2. Hard rules (each cost a failure once)

- **Units**: cm, Z up, character front = -Y. Time: 6000 ticks/s, `RLPy.RTime.FromValue(ticks)` (never `RTime(int)`).
- **Save a project path early** (`save_project` with `path`): checkpoint tools (set_look_at, render_*, reach, edit_clip)
  save first and fail without one. The path is recovered from iClone after hot reloads.
- **Popups**: never press Enter on an unread dialog; the default button may be "Yes, save". Capture it, read it,
  Tab to the right button, Space. `python_exec silent=true` suppresses modal message boxes for that snippet only;
  never make silent mode global (it also auto-answers save/discard prompts).
- **New scene**: `new_project` still blocks on "discard? Yes/No/Cancel". Use
  `python_exec silent=true` with `RLPy.RFileIO.LoadFile(RLPy.RApplication.GetDefaultProjectPath())`, only when the
  open scene may be discarded.
- **Loading avatars**: clear the selection first (`RLPy.RScene.ClearSelectObjects()`); loading while an avatar is
  selected REPLACES it.
- **Skies** (`.iSky`): `load_object` errors; use `python_exec` + `RLPy.RFileIO.LoadFile(path)`.
- **Material colour** is KEYED at the current frame: `set_timeline frame 0` first or it fades in mid-shot.
- **Primitives**: box = 100 cm cube, pivot at bottom centre; scale = size/100, z = underside.
- **Walks** (`walk_to`): pass `motion` explicitly (defaults point at a content root on another machine; stock CC walk:
  `%PUBLIC%\Documents\Reallusion\Template\iClone 7 Template\iClone Template\Motion\03_CC MixMove_Male\Walk.iMotion`,
  `04_CC MixMove_Female` for women). The whole walk must end before the project end (the tool refuses otherwise);
  delayed walkers wait at `from`. ~125 cm/s reads natural. Foot-bone positions read pinned during walks; judge gait
  from rendered frames, not bones.
- **Clips end -> bind pose**: chain clips (`motion_track`) to cover the shot; check `get_animation_clips` end times.
- **Undo**: RLPy edits are not undoable unless run via `python_exec undo_label="..."` (one step). `undo`/`redo` tools
  flush pending UI steps first. Do not use `RGlobal.Undo` directly.
- **Viewport captures can be stale** right after edits; set the timeline or capture again. Trust `render_snapshot`.
- **Never claim success from a return code alone** - RLPy2 calls return RL_OK/RL_SAFE/RL_FAIL and `RL_SAFE` usually
  means "ignored". Read back the scene (positions, counts, renders).

## 3. Picking tools

Full generated list: `references/tool-catalog.md` (regenerate with `scripts/gen_tool_catalog.py`). Prefer, in order:
1. A dedicated tool (it encodes measured fixes): `walk_to`, `walk_path`, `place_object`, `aim_camera`,
   `build_shot_list`, `crowd_scatter`, `generate_crowd`, `set_look_at`, `load_motion_verified`, `motion_track`,
   `render_snapshot`, `render_control_pass`, `undo`/`redo`, `list_scene_nodes`.
2. `python_exec` with RLPy / RLPy2 (`references/rlpy2.md`; signature dump in ReverseEngineerMCP
   `targets/iclone8/api/rlpy_live.json`). Use `undo_label` for edits, `silent` for risky loads.
3. UI-tier tools (`menu_action`, `timeline_clip_action`, `apply_pose`) - brittle; verify visually.

Find stock content with `references/content-paths.md` (sit/talk/walk motions, avatars, poses, skies).

## 4. Working loop for a scene

1. Write the plan as stages (project, set, cast, motion, dialog, sky, camera, renders) in a re-runnable script under
   ReverseEngineerMCP `targets/iclone8/scenes/` (pattern: `park_bench.py`, `icall.py` client). Recipes:
   `references/recipes.md`.
2. Run one stage, then verify: readback (positions, clip ends, counts via `list_scene_nodes`), then a
   `render_snapshot` at representative frames - LOOK at the image.
3. Fix the tool, not just the scene, when a tool misbehaves (CLAUDE-NOTE the measured reason, add a test, hot reload).
4. When done, rebuild from scratch with the script once to prove it reproduces.

## 5. Verification checklist

- Positions at the frames that matter (sample densely: a 1 s step aliases a 1 s walk cycle).
- Nothing at the origin that should not be (late walkers, freshly loaded avatars).
- Lip-sync: jaw (`CC_Base_JawRoot`) rotation spread during a speaker's lines vs silence.
- Clip coverage to project end for every animated avatar.
- No open dialogs (out-of-process window list) before declaring done.

## 6. Extending the server

New tools go in fork modules (`tools/icmcp_extra.py`, `tools/rlpy2_tools.py`, ...), registered by `register()`;
keep upstream files untouched where possible. Every tool verified live before it ships; offline unittest with fake
RLPy (`tests/test_rlpy2_tools.py` pattern); run `uv run --no-project --python 3.8 python -m unittest discover -s tests`
(`test_call_tool` fails pre-existing). Security: HTTP server checks Host/Origin; keep it that way.

## 7. Maintaining this skill

After every iClone session (or sooner when something surprising is measured):
1. Add a dated entry to `references/learning-log.md` (what happened, the rule, the evidence).
2. Promote the rule to the right place: a hard rule above if ignoring it breaks work, else `references/gotchas.md`
   or `references/recipes.md`. Remove or correct rules that turned out wrong (never leave contradictions).
3. Regenerate `references/tool-catalog.md` if tools changed. Keep this file under ~2,000 words.
4. Commit to mc-iclone8-mcp with the change; the installed skill is a link to this folder, so it updates in place.
