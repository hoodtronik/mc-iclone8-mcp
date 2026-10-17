# Scene spec (`scripts/build_scene.py`)

A scene is one JSON file. Units: **cm, Z up**; a character's front faces **-Y** (toward a camera placed at -Y).
Times in **seconds**. File paths: absolute, `${ENV}`-expanded, relative to the spec, or relative to the stock library
(avatars under `Reallusion Templates\Actor\Character`, motions under `Reallusion Templates\Animation\Motion` /
`Template\iClone 7 Template\iClone Template\Motion` / `...\MographMotion`, skies under `...\iClone Template\Sky`).
Working examples: `examples/scenes/park_bench.json` (primitives), `park_real.json` (real props), `plaza_crowd.json`
(crowds), `street_scene.json` (every feature: props, seated pair, group chat, walkers + wanderers, tracking shot).

| Key | Meaning |
|---|---|
| `name` | project name; saved to `~/Documents/Reallusion/<name>/<name>.iProject` unless `project` is given |
| `fps`, `length_s` | project frame rate (12/24/25/30/60) and length |
| `render` | output for the AI video model: `width`, `height`, `fps` (e.g. 832x480 at 16, 1280x720 at 24); shots are framed for this aspect. A render fps below the project fps RESAMPLES time (1 s at 15 fps = 16 files, numbered in output frames), so every pass and the MP4s stay in real time |
| `set[]` | primitive boxes: `name`, `size` [x,y,z], `at` [x,y] (centre), `bottom_z` (underside), `color` [r,g,b] 0-1; OR real content: `name`, `asset` (.iProp path or stock name, e.g. `Classic Park Bench_01`, `TSL_Roadster_Standard` under Props/Samples), `at`, `bottom_z`, `turn` (deg), `scale`. Real seats work with `sit_on` (seat found in the mesh). |
| `set[].room` | an interior: `{"name": "Room", "room": [width, depth, height], "at": [x, y]}` (Create > Surface > Room, an inward-facing box). Add top-level `"interior": "Room"` so every framed shot keeps its camera inside the walls (moves in, widens the lens). Furniture: `Leather Sofa 05` (an armchair), `Leather Sofa 12`, `Office Chair`, `Double Bed`, `Standing Lamp`, `Side-by-Side Refrigerator` |
| `paths[]` | `name`, `points` [[x,y],...] ground points; drawn with iClone's own path tool |
| `cast[]` | characters that stay in place: `name`, `avatar`, optional `motion` {`clip`, `start_s`, `loop_to_end`}, `place` {`at` [x,y,z], `turn` deg}, `sit_on` (prop name: `fit_sitter` rests the body on it), `sit_mode` (`seat` default / `feet`), `hold` {`preset` phone/cup/book or `prop`, `hand`, `offset_cm`, `rotation_deg`} (a prop in the hand), `actions` [{`clip`, `at_s`, `until_s`, `seconds`}] acting beats instead of `motion` (e.g. `HD Idle_M` 3 s, `Right_Turn_090`, `Step_Forward_Right_Small`, `HD Talk_M`; tails auto-trimmed, headings carried over), `look_at` (another cast name) |
| `groups[]` | standing conversations: `members` [{`name`, `avatar`, `clip`}] (e.g. Actor Group `Motion Plus/Actor Group/ActorGroup Series - Social Actions/01_Preset/01_Stand/3 People/3Stand_MMF/3Stand_Chat_G1_M1.iMotionPlus`), `at` [x,y], `radius_cm`, `start_deg` (0 = member 0 on the camera/-Y side), `until_s`. Members ring the point facing in. |
| `interactions[]` | contact via reach IK: `{"type": "handshake", "a", "b", "at_s", "seconds"}` - the pair must stand facing each other, chests <= ~100 cm apart (e.g. a 2-person `groups[]` entry with `radius_cm` 40) |
| `walkers[]` | moving characters. Straight: `from` [x,y], `to` [x,y], `start_s`, `pace_cm_s` (~100), `motion` (root-motion walk clip). Natural: `path` (a `paths` name), `imd` (male, female, male_stroll, male_jog (~330 cm/s), female_stroll, aged, child, crowd_male, crowd_female, push_cart, male_all, female_all, or a .iMD file), `start_s`, `seconds`, `stop_at_end` (default true: stops and idles at the path end; false = Motion Director keeps travelling back and forth along the path) |
| `vehicles[]` | a `set` prop driving a `paths` road: `name`, `path`, `start_s`, `speed_cm_s` (default 800 = 29 km/h), `front_axis` (stock cars 'Y Axis', the default). |
| `wander[]` | wandering crowd blocks (Motion Director Auto In Zone, `md_wander`): `zone` (a `set` prop name), `people` [{`name`, `avatar`, `imd`}], `seconds`, `start_s`, `spacing_cm`, `settings` (MD Action Settings, e.g. `IdleTimeRangeStart/End`, `MoveTimeRangeStart/End`, `IdleMoveFrequency`). Recorded in ONE `md_crowd` take with the path walkers that start at 0 (they avoid each other); zones are hidden. |
| `face[]` | facial performance: `who`, `clip` (stem 'Amused', mood folder 'Pleased'/'Sad'/'Excited', or path; see `list_expressions`), `at_s`, `until_s` (chains the clip). Combines with lip-sync. |
| `dialog[]` | `who` (cast name), `wav`, `at_s` - lip-sync is generated from the audio |
| `sky` | an `.iSky` file |
| `lighting` | time-of-day look on the stock rig: `preset` day/golden_hour/overcast/night, `sun_azimuth_deg` (0 = sun behind the camera on -Y, 90 = from +X, 180 = backlight), `sun_elevation_deg`, `intensity` |
| `camera` | single camera: `name`, `position`, `target`, `lens_mm` |
| `style`, `shots[].prompt` | text for the AI video model: with `--previz` each shot folder gets `prompt.txt` (shot prompt + scene style) and the manifest gets `prompt`, `shot`, `start_s`, `end_s` |
| `previz` | options for `--previz`: `passes` (any of beauty, openpose, depth, normal, canny; default the first three), `bFace`, `bHand`, `gizmo_scale` |
| `shots[]` | multi-camera edit: `id`, `start_s`, `end_s`, then EITHER `position`, `target`, `lens_mm` (+ optional `end_position`, `end_target`, `end_lens_mm` = a move) OR `frame` = `frame_shot` args (`subjects`, `size`: extreme_wide/wide/full/medium_wide/medium/medium_closeup/closeup/extreme_closeup/ots + `over_shoulder_of`, `azimuth_deg`, `facing`: body/head, `placement`, `lens_mm`) solved on the posed bodies over the whole shot, + optional `end_frame` (same keys) for a push-in/pull-out, or `track`: `follow` (camera moves with a walking subject, keyed every `track_step_s`, default 1 s) / `pan` (fixed camera re-aims). A `WARN ... fit_error` line = that OTS can't be clean for the staging. |

## Picking content (what exists in the stock library)

- **People**: `examples/catalog/avatars.json` lists every stock avatar with gender, age, height, outfit (`look`) and
  whether it has the CC skeleton (`cc_skeleton`; needed for `sit_on` and Motion Director). Use its `spec` value as
  `avatar`. The extension is optional and its case does not matter (some stock files are `.iavatar`). Unknown names
  fail with the list of folders searched. Quick picks (all realistic, CC skeleton):
  - elderly: men `Casual/Casual_M_0049`, `_0050` (white beard), `_0051` (Hawaiian shirt), `ActorCore Crowd/Casual_M_E0002`;
    women `Casual/Casual_F_0053` (~75), `Casual/Casual_F_0045` (~60s). (`_E0001`-style names are NOT elderly.)
  - office: `Business/Business_M_*`, `Business/Business_F_*`; young casual: `Casual/Casual_M_0054`-`0056`,
    `Casual/Casual_F_0019`, `_0054`, `_0055`; children: `Casual/Kid_F_0003`, `_0004`, `Kid_M_0004`-`0006`.
  - avoid for realistic previz: mannequins (`Motion Dummy*`), cartoons (`Toon Goon`, `Walter`, `Slacker_Morph`,
    `Coyote`, `TRex`), `Kevin ActorBUILD` (sci-fi armour), horses (no CC skeleton).
  Lineup renders: `scripts/avatar_catalog.py` writes them to `~/Documents/Reallusion/_scratch/AvatarCatalog/`.
- **Skies** (`sky`): `Cloudy`, `Clear Day 02`, `Clear Day 04`, `Clear Day 05`, `Sunset`, `Red Sky`, `Night`, `Sky_01`,
  `Sky_02`, `Sky_03`, `Universal` (`.iSky` optional). Match it to `lighting`: Sunset/Red Sky + `golden_hour`, Night +
  `night`, Cloudy + `overcast`.
- **Gaits** (`imd`): men `male_walk`, `male_stroll`, `male_jog`; women `female_walk`, `female_stroll` - there is **no
  female jog/run** in the stock library (use `female_walk`, or a male jogger); elderly `aged`; children `child`;
  background extras `crowd_male` / `crowd_female`; `push_cart`. `male_all` / `female_all` mix walk, stroll and idles.
- **Elderly acting**: sitting `.../ActorGroup Series - Social Actions/02_Idle/02_Sit/Elderly/` (`Sit_Rub legs_E`,
  `Sit_Take a nap_E`); a standing elderly + seated partner chat under `01_Preset/03_Stand and Sit/2 People/2StandSit_ME`
  (`_FE` for a woman). Walk them with `imd: aged`.
- **Phones**: `02_Idle/02_Sit/{Male,Female}/Sit_Text messages_*`, `Sit_Swipe phone_*`, `Sit_Talk_Phone_*`, standing
  `02_Idle/01_Stand/*/Stand_Swipe phone_Drink_*`; add `hold: {"preset": "phone"}`. There is no stock *reading* clip:
  use a phone/text clip with `hold: {"preset": "book"}`, or `Sit_Take a nap_E` for a still reader.
- **Weather**: the spec has no rain. The only stock effect is the legacy particle
  `Template/iClone 7 Template/iClone Template/Particle/Legacy/Environment/Rain.iParticle` (untested here) - describe
  rain in `style` / `prompt` for the AI model instead.

## When a build step complains

- `sit` **advice "clip expects a 35 cm seat but the seat is 43 cm"**: on a primitive seat, set the seat top to the
  clip's height. On a real prop (bench) pick a clip authored near that seat height from
  `examples/catalog/sit_clips.json` (`authored_seat_height_cm`), or accept it: `sit_mode: seat` (default) keeps the
  body on the seat and the feet float by the stated amount; `sit_mode: feet` plants the feet and the hips sink.
  A gap under ~5 cm rarely shows in a medium shot.
- `fit_sitter: could not find ...'s seat/sole surface`: that avatar's mesh can't be measured - use another avatar
  (`seat_vertices` > 0 in the catalog) or drop `sit_on` and place it by hand.
- `could not assign <path> to <walker>`: Motion Director could not pick the path in the viewport. Picks click the
  path's END point: don't end a path under another object or on the same spot as another path.
- **`start_s` on Motion Director walkers**: walkers and wanderers starting at 0 record together in one take and avoid
  each other. A walker with `start_s` > 0 records in a SEPARATE take and does not avoid the others - keep its path
  clear of them.

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
