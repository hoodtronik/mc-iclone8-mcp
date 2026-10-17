# Scene spec (`scripts/build_scene.py`)

A scene is one JSON file. Units: **cm, Z up**; a character's front faces **-Y** (toward a camera placed at -Y).
Times in **seconds**. File paths: absolute, `${ENV}`-expanded, relative to the spec, or relative to the stock library
(avatars under `Reallusion Templates\Actor\Character`, motions under `Reallusion Templates\Animation\Motion` /
`Template\iClone 7 Template\iClone Template\Motion` / `...\MographMotion`, skies under `...\iClone Template\Sky`).
Working example: `examples/scenes/park_bench.json`.

| Key | Meaning |
|---|---|
| `name` | project name; saved to `~/Documents/Reallusion/<name>/<name>.iProject` unless `project` is given |
| `fps`, `length_s` | project frame rate (12/24/25/30/60) and length |
| `set[]` | primitive boxes: `name`, `size` [x,y,z], `at` [x,y] (centre), `bottom_z` (underside), `color` [r,g,b] 0-1; OR real content: `name`, `asset` (.iProp path or stock name, e.g. `Classic Park Bench_01`, `TSL_Roadster_Standard` under Props/Samples), `at`, `bottom_z`, `turn` (deg), `scale`. Real seats work with `sit_on` (seat found in the mesh). |
| `paths[]` | `name`, `points` [[x,y],...] ground points; drawn with iClone's own path tool |
| `cast[]` | characters that stay in place: `name`, `avatar`, optional `motion` {`clip`, `start_s`, `loop_to_end`}, `place` {`at` [x,y,z], `turn` deg}, `sit_on` (prop name: `fit_sitter` rests the body on it), `sit_mode` (`seat` default / `feet`), `look_at` (another cast name) |
| `walkers[]` | moving characters. Straight: `from` [x,y], `to` [x,y], `start_s`, `pace_cm_s` (~100), `motion` (root-motion walk clip). Natural: `path` (a `paths` name), `imd` ("male"/"female"/file), `start_s`, `seconds` |
| `wander[]` | wandering crowd blocks (Motion Director Auto In Zone, `md_wander`): `zone` (a `set` prop name), `people` [{`name`, `avatar`, `imd`}], `seconds`, `start_s`, `spacing_cm`, `settings` (MD Action Settings, e.g. `IdleTimeRangeStart/End`, `MoveTimeRangeStart/End`, `IdleMoveFrequency`). Recorded in ONE `md_crowd` take with the path walkers that start at 0 (they avoid each other); zones are hidden. |
| `face[]` | facial performance: `who`, `clip` (stem 'Amused', mood folder 'Pleased'/'Sad'/'Excited', or path; see `list_expressions`), `at_s`, `until_s` (chains the clip). Combines with lip-sync. |
| `dialog[]` | `who` (cast name), `wav`, `at_s` - lip-sync is generated from the audio |
| `sky` | an `.iSky` file |
| `camera` | single camera: `name`, `position`, `target`, `lens_mm` |
| `shots[]` | multi-camera edit: `id`, `start_s`, `end_s`, then EITHER `position`, `target`, `lens_mm` (+ optional `end_position`, `end_target`, `end_lens_mm` = a move) OR `frame` = `frame_shot` args (`subjects`, `size`: extreme_wide/wide/full/medium_wide/medium/medium_closeup/closeup/extreme_closeup/ots + `over_shoulder_of`, `azimuth_deg`, `facing`: body/head, `placement`, `lens_mm`) solved on the posed bodies over the whole shot, + optional `end_frame` (same keys) for a push-in/pull-out, or `track`: `follow` (camera moves with a walking subject, keyed every `track_step_s`, default 1 s) / `pan` (fixed camera re-aims). A `WARN ... fit_error` line = that OTS can't be clean for the staging. |

## Tips that matter for AI-video previz
- Keep people large in frame (35-50 mm, 3-8 m away); tiny figures give poor pose/depth conditioning. Prefer `frame`
  shots (by size) over hand-typed coordinates: they follow the blocking when it changes.
- Over-the-shoulder needs people facing each other; side-by-side sitters -> use `medium_closeup` with `facing: head`.
- Walkers going opposite ways need lanes >= 60-85 cm apart; same-direction walkers need different start times.
- Seated motions are authored for a seat height (32-47 cm): look the clip up in `examples/catalog/sit_clips.json`,
  build the seat top at that height, and use `sit_on` (do not hand-tune `place.at` z). A mismatch prints `advice`.
  Two people on one bench: Actor Group pairs (`Motion Plus/Actor Group/.../02_Sit/2 People/...`) suit one seat height.
- Natural paced walks: ~85-110 cm/s. Faster looks frantic.
- Motion Director walkers need the user's Reallusion content packs (`scripts/doctor.py` checks). All MD walkers with
  the same `start_s` record in ONE real-time take (`md_walk_paths`); each starts on its own path start. A walker whose
  path ends early idles there for the rest of the take (MD idles include sitting on the ground): give paths similar
  lengths (~1 m/s), or `seconds` to cap the take. Example: `examples/scenes/plaza_crowd.json`.
