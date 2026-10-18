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
- **Multi-select**: `RScene.SelectObject` REPLACES the selection; use `SelectObjects(list)`.
- **Clips end -> bind pose**: chain clips (`motion_track`) to cover the shot; check `get_animation_clips` end times.
- **Undo**: RLPy edits are not undoable unless run via `python_exec undo_label="..."` (one step). `undo`/`redo` tools
  flush pending UI steps first. Do not use `RGlobal.Undo` directly.
- **Viewport captures**: with iClone in the background `viewport_capture` renders the current camera instead of
  grabbing the stale GL view (result `target` says so). `render_snapshot` remains the proof for a specific frame.
- **Never claim success from a return code alone** - RLPy2 calls return RL_OK/RL_SAFE/RL_FAIL and `RL_SAFE` usually
  means "ignored". Read back the scene (positions, counts, renders).

## 3. Task recipes (pick the tool, know its trap)

| Task | Tool | Trap / rule that matters |
|---|---|---|
| natural walk on a path | `draw_path` + `md_walk_path` | path must be visible in the current camera; MD packs need the user's Reallusion login |
| several walkers / a crowd crossing | `md_walk_paths` | one real-time take per start frame; walkers start on their path |
| people milling about | `md_wander` (zone = any flat prop) | Action Settings one key per call (tool does it) |
| audience / onlookers / queue facing something | spec `crowds[]` (rows / arc / scatter + `focus`) | expanded into cast (full avatars, real clips); the Crowd Generator panel only scatters light actors |
| walkers + wanderers together | `md_crowd` | ONE take so everyone avoids everyone; hides zones; `retakes` while hips < 30 cm |
| straight A->B walk | `walk_to` | pass `motion` (stock CC walk under `Template\iClone 7 Template\iClone Template\Motion\03_CC MixMove_Male`); ~85 cm/s; ends before project end; lanes >= 60 cm |
| sit on a bench/chair | `fit_sitter {avatar, seat}` | seat height belongs to the CLIP (32-47 cm): `examples/catalog/sit_clips.json`; real props: seat found in the mesh; pairs: Actor Group `2Sit_Chat_*` |
| do two things at once (text/talk while walking) | `overlay_clip {avatar, clip, start_frame, end_frame, bones}` | motion-layer keys over the body's clip; spec `overlay` |
| touch / wipe / pick up a prop | `hand_reach {avatar, action, object or point, at_s}` | reach IK; target within ~65 cm of the shoulder; spec `reach` |
| show the user the result | `build_scene.py spec --previz` -> `previz/reel/` | edit + passes side by side + index.html; to watch on a phone publish the reel folder as an Artifact (copy it under the project's gitignored `work/` first - scratchpad media is read-blocked) |
| group chat (standing) | `group_conversation` | Actor Group member clips are in place: the tool makes the ring layout |
| facial expression | `face_performance` (`list_expressions`) | .iTalk on the FACE track; also turns head/eyes - check close-ups |
| camera by shot size | `frame_shot` (spec `shots[].frame`) | `through_frame` for moving subjects; `facing: head`; dodges blockers; OTS `fit_error` > 0.3 = bad staging |
| tracking shot | `frame_shot track: follow/pan` | crowds: `track_step_s 0.5`, `height_offset_cm 60` |
| vehicle along a road | `draw_path` + `drive_path` | stock cars face +Y ('Y Axis'); Follow Path controls only work with the playhead inside the path range (tool handles it) |
| acting beats in order | `perform_sequence` | chained clips keep POSITION but not HEADING - the tool keys the carry-over; Standing Pack turns/steps are ~10.9 s (trim='auto'); refuses beats past the project end |
| handshake | `handshake` | no stock contact clips; reach IK to hidden targets; chests <= ~100 cm apart |
| prop in a hand | `hold_prop` (preset phone/cup/book) | LinkTo `__None` keeps the WORLD offset at link time - pose must be evaluated first (tool does) |
| lighting look | `light_preset` | re-aims the stock Key/Side/Back; the visible ground shadow is the 'Floor Shadow' light (tool aims it with the sun) |
| add a light (lamp, pendant, streetlight) | `add_light {kind, position, aim_at, color, multiplier, range}` | goes through Create > Light (adds); NEVER RFileIO.LoadObject a .iLight - it replaces every light; spec `lights` |
| IBL / ambient fill | `environment_light` | `save_current_to` before `ibl_image` (a load can't be undone); spec `environment` |
| depth of field / rack focus | `focus_on {camera, target or keys, look}` | focus = DEPTH along the view axis (tool measures heads); RemoveDofKeys leaves blur on - use look `off`; spec `shots[].focus` |
| finger poses (grip a cup, point, fist) | `hand_pose {avatar, hand, poses:[{pose, start_frame, end_frame}]}` | one call per hand (a second call clears the first); .iHand content can't be applied from Python; spec `hands` |
| quick beauty video of a range (dailies, review) | `render_video {output_path, start_frame, end_frame, width, height}` | native encoder, synchronous, ~real time at 832x480; follows switch-camera cuts; fps comes from the render panel (16 here) - pass `fps` to change it. Alpha-only gives a white matte while a sky is loaded |
| stop a planted foot sliding / pin a hand | `pin_effector {avatar, effector, start_s, end_s}` | hidden marker + reach TARGET key + release; ReachKeyType_Lock does nothing and head reach fails; spec `cast[].pins` |
| animate a prop over time (slide, roll in, swing) | spec `set[].moves` [{start_s, end_s, to, turn, transition}] (or `place_object {frame, clear_keys:false}` + `set_transform_key_transition`) | measured: linear moves exact at every frame, holds before start_s; key at frame 0 first (auto-key rule) |
| duplicate a prop or person (row of chairs, a second walker) | `clone_object {name, new_name, offset:{x,y,z}, turn_deg, count}` | clips, layer keys and every transform key come along, shifted (walker clone stays exactly offset through its walk); count = series new_name01.. |
| look into the lens / glance at someone | `set_look_at {avatar, target: <camera or prop>, frame}` (object mode) or target an avatar (head, bone mode) | measured: the eyes lock onto the lens (0.5-3.6 deg), the head turns most of the way; spec `cast[].looks` [{target: shot id / person / set, at_s, until_s}] |
| turn the head / nod / lean (FK pose) | `pose_bones {avatar, bones:{head:{yaw,pitch,roll}}, start_frame, end_frame}` | body-relative degrees, additive layer keys; clears earlier layer keys on those bones; spec `pose` |
| interior | spec `set[].room` + `interior`; `frame_shot inside=<room>` | Room surface = inward 957 cm cube; cameras solved by distance end up behind walls unless kept inside |
| AI-video package | `previz_export` | beauty + OpenPose + depth, MP4s, check sheet; long shots are fine (tool timeout 2 h) |

Details and the measurements behind each rule: `references/learning-log.md` (newest first) and `gotchas.md`.

## 4. Picking tools

Full generated list: `references/tool-catalog.md` (regenerate with `skills/iclone-mcp/scripts/gen_tool_catalog.py`). Prefer, in order:
0. For a whole scene, write a JSON spec and run `scripts/build_scene.py` (`docs/STORY_TO_SPEC.md` maps story beats to
   blocks; format `docs/SCENE_SPEC.md`; every feature in `examples/scenes/street_scene.json`).
1. A dedicated tool (it encodes measured fixes): see the recipes table above, plus `place_object`, `aim_camera`,
   `build_shot_list`, `set_look_at`, `load_motion_verified`, `motion_track`, `render_snapshot`, `render_control_pass`,
   `undo`/`redo`, `list_scene_nodes`, `filmstrip`, `motion_qa`.
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

## 5. Working loop for a scene

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

## 6. Verification checklist

- `motion_qa` clean: walkers `slide_ratio` < 0.3 (glide ~0.9), `pop_count` 0, no overlaps on screen.
- Positions at the frames that matter (sample densely: a 1 s step aliases a 1 s walk cycle).
- Nothing at the origin that should not be (late walkers, freshly loaded avatars).
- Lip-sync: jaw (`CC_Base_JawRoot`) rotation spread during a speaker's lines vs silence.
- Clip coverage to project end for every animated avatar.
- No open dialogs (out-of-process window list) before declaring done.

## 7. Extending the server

New tools go in fork modules (`tools/icmcp_extra.py`, `tools/rlpy2_tools.py`, ...), registered by `register()`;
keep upstream files untouched where possible. Every tool verified live before it ships; offline unittest with fake
RLPy (`tests/test_rlpy2_tools.py` pattern); run `uv run --no-project --python 3.8 python -m unittest discover -s tests`
(all pass since 2026-10-16). Security: HTTP server checks Host/Origin; keep it that way.

## 8. Maintaining this skill

After every iClone session (or sooner when something surprising is measured):
1. Add a dated entry to `references/learning-log.md` (what happened, the rule, the evidence).
2. Promote the rule to the right place: a hard rule above if ignoring it breaks work, else `references/gotchas.md`
   or `references/recipes.md`. Remove or correct rules that turned out wrong (never leave contradictions).
3. Regenerate `references/tool-catalog.md` if tools changed. Keep this file under ~2,000 words.
4. Commit to mc-iclone8-mcp with the change; the installed skill is a link to this folder, so it updates in place.

## Feature registry

Every iClone 8 feature is graded 0-5 in ReverseEngineerMCP `targets/iclone8/feature_registry.json` (report: `FEATURE_REGISTRY.md`). Check it before assuming a feature is (un)supported; after you tool or verify a feature, raise its grade with the evidence in `why` and run `retk registry-score iclone8 --md`.
