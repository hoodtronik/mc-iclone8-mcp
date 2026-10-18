# Scene spec (`scripts/build_scene.py`)

A scene is one JSON file. Units: **cm, Z up**, floor at z 0; a character's front faces **-Y** (toward a camera placed
at -Y). `turn` (people and props) is degrees counter-clockwise seen from above: a -Y front turns to +X at 90, +Y at
180, -X at -90 (measured).
**Check first**: `python scripts/build_scene.py spec.json --check` resolves every file and name offline in seconds
and suggests close names (`did you mean ...`); a build runs the same check and stops on errors.
Times in **seconds**. File paths: absolute, `${ENV}`-expanded, relative to the spec, or relative to the stock library
(avatars under `Reallusion Templates\Actor\Character`, motions under `Reallusion Templates\Animation\Motion` /
`Template\iClone 7 Template\iClone Template\Motion` / `...\MographMotion`, skies under `...\iClone Template\Sky`).
Motion paths may also start at `Animation` (`Motion Plus/Actor Group/...`, as in the examples) or be copied from the
catalogs as-is (`Reallusion Templates/Animation/...`) - all resolve to the same file.
Working examples: `examples/scenes/park_bench.json` (primitives), `park_real.json` (real props), `plaza_crowd.json`
(crowds), `street_scene.json` (every feature: props, seated pair, group chat, walkers + wanderers, tracking shot).

| Key | Meaning |
|---|---|
| `name` | project name; saved to `~/Documents/Reallusion/<name>/<name>.iProject` unless `project` is given |
| `fps`, `length_s` | project frame rate (12/24/25/30/60) and length |
| `render` | output for the AI video model: `width`, `height`, `fps` (e.g. 832x480 at 16, 1280x720 at 24); shots are framed for this aspect. A render fps below the project fps RESAMPLES time (1 s at 15 fps = 16 files, numbered in output frames), so every pass and the MP4s stay in real time |
| `set[]` | primitive boxes: `name`, `size` [x,y,z], `at` [x,y] (centre), `bottom_z` (underside), `color` [r,g,b] 0-1, `fit_height` (true on a seat box: it takes the height its one sitter's clip needs, measured at build); OR real content: `name`, `asset` (.iProp path or stock name, e.g. `Classic Park Bench_01`, `TSL_Roadster_Standard` under Props/Samples), `at`, `bottom_z`, `turn` (deg), `scale`. Real seats work with `sit_on` (seat found in the mesh). Any non-room item may also take `moves` [{`start_s`, `end_s`, `to` [x,y], `bottom_z`, `turn`, `transition` (ease_in_out default, linear for an even speed, ease_in, ease_out, step)}]: it holds still until `start_s` and arrives at `end_s` (a cart rolled in, a box slid along the counter, a gate swung with `turn`). Moves may not overlap. |
| `set[].room` + `doorways` | a room you can walk into: [{`wall` -X/+X/-Y/+Y, `center` (cm along the wall from the room centre), `width` (100), `height` (215), `door` {`open_at_s`, `seconds` (1.2), `deg` (95), `hinge` near/far, `color`}}]. Built from box walls (no ceiling unless `ceiling: true`, so the sun lights it; `wall_color`, `floor_color`, `outside_cm` floor beyond the walls); the door leaf swings INTO the room on cue. Start a walker's path outside and run it through the opening (walls and door are hidden while Motion Director records). |
| `set[].room` | an interior: `{"name": "Room", "room": [width X, depth Y, height Z], "at": [x, y]}` (centred on `at`, floor at z 0) (Create > Surface > Room, an inward-facing box). Add top-level `"interior": "Room"` so every framed shot keeps its camera inside the walls (moves in, widens the lens); hand-placed `position` shots are not moved - keep them inside yourself. Room walls are hidden while Motion Director records (they block walkers) and shown again after. Furniture: `Leather Sofa 05` (an armchair), `Leather Sofa 12`, `Office Chair` (seat top 45 cm, faces -Y), `Double Bed`, `Standing Lamp`, `Side-by-Side Refrigerator` |
| `paths[]` | `name`, `points` [[x,y],...] ground points; drawn with iClone's own path tool |
| `cast[]` | characters that stay in place: `name`, `avatar`, optional `motion` {`clip`, `start_s`, `loop_to_end`}, `place` {`at` [x,y,z], `turn` deg}, `sit_on` (prop name: `fit_sitter` rests the body on it - it sets the HEIGHT only; put `at` on the seat (the chair's own `at` works), `turn` = the seat's), `sit_mode` (`seat` default / `feet`), `hold` {`preset` phone/cup/book or `prop`, `hand`, `offset_cm`, `rotation_deg`} (a prop in the hand), `actions` [{`clip`, `at_s`, `until_s`, `seconds`}] acting beats instead of `motion` (e.g. `HD Idle_M` 3 s, `Right_Turn_090`, `Step_Forward_Right_Small`, `HD Talk_M`; women: `HD Idle 01_F`, `HD Idle 02_F`, `HD Emote_F`, `HD Posing_F` - there is no `HD Talk_F`/`HD Think_F`; tails auto-trimmed, headings carried over), `look_at` (another cast name), `overlay` (see below) |
| `cast[]` / `walkers[].laugh` | [{`at_s`, `seconds` (2), `intensity` (1 = hearty, 0.5 = chuckle), `face` (true)}]: leans back, head up, chest heave and shoulder bounce at ~4.5 Hz, smile + squint with the mouth opening on each 'ha'. Built procedurally (no stock laugh clip exists); runs after `face[]`, so it wins over an expression clip at that time. |
| `cast[].reach` | hand contact via reach IK over the clip: [{`action` touch / wipe / pick, `hand` right/left, `point` [x,y,z] or `object` (a set name; its top centre), `offset_cm`, `at_s`, `seconds`, `ramp_s` (0.5), wipe: `width_cm` (40), `stroke_s` (0.6)}]. touch = push a door, rest a hand on a counter; wipe = strokes across a surface in front of the body; pick = grab the object and carry it (it stays in the hand). Targets beyond ~65 cm from the shoulder are refused - stand the person close. |
| `cast[]` / `walkers[].overlay` | part-body actions on top of the body's motion: [{`clip`, `bones` (arm_r, arm_l, arms, head, arm_r_head, arms_head, upper), `at_s`, `until_s`, `blend_s` (0.4), `clip_offset_s`}]. The chosen bones follow `clip` while the rest keeps walking/idling/sitting - e.g. texting while walking = walker + `hold` phone + overlay `Stand_Swipe phone_Drink_M` on `arm_r_head`; talking while walking = overlay `2Stand_Chat_G1_M1` (Actor Group chat: real hand gestures, head turns to the side; `HD Talk_M` barely moves the arms) on `arms_head`. Bare clip stems work. A `hold` prop rides the overlaid hand. |
| `cast[]` / `walkers[].hands` | finger poses on top of any clip: [{`pose` open/relaxed/fist/point/grip/pinch/thumbs_up/peace, `hand` r (default) / l / both, `at_s`, `until_s`}]. Spans on the same hand must not overlap. Use `grip` on a hand that holds a cup/phone (stock clips often leave it half open around the prop), `point` for pointing, `fist` for anger, `open` for a wiping hand. Runs after overlays (an arm overlay also moves the fingers). Matters for the OpenPose hand pass. |
| `cast[].pins` | hold a planted foot (or hand) still on top of the clip: [{`effector` left_foot / right_foot / left_hand / right_hand, `at_s`, `until_s`}]. The limb stays where it was at `at_s` (measured: a talking clip's 21 cm foot shuffle -> 1.1 cm) and rejoins the clip after `until_s`. Use when an idle or talk clip skates; not on walkers; no head. |
| `cast[].looks` | timed glances [{`target`, `at_s`, `until_s`}]: a person (their head), a `set` name, or a SHOT ID = that shot's camera (a look straight into the lens). The head eases over ~0.4 s; after `until_s` it goes back to the member's `look_at` (or is released). One look at a time; sort by `at_s`. E.g. `{target: "Man", at_s: 8.8, until_s: 10.6}` (glances at the man coming in). |
| `cast[]` / `walkers[].pose` | FK pose beats on top of any clip: [{`bones` {name: {`yaw`, `pitch`, `roll`} degrees}, `at_s`, `until_s`, `blend_s` (0.3)}]. Axes are the BODY's: yaw + turns to the character's own left, pitch + looks up / leans back, roll + tilts toward the right shoulder. Names: `head`, `neck`, `chest`, `spine`, `waist`, `hip`, `r_shoulder`/`l_shoulder`, `r_upperarm`, `r_forearm`, `r_hand` (and `l_`), `r_thigh`, `r_calf`, or CC_Base_ names. E.g. glance at the door `{head: {yaw: 40}}`, nod `{head: {pitch: -15}}`, slump `{chest: {pitch: -12}}`. A bone may appear in one entry only, and not together with `laugh`. |
| `groups[]` | standing conversations: `members` [{`name`, `avatar`, `clip`}] (e.g. Actor Group `Motion Plus/Actor Group/ActorGroup Series - Social Actions/01_Preset/01_Stand/3 People/3Stand_MMF/3Stand_Chat_G1_M1.iMotionPlus`), `at` [x,y], `radius_cm`, `start_deg` (0 = member 0 on the camera/-Y side), `until_s`. Members ring the point facing in. |
| `interactions[]` | contact via reach IK: `{"type": "handshake", "a", "b", "at_s", "seconds"}` - the pair must stand facing each other, chests <= ~100 cm apart (e.g. a 2-person `groups[]` entry with `radius_cm` 40) |
| `walkers[]` | moving characters. Straight: `from` [x,y], `to` [x,y], `start_s`, `pace_cm_s` (~100), `motion` (root-motion walk clip). Natural: `path` (a `paths` name), `imd` (male, female, male_stroll, male_jog (~330 cm/s), female_stroll, aged, child, crowd_male, crowd_female, push_cart, male_all, female_all, or a .iMD file), `start_s`, `seconds`, `stop_at_end` (default true: stops and idles at the path end; false = Motion Director keeps travelling back and forth along the path). `arrive_clip` (path walkers that stop: a clip played on arrival instead of the stock idle, blended in over 0.5 s, e.g. `Motion Plus/Actor Group/ActorGroup Series - Social Actions/02_Idle/01_Stand/Male/Stand_Swipe phone_Drink_M`), `hold` (as on cast; the prop is in the hand for the whole shot). Walkers take no `actions`, `look_at` or `sit_on`. |
| `vehicles[]` | a `set` prop driving a `paths` road: `name`, `path`, `start_s`, `speed_cm_s` (default 800 = 29 km/h), `front_axis` (stock cars 'Y Axis', the default). |
| `wander[]` | wandering crowd blocks (Motion Director Auto In Zone, `md_wander`): `zone` (a `set` prop name), `people` [{`name`, `avatar`, `imd`}], `seconds`, `start_s`, `spacing_cm`, `settings` (MD Action Settings, e.g. `IdleTimeRangeStart/End`, `MoveTimeRangeStart/End`, `IdleMoveFrequency`). Recorded in ONE `md_crowd` take with the path walkers that start at 0 (they avoid each other); zones are hidden. |
| `crowds[]` | standing crowds laid out for you and built as ordinary `cast` (named `<name>01`, `<name>02`...): `name`, `count`, `formation` rows (an audience block centred on `at`, first row nearest the focus, staggered) / arc (a ring of `radius_cm` around `at` spanning `arc_deg`, e.g. onlookers around a busker at `at`) / scatter (random in `size` [w,d], `spacing_cm` apart), `focus` [x,y] everyone turns to (arc: defaults to `at`), `facing_deg` (rows/arc: where they look; 0 = -Y), `jitter_deg` (8), `seed`, and `people` [{`avatar`, `clip`}] (cycled; keeps gendered clips on matching bodies - full library paths, e.g. `Motion Plus/Actor Group/Embed/02_Idle/01_Stand/Male/Stand Wait_M.iMotionPlus`) or `avatars` + `clips` pools. Use for audiences, queues, onlookers; `wander` is for people who walk about. Each member is a full avatar: keep crowds under ~12. |
| `face[]` | facial performance: `who`, `clip` (stem 'Amused', mood folder 'Pleased'/'Sad'/'Excited', or path; see `list_expressions`), `at_s`, `until_s` (chains the clip). Combines with lip-sync. |
| `dialog[]` | `who` (cast name), `wav`, `at_s` - lip-sync is generated from the audio |
| `sky` | an `.iSky` file |
| `lighting` | time-of-day look on the stock rig: `preset` day/golden_hour/overcast/dusk/night, `sun_azimuth_deg` (0 = sun behind the camera on -Y, 90 = from +X, 180 = backlight), `sun_elevation_deg`, `intensity` (multiplier, default 1) |
| `lights[]` | NEW lights added to the scene (the stock rig stays): [{`kind` spot/point/directional, `name`, `position` [x,y,z] cm, `aim_at` [x,y,z] (or `direction`), `color` [r,g,b] 0-1, `multiplier`, `range` cm, spot: `spot_angle` (45), `spot_falloff` (20), `cast_shadow`}]. Practicals sell an interior: a warm spot pendant over a table (`position` 2 m above it, `aim_at` its top, angle ~70), a point lamp behind a counter. |
| `environment` | scene-wide light: `ambient_color` [r,g,b] 0-1 (lifts/tints every shadow; keep it under ~0.1), `ibl_enable`, `ibl_image` (.hdr), `sync_sky_image`, `sync_sky_orientation`. |
| `camera` | single camera: `name`, `position`, `target`, `lens_mm` |
| `style`, `shots[].prompt` | text for the AI video model: with `--previz` each shot folder gets `prompt.txt` (shot prompt + scene style) and the manifest gets `prompt`, `shot`, `start_s`, `end_s` |
| `previz` | options for `--previz`: `passes` (any of beauty, openpose, depth, normal, canny; default the first three), `bFace`, `bHand`, `gizmo_scale` |
| `shots[]` | multi-camera edit: `id`, `start_s`, `end_s`, then EITHER `position`, `target`, `lens_mm` (+ optional `end_position`, `end_target`, `end_lens_mm` = a move) OR `frame` = `frame_shot` args (`subjects`, `size`: extreme_wide/wide/full/medium_wide/medium/medium_closeup/closeup/extreme_closeup/ots + `over_shoulder_of`, `azimuth_deg`, `facing`: body/head, `placement`, `lens_mm`) solved on the posed bodies over the whole shot, + optional `end_frame` (same keys) for a push-in/pull-out, or `track`: `follow` (camera moves with a walking subject, keyed every `track_step_s`, default 1 s) / `pan` (fixed camera re-aims). A `WARN ... fit_error` line = that OTS can't be clean for the staging. |
| `shots[].focus` | depth of field: `{target, look}` (person or set name, or [x,y,z]; look shallow = background melts, medium, deep, off) or rack focus `{look, keys: [{at_s, target}, ...]}` (keys inside the shot, linear between). A single `target` is FOLLOW focus (re-measured from the posed head every 0.5 s through the shot), so walkers stay sharp. Beauty pass only; depth/OpenPose passes stay sharp. |

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
  `Sky_02`, `Sky_03`, `Universal` (`.iSky` optional). Match it to `lighting`: Sunset/Red Sky + `golden_hour` or
  `dusk`, Night + `night`, Cloudy + `overcast`.
- **Gaits** (`imd`): men `male_walk`, `male_stroll`, `male_jog`; women `female_walk`, `female_stroll` - there is **no
  female jog/run** in the stock library (use `female_walk`, or a male jogger); elderly `aged`; children `child`;
  background extras `crowd_male` / `crowd_female`; `push_cart`. `male_all` / `female_all` mix walk, stroll and idles.
  Measured speeds (cm/s) in `examples/catalog/gaits.json`: male_walk 114, male_stroll 77, male_jog 358, female_walk
  101, female_stroll 43 (very slow), aged 35, child 66, crowd_male 111, crowd_female 84. Female gaits need ~4 s to
  reach speed. Walkers who move together need matching speeds: couple = `male_stroll` + `crowd_female`.
- **Elderly acting**: sitting `.../ActorGroup Series - Social Actions/02_Idle/02_Sit/Elderly/` (`Sit_Rub legs_E`,
  `Sit_Take a nap_E`); a standing elderly + seated partner chat under `01_Preset/03_Stand and Sit/2 People/2StandSit_ME`
  (`_FE` for a woman). Walk them with `imd: aged`.
- **Phones**: `02_Idle/02_Sit/{Male,Female}/Sit_Text messages_*`, `Sit_Swipe phone_*`, `Sit_Talk_Phone_*`, standing
  `02_Idle/01_Stand/*/Stand_Swipe phone_Drink_*`; add `hold: {"preset": "phone"}`. Other standing idles:
  `Stand_Look around_Drink_{M,F}` (a cup), `Stand_Wait_Bag_F`, `Stand_Wait_Backpack_M`. The `_Drink` clips are
  animated for a cup in hand but load none - add `hold: {"preset": "cup"}`. There is no stock *reading* clip:
  use a phone/text clip with `hold: {"preset": "book"}`, or `Sit_Take a nap_E` for a still reader.
- **Real props**: `asset` props stand with their base at `bottom_z` (default 0). Thin slabs (sidewalks 1 cm) need no
  offset; on a raised slab set the prop's `bottom_z` to the slab top. `Classic Park Bench_01` seat top = 43 cm
  (backrest 87 cm), so its matching sit clips are ~40-46 cm in `sit_clips.json`. Stock cars face +Y: `turn: 90` points
  one along X (parallel to an X-running road). No curb/sidewalk/building props are stocked - use primitive slabs.
- **Couples / families**: Actor Group chat pairs (`2Look_MF` M1+F1) work for adult+child too (DuskStreet trial:
  father + `Kid_F_0004`; a 2-person group with heights > 25 cm apart automatically looks at each other's head;
  members may also set `look_at` explicitly). A couple walking together = two MD walkers on parallel paths 80-100 cm apart with matching speeds (see gaits);
  add `face[]` (works on walkers). There is no talk-while-walking body clip. No teen male avatar exists
  (`Casual_M_0054`-`0056` read as early 20s).
- **Weather**: the spec has no rain. The only stock effect is the legacy particle
  `Template/iClone 7 Template/iClone Template/Particle/Legacy/Environment/Rain.iParticle` (untested here) - describe
  rain in `style` / `prompt` for the AI model instead.

## When a build step complains

- `sit` **advice "clip expects a 35 cm seat but the seat is 43 cm"**: on a primitive seat, set the seat top to the
  clip's height. On a real prop (bench) pick a clip authored near that seat height from
  `examples/catalog/sit_clips.json` (`authored_seat_height_cm`), or accept it: `sit_mode: seat` (default) keeps the
  body on the seat and the feet float by the stated amount; `sit_mode: feet` plants the feet and the hips sink.
  A gap under ~5 cm rarely shows in a medium shot.
- `fit_sitter: could not find ...'s seat/sole surface` or `cannot measure ...: its mesh does not sit on its bind
  skeleton`: that avatar can't be seated automatically - use one whose catalog row says `seat_fit: ok`, or drop
  `sit_on` and place it by hand.
- `could not assign <path> to <walker>`: Motion Director could not pick the path in the viewport. Picks click the
  path's END point: don't end a path under another object or on the same spot as another path.
- **`start_s` on Motion Director walkers**: walkers and wanderers starting at 0 record together in one take and avoid
  each other. A walker with `start_s` > 0 records in a SEPARATE take and does not avoid the others - keep its path
  clear of them. Until `start_s` it plays a standing idle at its path start (start the path off-screen if it should
  enter the shot). `track: follow` accepts several subjects (it frames them together).

## Tips that matter for AI-video previz
- `--previz` also leaves a watchable reel in `<project>/previz/reel/`: `edit.mp4` (every shot's beauty in order),
  `<shot>_passes.mp4` (passes side by side), posters and `index.html` with inline players. Re-make it without
  rendering: `python scripts/reel.py spec.json`.
- Keep people large in frame (35-50 mm, 3-8 m away); tiny figures give poor pose/depth conditioning. Prefer `frame`
  shots (by size) over hand-typed coordinates: they follow the blocking when it changes.
- Over-the-shoulder needs people facing each other; side-by-side sitters -> use `medium_closeup` with `facing: head`.
- Walkers going opposite ways need lanes >= 60-85 cm apart; same-direction walkers need different start times.
- Seated motions are authored for a seat height (32-47 cm): look the clip up in `examples/catalog/sit_clips.json`.
  That height is measured on the catalog's reference avatar; on another person it differs and nothing offline
  predicts it (a 179 cm woman needed 54 cm for a clip authored at 45; `seat_ratio_to_hip` x hip height was off by
  up to 15 cm). On a primitive seat with one sitter add `"fit_height": true` and the build sizes the box to the
  measured need (`seat_resized_to_cm` in the report); otherwise the build prints it (`sit.authored_seat_height_cm`):
  set the seat top to it and rebuild, or for a real prop pick another clip. Then
  build the seat top at that height, and use `sit_on` (do not hand-tune `place.at` z). A mismatch prints `advice`.
  Two people on one bench: Actor Group pairs (`Motion Plus/Actor Group/.../02_Sit/2 People/...`) suit one seat height.
- Natural paced walks: ~85-110 cm/s. Faster looks frantic.
- Motion Director walkers need the user's Reallusion content packs (`scripts/doctor.py` checks). All MD walkers with
  the same `start_s` record in ONE real-time take (`md_walk_paths`); each starts on its own path start. A walker whose
  path ends early idles there for the rest of the take (MD idles include sitting on the ground): give paths similar
  lengths (~1 m/s), or `seconds` to cap the take. Example: `examples/scenes/plaza_crowd.json`.
