# From a story beat to a scene spec

How to turn a script ("two friends argue on a bench while the city rushes by") into a `scripts/build_scene.py` spec
that builds believable previz for AI video. Format reference: `SCENE_SPEC.md`. Full example: `examples/scenes/street_scene.json`.

## 1. Read the beat for five things

| In the script | Spec block | Tool behind it |
|---|---|---|
| where (park, street, plaza, room) | `set[]`: real props via `asset` (bench, bin, car, building) + primitive ground/zones | `load_object`, `create_primitive` |
| who sits | `cast[]` + `motion.clip` (a sit clip) + `sit_on` | `fit_sitter` |
| who talks together standing | `groups[]` (2-3 people, Actor Group clips) | `group_conversation` |
| who does a sequence (waits, turns, steps, talks) | `cast[].actions` | `perform_sequence` |
| who walks somewhere | `paths[]` + `walkers[].path` (natural) or `from`/`to` (straight) | `md_walk_paths` / `walk_to` |
| background people milling | `wander[]` on a zone prop | `md_wander` (all MD people go into one `md_crowd` take) |
| cars / buses passing | `paths[]` road + `vehicles[]` | `drive_path` |
| feelings on faces | `face[]` (mood: Pleased, Excited, Tender, Unhappy, Scared, Sad) | `face_performance` |
| things in hands | `cast[].hold` (phone, cup, book) | `hold_prop` |
| what we see, shot by shot | `shots[]` with `frame` (size + subjects) | `frame_shot` |

## 2. Pick clips by what the body does

- **Sitting**: look the clip up in `examples/catalog/sit_clips.json` - each clip wants a seat height (32-47 cm). For two
  people on one bench use an Actor Group pair (`.../02_Sit/2 People/2Sit_Chat_G1_M1` + `_F1`) and a seat between their
  heights. Real benches work (the seat is found in the mesh).
- **Standing chat**: `Motion Plus/Actor Group/ActorGroup Series - Social Actions/01_Preset/01_Stand/{2,3} People/...`.
- **Solo idles / talks**: `Motion Plus/1.Acting/HD Idle_M`, `HD Talk_M`, `HD Think_M`, `HD Emote_M` (`_F` variants).
  These are long (Idle 41 s): give `seconds`.
- **Turns / steps**: `Motion/Standing Pack 1/Right_Turn_090`, `Left_Turn_045`, `Step_Forward_Right_Small`... (~10.9 s
  each, the move mid-clip; `trim: auto` cuts the tail).
- **Walking**: Motion Director (`imd: male|female`) on a `paths[]` path - the most natural option.
- Faces: `list_expressions` shows the moods; the clip also moves head/eyes, so check close-ups.

## 3. Numbers that keep it believable

- Walking pace ~85-110 cm/s; Motion Director paths ~1 m/s - make paths of similar length (early finishers idle, may sit).
- Opposite walkers >= 60-85 cm apart; give wander zones room (spacing 150-170 cm per person).
- People in a standing chat: the tool rings them (2 people ~110 cm apart).
- Cars ~500-1000 cm/s (18-36 km/h); stock cars face +Y (default).
- Every action must END before `length_s` (tools refuse beats past the project end).

## 4. Shots for AI video

- Keep subjects large: prefer `medium_wide`, `medium`, `medium_closeup`, `closeup` over `wide` for the people that matter.
- One establishing shot may use a hand-placed `position`/`target`; everything else: `frame` by size.
- Faces turned away? `facing: head`. Walkers? `track: follow` (crowds: `track_step_s: 0.5`, `height_offset_cm: 60`).
- Over-the-shoulder needs people FACING each other; side-by-side sitters -> `medium_closeup` per person instead.
- Run `--previz` for beauty + OpenPose + depth (+ `previz.passes` for normal/canny) per shot.

## 5. Worked example

Beat: *"Evening street. Mia waits on a bench, scrolling her phone. Leo walks up the sidewalk, they chat. Behind them
two colleagues talk by a car; people drift past."*

- set: ground, `Classic Park Bench_01`, a `TSL_Roadster_Standard`, a zone slab behind the sidewalk.
- Mia: `cast[]` sitting (`2Sit_Chat_G1_F1`), `sit_on` the bench, `hold` phone, `face` Amused.
- Leo: `walkers[]` on a short path ending beside the bench (Motion Director), or `cast[].actions` (idle -> turn ->
  step -> talk) if he must stop at an exact spot.
- colleagues: `groups[]` with `2Stand_Chat_Direction_G1_M1` / `_F1` next to the car.
- passers-by: `wander[]` on the zone (3-6 people) + 1-2 sidewalk `walkers[]`.
- shots: establishing wide (hand-placed), `medium_wide` of Mia, `track: follow` on Leo's walk, `medium` two-shot at
  the bench, `closeup` of Mia with `facing: head`.

Build, read `qa/filmstrip.png` and the `flags`, fix the spec (not the scene), rebuild, then `--previz`.
