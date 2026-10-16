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
| `set[]` | primitive boxes: `name`, `size` [x,y,z], `at` [x,y] (centre), `bottom_z` (underside), `color` [r,g,b] 0-1 |
| `paths[]` | `name`, `points` [[x,y],...] ground points; drawn with iClone's own path tool |
| `cast[]` | characters that stay in place: `name`, `avatar`, optional `motion` {`clip`, `start_s`, `loop_to_end`}, `place` {`at` [x,y,z], `turn` deg}, `look_at` (another cast name) |
| `walkers[]` | moving characters. Straight: `from` [x,y], `to` [x,y], `start_s`, `pace_cm_s` (~100), `motion` (root-motion walk clip). Natural: `path` (a `paths` name), `imd` ("male"/"female"/file), `start_s`, `seconds` |
| `dialog[]` | `who` (cast name), `wav`, `at_s` - lip-sync is generated from the audio |
| `sky` | an `.iSky` file |
| `camera` | single camera: `name`, `position`, `target`, `lens_mm` |
| `shots[]` | multi-camera edit: `id`, `start_s`, `end_s`, `position`, `target`, `lens_mm`, optional `end_position`, `end_target`, `end_lens_mm` (a move over the shot) |

## Tips that matter for AI-video previz
- Keep people large in frame (35-50 mm, 3-8 m away); tiny figures give poor pose/depth conditioning.
- Walkers going opposite ways need lanes >= 60-85 cm apart; same-direction walkers need different start times.
- Seated motions are authored for a seat height: `Sit Talk` male ~40 cm, female ~46 cm (lift with `place.at` z).
- Natural paced walks: ~85-110 cm/s. Faster looks frantic.
- Motion Director walkers need the user's Reallusion content packs (`scripts/doctor.py` checks).
