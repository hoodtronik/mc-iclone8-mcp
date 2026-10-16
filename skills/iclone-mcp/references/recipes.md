# Recipes (all measured live; reproduce before trusting a variation)

Full worked example: ReverseEngineerMCP `targets/iclone8/scenes/park_bench.py` (`all` rebuilds the scene end to end).
Call tools from Python with `targets/iclone8/tools/icall.py` (`call(tool, args)`).

## Fresh project
```python
call("python_exec", {"code": "import RLPy\nRLPy.RFileIO.LoadFile(RLPy.RApplication.GetDefaultProjectPath())", "silent": True})
call("set_project_fps", {"fps": 30})            # new projects default to 60
call("set_timeline_range", {"project_length": 25, "start": 0, "end": 25, "unit": "seconds"})
call("save_project", {"path": r"...\Scene.iProject"})   # checkpoint tools need a path
```

## Props from primitives (bench example)
Box = 100 cm cube, pivot bottom-centre. `create_primitive {type: box, name, position {x,y,z=underside}, scale {size/100}}`,
then `set_timeline {frame: 0}` and `set_material_color {name, color {r,g,b 0..1}}`. Bench used: seat 170x48x6 at z 40
(top 46 cm), two back slats 170x4x12 at y 24 (z 54, 72), posts 6x5x50, legs 6x6x40 at x +-76, y +-19.
Ground: 40000x40000x2 at z -2 reaches the horizon. Light colours (>0.5) render near-white under default lights.

## Seated conversation
1. Clear selection, `load_object` the avatar (`Reallusion Templates\Actor\Character\Business\*.iAvatar`).
2. `load_motion_verified` `Animation\Motion\1.Human Male\Perform\Sit Talk.rlMotion` (female: `2.Human Female\...`).
   Root stays at floor level; hip ~56 cm (female) / ~49 cm (male) -> on a 46 cm seat lift the male 7 cm.
3. Chain a second copy with `motion_track` at the first clip's end (female 19.65 s, male 23.3 s).
4. `place_object` (position + rotation_degrees z +-20 to face each other). Front is -Y.
5. `set_look_at` each at the other (bone mode, head_weight 0.8, body_weight 0.2) - needs a saved project path.

## Dialog with lip-sync
1. Generate lines with Windows TTS (`scenes/make_dialog.ps1`: David male / Zira female, Rate 1).
2. `load_vocal {avatar_name, audio_path, clip_name, start_frame}` per line; schedule with ~0.5 s gaps.
3. Verify: `CC_Base_JawRoot` local rotation spread > 0.01 while speaking, ~0 while listening.

## Passers-by
`walk_to {avatar, from, to, start_frame, speed_cm_s: 125, motion: <CC Walk.iMotion>, idle_after: false}`.
Start/end off-screen (a 40 mm lens at ~11 m sees ~+-300 cm of a path 3 m in front of the subject). Stagger starts;
every walk must end before the project end. Expect hip error < 30 cm.

## Crowd (no motions)
`crowd_scatter {actors: [.iAvatar...], amount, center {x,y,z}, size {x,y}, spacing_cm}` - ActorCore Crowd actors in
`Reallusion Templates\Actor\Character\ActorCore Crowd`. They list as `LIGHT_AVATAR`. Motion pools: `generate_crowd`.

## Sky
`python_exec silent=true`: `RLPy.RScene.ClearSelectObjects(); RLPy.RFileIO.LoadFile(<.iSky>)`.
Skies: `Template\iClone 7 Template\iClone Template\Sky\` ("Clear Day 04" = blue sky; "Clear Day 02" = desert hills).

## Camera + check renders
`aim_camera {position, target, focal_length_mm, make_current: true, hold: true}` (omit `name` to create one).
`render_snapshot {output_path, frame}` at 3-5 frames and LOOK at each image.

## Undoable scripted edit
`python_exec {code, undo_label: "Move bench"}` then `undo` / `redo`.
