---
name: iclone-mcp
description: Operating skill for driving Reallusion iClone 8 through the hoodtronik mc-iclone8-mcp server (136+ tools, RLPy + the hidden RLPy2 API, Qt/UI automation). Use for any iClone task through MCP - building scenes from primitives or content, placing/animating avatars (sit, talk, walk, crowds), lip-sync dialog, cameras, materials, skies, renders, undo - and for launching iClone, recovering from popups or a frozen main thread, or extending the MCP server itself. Encodes live-measured gotchas; read references before improvising.
---

# iClone MCP operator

Endpoint `http://127.0.0.1:8766/mcp` (local only). Repo: hoodtronik/mc-iclone8-mcp. Measured on iClone 8.75.5630.1.
Every rule here was learned live; `references/learning-log.md` says when and why. Update this skill as you learn
(see "Maintaining this skill").

## 1. Start / health

0. `python scripts/doctor.py` (repo root) checks everything below and prints a FIX per problem. New scenes: prefer a
   JSON spec + `python scripts/build_scene.py` (`docs/SCENE_SPEC.md`). Overview for any agent: `AGENT_START_HERE.md`.

1. `curl -s http://127.0.0.1:8766/health`. If down: `python scripts/launch_iclone.py` (autostart plugin installed;
   `--restart` kills a hung iClone, only after a save). It answers known startup prompts for 20 s after healthy.
2. `scripts/hot_reload.py` reloads tool code (including `main.py`) without restarting iClone. New tool modules must be
   registered in `main._tool_registry`.
3. Keep **eyes outside the process**: in-process tools (`list_dialogs`, `viewport_capture`) run on iClone's main
   thread and freeze with it. Use `python scripts/iclone_eyes.py popups|read|press|capture|close` (this repo, stdlib
   only; text + button names via UI Automation) or ReverseEngineerMCP's `retk_window_*` tools.

## 2. Hard rules (each cost a failure once)

- **Units**: cm, Z up, character front = -Y. Time: 6000 ticks/s, `RLPy.RTime.FromValue(ticks)` (never `RTime(int)`).
- **Save a project path early** (`save_project` with `path`): checkpoint tools (set_look_at, render_*, reach, edit_clip)
  save first and fail without one. The path is recovered from iClone after hot reloads.
- **Popups**: never press Enter on an unread dialog; the default button may be "Yes, save". Capture it, read it,
  Tab to the right button, Space. `python_exec silent=true` suppresses modal message boxes for that snippet only;
  never make silent mode global (it also auto-answers save/discard prompts).
- **Scratch scenes**: right after opening one, `save_project` it to its OWN scratch path (e.g.
  `Documents\Reallusion\_scratch\<name>.iProject`). Checkpoint tools save the current project in place; since
  6b270ba they skip unsaved default-project scenes, but a scratch scene must never share a real project's path.
- **Frozen iClone / popups**: `python scripts/iclone_eyes.py popups` (outside iClone) lists every popup's text and
  buttons; `press <hwnd> "<button>"` clicks by name. Read first; never press save/discard answers on your own.
- **New scene**: `new_project` still blocks on "discard? Yes/No/Cancel". Use
  `python_exec silent=true` with `RLPy.RFileIO.LoadFile(RLPy.RApplication.GetDefaultProjectPath())`, only when the
  open scene may be discarded.
- **Loading avatars**: clear the selection first (`RLPy.RScene.ClearSelectObjects()`); loading while an avatar is
  selected REPLACES it.
- **Skies** (`.iSky`): `load_object` errors; use `python_exec` + `RLPy.RFileIO.LoadFile(path)`.
- **Material colour** is KEYED at the current frame: `set_timeline frame 0` first or it fades in mid-shot.
- **Primitives**: box = 100 cm cube, pivot at bottom centre; scale = size/100, z = underside.
- **Motion clips: never `RFileIO.LoadMotion`** on avatars - it glues the feet to the floor (walks glide, a backflip
  becomes a fold-over). Use the tools (they go through `tools.common.load_motion_clip` = `LoadFile` at the playhead on
  the selected avatar) or call that helper from `python_exec`. A clip loaded right after another continues from where
  it ended; start it at the previous clip's end frame **+1**.
- **Wandering crowds**: `md_wander` (MD Auto In Zone on any prop; set Action Settings ONE key per call - the tool
  does). Mixed crowds: `md_crowd` = path walkers + zone wanderers in ONE take (separate takes walk through each
  other); it hides zones before Start (a visible zone slab makes path walkers detour), raises the avoidance radius
  to 50 cm and re-records (`retakes`, default 2) while two people come within 30 cm. Read `collisions` in the result.
- **Moving crowds**: `md_walk_paths` (one MD take for every walker with the same start frame; walkers start on their
  path). `RScene.SelectObject` REPLACES the selection - use `SelectObjects(list)` for multi-select.
- **Locomotion choice**: `md_walk_path` (Motion Director on a `draw_path` path, recorded clip; slide 0.0-0.1, real
  turns/idles; path must be visible in the current camera) beats `walk_to` (straight chained clips) for anything on
  screen. MD needs the user's Reallusion login for its content packs (installed on this PC 2026-10-16).
- **Walks** (`walk_to`): pass `motion` explicitly (defaults point at a content root on another machine; stock CC walk:
  `%PUBLIC%\Documents\Reallusion\Template\iClone 7 Template\iClone Template\Motion\03_CC MixMove_Male\Walk.iMotion`,
  `04_CC MixMove_Female` for women). The whole walk must end before the project end (the tool refuses otherwise);
  delayed walkers wait at `from`. Natural clip pace is ~85 cm/s; don't push speed far past it (legs look frantic).
  Opposite-direction walkers need lanes >= 60 cm apart (`motion_qa` reports overlaps).
- **Sitting**: seat height is a property of the CLIP (stock clips want 32-47 cm; Sit Talk M 34 / F 43). Look it up in
  `examples/catalog/sit_clips.json` (or measure: `fit_sitter apply=false`), build the seat at that height (pairs:
  Actor Group `2Sit_Chat_*` clips), then `fit_sitter {avatar, seat}` to rest the body on the seat. Never guess a lift
  from bone heights (that sank a sitter 4 cm with feet 8 cm up). `RIMesh.GetVertices` is the BIND pose, not deformed.
- **Cameras**: frame by SHOT SIZE with `frame_shot` (or spec `shots[].frame`), not hand-typed coordinates; pass
  `through_frame` (builder does) so a static shot holds moving subjects; `facing: head` to see turned faces; OTS
  `fit_error` > 0.3 = staging can't give a clean OTS. iClone camera: 36 mm film width, AOV is horizontal.
  Moving subjects: `frame_shot` `track: follow|pan` + `through_frame` keys a tracking camera; it dodges people on
  the sight line per key. In crowds use `track_step_s: 0.5` and `height_offset_cm: 60` (sight line over heads).
- **Clips end -> bind pose**: chain clips (`motion_track`) to cover the shot; check `get_animation_clips` end times.
- **Undo**: RLPy edits are not undoable unless run via `python_exec undo_label="..."` (one step). `undo`/`redo` tools
  flush pending UI steps first. Do not use `RGlobal.Undo` directly.
- **Viewport captures can be stale** right after edits; set the timeline or capture again. Trust `render_snapshot`.
- **Never claim success from a return code alone** - RLPy2 calls return RL_OK/RL_SAFE/RL_FAIL and `RL_SAFE` usually
  means "ignored". Read back the scene (positions, counts, renders).

## 3. Picking tools

Full generated list: `references/tool-catalog.md` (regenerate with `scripts/gen_tool_catalog.py`). Prefer, in order:
1. A dedicated tool (it encodes measured fixes): `md_walk_path` (best locomotion: Motion Director), `walk_to`, `walk_path`, `place_object`, `aim_camera`,
   `build_shot_list`, `frame_shot`, `fit_sitter`, `crowd_scatter`, `generate_crowd`, `set_look_at`, `load_motion_verified`, `motion_track`,
   `render_snapshot`, `render_control_pass`, `previz_export`, `undo`/`redo`, `list_scene_nodes`, `filmstrip`,
   `motion_qa`.
2. `python_exec` with RLPy / RLPy2 (`references/rlpy2.md`; signature dump in ReverseEngineerMCP
   `targets/iclone8/api/rlpy_live.json`). Use `undo_label` for edits, `silent` for risky loads.
3. UI-tier tools (`menu_action`, `timeline_clip_action`, `apply_pose`) - brittle; verify visually.

Find stock content with `references/content-paths.md` (sit/talk/walk motions, avatars, poses, skies).

**The iClone 8 manual is on disk**: mc-iclone8-mcp `docs/hoodtronik/manual/ic8/<section>__<topic>.md` (1030 English
topics incl. 8.1-8.7 additions like Motion Director) and `manual/wiki/` (RLPy API pages); one file per section in
`manual/bundles/`. Grep it before guessing how a feature or panel behaves. Gitignored (Reallusion copyright); rebuild on
a new machine with `python scripts/scrape_docs.py manual-all && python scripts/scrape_docs.py wiki &&
python scripts/bundle_docs.py`. Curated notes: `docs/hoodtronik/ICLONE8_AGENT_REFERENCE.md`,
`NOTEBOOKLM_PREVIZ_FIELD_GUIDE.md` (cite manual URLs; their UNVERIFIED claims need a live check).

## 4. Working loop for a scene

1. Write the plan as stages (project, set, cast, motion, dialog, sky, camera, renders) in a re-runnable script under
   ReverseEngineerMCP `targets/iclone8/scenes/` (pattern: `park_bench.py`, `icall.py` client). Recipes:
   `references/recipes.md`.
2. Run one stage, then verify: readback (positions, clip ends, counts via `list_scene_nodes`), `motion_qa` over the
   shot (foot slide, pops, overlaps as numbers), then a `filmstrip` (optionally `focus=<avatar>`) - LOOK at it.
   Jank lives between frames; single stills hide it.
3. Fix the tool, not just the scene, when a tool misbehaves (CLAUDE-NOTE the measured reason, add a test, hot reload).
4. When done, rebuild from scratch with the script once to prove it reproduces.
5. Deliver with `previz_export` (the MCP's main purpose is previz that drives AI video): beauty + OpenPose + depth per
   shot, MP4s, manifest, check sheet. Keep subjects large in frame; zoom-check OpenPose over beauty before handing off.

## 5. Verification checklist

- `motion_qa` clean: walkers `slide_ratio` < 0.3 (glide ~0.9), `pop_count` 0, no overlaps on screen.
- Positions at the frames that matter (sample densely: a 1 s step aliases a 1 s walk cycle).
- Nothing at the origin that should not be (late walkers, freshly loaded avatars).
- Lip-sync: jaw (`CC_Base_JawRoot`) rotation spread during a speaker's lines vs silence.
- Clip coverage to project end for every animated avatar.
- No open dialogs (out-of-process window list) before declaring done.

## 6. Extending the server

New tools go in fork modules (`tools/icmcp_extra.py`, `tools/rlpy2_tools.py`, ...), registered by `register()`;
keep upstream files untouched where possible. Every tool verified live before it ships; offline unittest with fake
RLPy (`tests/test_rlpy2_tools.py` pattern); run `uv run --no-project --python 3.8 python -m unittest discover -s tests`
(all pass since 2026-10-16). Security: HTTP server checks Host/Origin; keep it that way.

## 7. Maintaining this skill

After every iClone session (or sooner when something surprising is measured):
1. Add a dated entry to `references/learning-log.md` (what happened, the rule, the evidence).
2. Promote the rule to the right place: a hard rule above if ignoring it breaks work, else `references/gotchas.md`
   or `references/recipes.md`. Remove or correct rules that turned out wrong (never leave contradictions).
3. Regenerate `references/tool-catalog.md` if tools changed. Keep this file under ~2,000 words.
4. Commit to mc-iclone8-mcp with the change; the installed skill is a link to this folder, so it updates in place.
