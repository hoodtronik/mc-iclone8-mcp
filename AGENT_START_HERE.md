# Start here (any agent driving iClone through this MCP)

This repo lets an agent control Reallusion **iClone 8** (Windows) through an MCP server running *inside* iClone at
`http://127.0.0.1:8766/mcp`. Its main purpose: build **previz that drives AI video** (believable motion, readable
poses, camera shots, aligned beauty / OpenPose / depth passes).

Read this page, then `skills/iclone-mcp/SKILL.md`. Everything here was measured live; follow it literally.

## 1. Every session: run the doctor

```
python scripts/doctor.py
```
Fix every FAIL/WARN it prints (each line has a FIX). Typical: iClone not running → `python scripts/launch_iclone.py`;
a popup is open → read it, then press a button by name (below); scratch scene → save it to its own path.

## 2. The easy path: describe the scene, let the builder do it

Write a JSON spec (copy `examples/scenes/park_bench.json`; format in `docs/SCENE_SPEC.md`) and run:
```
python scripts/build_scene.py my_scene.json            # builds + verifies + QA filmstrip (discards the open scene)
python scripts/build_scene.py my_scene.json --previz   # + per-shot AI-video packages (slow)
python scripts/build_scene.py my_scene.json --stages walks,qa   # re-run only some stages
```
It handles: set (primitive boxes), paths, seated/looping characters with look-at, walkers (straight `walk_to` or
natural Motion Director along a path), dialog wavs with lip-sync, sky, a camera or a multi-shot edit, motion QA.
**Read the QA filmstrip** it saves (`<project dir>/qa/filmstrip.png`) and the `flags` it prints.

## 3. Calling single tools

From a shell (no MCP client needed): `python scripts/icall.py <tool> '<json args>'`, or
`python scripts/icall.py exec < snippet.py` to run Python inside iClone (`_result = ...` is returned).
Tool list with arguments: `skills/iclone-mcp/references/tool-catalog.md`. Prefer these (they carry measured fixes):

| Need | Tool |
|---|---|
| see a frame / motion over time | `render_snapshot`, `filmstrip` (focus=<avatar>) |
| numbers for motion quality | `motion_qa` (slide_ratio < 0.3, pop_count 0, no on-screen overlaps) |
| natural walk along a path | `draw_path` then `md_walk_path` (one) / `md_walk_paths` (a moving crowd, one take) |
| people milling about an area | `md_wander` (zone = any flat prop; one take for everyone) |
| walkers + wanderers together | `md_crowd` (ONE take so everyone avoids everyone; spec: `walkers[].path` + `wander[]`) |
| straight walk A→B | `walk_to` (pass `motion`) |
| clips on a character | `motion_track`, `load_motion_verified` (never raw `RFileIO.LoadMotion`) |
| place / hold an object | `place_object` |
| seat a sitter on a chair/bench | `fit_sitter` (seat heights per clip: `examples/catalog/sit_clips.json`) |
| cameras and cuts | `frame_shot` (by shot size: wide/full/medium/closeup/ots), `build_shot_list` |
| AI-video passes | `previz_export` (beauty + OpenPose + depth, MP4s, check sheet) |
| a QML panel's controls | `qml_inspect` |

## 4. If iClone freezes or a popup appears

In-process tools hang while a modal dialog is open. Use the out-of-process eyes (work even then):
```
python scripts/iclone_eyes.py popups                     # title, text, button names, PNG for every popup
python scripts/iclone_eyes.py press <hwnd> "OK"          # press a button by name
python scripts/iclone_eyes.py close <hwnd>               # WM_CLOSE
```
**Never** answer a save / discard / overwrite prompt about the user's work without asking the user.

## 5. Hard rules (each one cost real damage once)

1. Give every scene its own saved path before working (`save_project {"path": ...}`); checkpoint tools save in place.
2. Never load motions with `RFileIO.LoadMotion` (glues feet to the floor); use the tools.
3. Clear the selection before loading an avatar (a selected avatar gets REPLACED).
4. Verify with renders and `motion_qa`, not return codes. Look at the images.
5. Keep scenes reproducible: a JSON spec or a stage script, never only manual edits.
6. When you learn something new, add it to `skills/iclone-mcp/references/learning-log.md` (see the skill's section 7).

## 6. Map of the repo

`main.py` registers tool modules from `tools/` · `scripts/` (launch, hot reload, doctor, build_scene, icall,
iclone_eyes) · `examples/scenes/` specs · `skills/iclone-mcp/` operator skill (rules, recipes, gotchas, catalog) ·
`docs/hoodtronik/` research notes; `docs/hoodtronik/manual/` local copy of the iClone manual (gitignored; rebuild with
`scripts/scrape_docs.py manual-all`).
