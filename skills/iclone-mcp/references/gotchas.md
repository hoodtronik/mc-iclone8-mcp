# Measured gotchas (iClone 8.75.5630.1)

Each line: rule -> reason (source). REF = docs/hoodtronik/ICLONE8_AGENT_REFERENCE.md (section 8 overrides the rest of
it), GAP = docs/hoodtronik/ICLONE_CAPABILITY_GAP_MATRIX.md. Correct entries here when a measurement contradicts them.

## Units / time / coordinates
- `RTime.FromValue(ticks)`, 6000 ticks/s; `RTime(int)` raises; `RLPy.IndexedFrameTime` is module-level. (timeline.py, REF 1.4)
- `RGlobal.GetFps()` returns an `RFps` object, not an int. (REF 1.4)
- Heading 0 faces -Y, +h is CCW (90 faces +X): heading = atan2(dx, -dy). (icmcp_extra.py walk_to)
- Viewport angle of view is horizontal; cameras look down local -Z. (icmcp_extra.py world_to_viewport)
- Primitives pivot at their base (box = 100 cm cube): use bounds centres for markers. (REF, park-bench 2026-10-16)
- `GetClipLength()` is scene seconds (already speed-adjusted); don't divide by speed again. (REF)

## Transforms & keys
- Key transforms at frame 0 first: iClone auto-keys at the current frame, so later-first keys drift/pop. (icmcp_extra.py place_object)
- Write hold keys with explicit values; identical keys merge on save. (REF)
- `RMatrix3.FromEulerAngle` returns `[RMatrix3, x, y, z]`; take `[0]`. (common.py)
- Hold the RTransform in a variable before `.T()`: chained `WorldTransform().T()` is a dangling SWIG ref. (icmcp_extra.py, camera.py)
- After clip/reach edits move the playhead elsewhere + processEvents before sampling (first read stale by 51 cm). (fight_tools.py)
- Motion clips, transform keys and reach keys are separate layers; touch only the one you mean. (fight_tools.py)
- A freshly loaded avatar already has a frame-0 key at the origin. (walk_to fix d0124a2)
- Undo: RLPy edits need `python_exec undo_label`; never call `RGlobal.Undo()` directly (an undo/redo chain crashed). Use the `undo`/`redo` tools. (rlpy2_tools.py, GAP)

## Motion clips & walking
- `LoadMotion` can "succeed" with nothing moving: verify bone displacement (`load_motion_verified`). (REF)
- `RIClip.SetLength` is clip time: `SetLength(L * speed)`; sub-frame clips silently rejected. (fight_tools.py)
- Outside any clip: first frame before it, BIND POSE after it. Cover the shot (chain clips) or park in an idle. (REF)
- `MirrorClip` mirrors in world X incl. root; re-place the actor. Both halves of `BreakClip` report speed 1.0. (icmcp_extra.py)
- `SetLength` past a root-motion clip's natural length holds the pose instead of travelling: chain clips (~440 cm each), next clip at previous end +1, NO boundary keys (LoadFile clips continue; a key double-offsets). Distance is sub-linear in speed: calibrate. (walk_to)
- Walks must end inside the project length (playhead clamps; walk_to refuses). (walk_to)
- `RFileIO.LoadMotion(path, t, av)` glues the feet to the floor on every avatar/clip (that was the old "foot bones read pinned" / "Walk_2Loop barely moves legs" note). `LoadFile` at the playhead with the avatar selected plays clips correctly; bone reads are then trustworthy. (common.load_motion_clip, 2026-10-16)
- The iClone 8 `*_2Loop` / `*_1Start` template walks are in-place (no root travel); iClone 7 `Walk.iMotion` (CC MixMove) carries ~440 cm per clip at ~85 cm/s. (motion audition 2026-10-16)
- `walk_to` re-runs must clear the old walk's transform keys after `start` (now automatic). (walk_to)
- Walk clips curve slightly (CC male ~1.1 deg: 22 cm sideways over 11 m); `walk_to` measures the drift during calibration and pre-rotates (`drift_correction_deg`). (walk_to)
- `RIClip.SetLoopCount` does not exist (upstream `set_clip_loop_count` raises). (REF)
- Clear selection before loading an `.iAvatar`, or it REPLACES the selected avatar. (REF, park-bench)
- Reach targets must be objects (link a small prop to a bone); arm reach ~55-60 cm. Never call methods on `RReachKey.GetTargetObject()` (hard crash). (fight_tools.py)
- External FBX motion: use the Convert External Motion UI route (`convert_external_motion`). (icmcp_extra.py)

## Cameras
- Multi-camera cuts drive view/render only with the toolbar `qtCameraSwitchAction` on "Switch" (`camera_cuts`). (icmcp_extra.py)
- No camera look-at setter: rotation keys are baked per frame (`track_target`, aim error <= 0.02 deg). (icmcp_extra.py)
- `aim_camera name=X` errors if X doesn't exist; omit `name` to create a Linear Camera. (park-bench)
- A posted drag outside a creation mode flies the camera (~2 km): re-check after failed UI runs. (REF)
- The Preview Camera cannot be animated: use a scene camera. (upstream skill)

## Materials / props
- `set_material_color` keys at the current frame: set at frame 0. (park-bench)
- Video plates: Create > Billboard = 100x100 cm plate in local Y/Z; video on diffuse (`video_plate`). (icmcp_extra.py)
- Bright colours (>0.5) render near-white under default lights. (park-bench)

## Face / voice
- Look-at: 2-arg overload for props/cameras, 5-arg for bones; targeting an avatar object looks at its feet, so target `CC_Base_Head` (`set_look_at` bone mode). Weights don't read back: prove with head rotation + render. (icmcp_extra.py)
- Never put audio on a camera (`LoadAudioToObject` on a camera crashed iClone twice). Its float return is not a success flag. (icmcp_extra.py)
- `load_vocal` with a WAV gives lip-sync; prove with `CC_Base_JawRoot` rotation spread. (park-bench)

## Paths
- `PathPosition.SetValue` is a no-op; `AddKey(RFloatKey)` on it crashes: use `path_position_key` (Modify spin box). UI 0-100 % = stored 0..1. (icmcp_extra.py)
- First world read after a path key can be ~1e17 garbage: nudge time and re-read. (icmcp_extra.py)
- No path point API: `.iPath` templates or `draw_path`. Hide props/avatars while clicking (clicks raycast onto them); keep paths flat; follow axis "-Y Axis"; clear old path keys before switching paths. (icmcp_extra.py)

## Crowd
- Native: `crowd_scatter` (CreateVolume, 200 cm scale unit). PickObject/AddRangeObject is ignored. (rlpy2_tools.py)
- Panel route (`generate_crowd`): make the region prop before opening the panel; one hover-click to pick; type spin values with key events (`setValue` is ignored); Generate Placement before every Deploy. (icmcp_extra.py)
- NEVER enable Loop / Random Start (checkboxes or API) with a motion in the pool: crash. Repeat via LoopCount. (icmcp_extra.py)
- A "restart crowd generation" modal after Deploy blocks the bridge; OK also closes the panel. (icmcp_extra.py)

## Rendering
- Range renders need end > start (equal pops a modal); single frames: `render_snapshot`. (icmcp_extra.py)
- Raw RLPy render paths need backslashes (forward slashes "succeed" and write nothing); MCP tools convert. (icmcp_extra.py)
- OpenPose defaults render transparent: COCO format + gizmo settings (`render_control_pass`). Canny defaults crash: derive from beauty. 8-bit depth is useless: 16-bit = half-float EXR. (icmcp_extra.py)
- Project fps and Render-panel fps are separate (`set_project_fps` vs `set_render_output`). (icmcp_extra.py)
- Black background in renders = no sky loaded (`LoadFile(.iSky)`). (park-bench)

## UI automation
- Project fps only via the Project dock combo (no RLPy setter). (icmcp_extra.py)
- Timeline clip menu: in-process QMouseEvents with global position, then QContextMenuEvent; never a Win32 right-click. (icmcp_extra.py)
- Never send physical input that can reach another app (it once typed into the user's browser); post to iClone HWNDs. Private `WinDLL("user32")`. (native_ui.py)
- Menus that may open a modal: `QTimer.singleShot(200, action.trigger)`. (REF)
- Viewport grabs can be stale; prefer `render_snapshot` as proof. (icmcp_extra.py)

## Dialogs / popups
- Qt dialogs keep the bridge serviced; native modals (Open, Import Settings) and blocking message boxes freeze main-thread tools: use out-of-process `retk` window tools. (native_ui.py, 2026-10-16)
- Auto-answer only harmless dialogs (AccuPOSE serial nag, equal-time render warning, registration nag). Never data prompts. (dialog_watch.py)
- `new_project` blocks on "discard?": use silent `LoadFile(default project)`. (park-bench)
- A posted right-click in the viewport opens a menu that blocks the main thread: post Esc to it. (REF)

## Crashes / checkpoints / files
- Checkpoint-save before risky tools (reach, look-at, edit_clip, renders) - automatic, needs a project path. Never checkpoint an empty scene. (mcp_handler.py)
- After a crash: "Unsaved project data" -> Cancel; "discarded... save?" -> No (launcher handles it). (launch_iclone.py)
- `SaveProject()` needs a path; never save over DefProject. `LoadProject` / New Project discard changes silently via API. (project.py, common.py)
- Growing project length does not move `end`: always pass `end`. (icmcp_extra.py set_timeline_range)
- Big projects finish loading ~60 s after the MCP is healthy. (launch_iclone.py)
- Unknown tool arguments are rejected (an ignored `name` once answered for the wrong avatar). (mcp_handler.py)

## Known broken / open
- Upstream `set_path_position` (no-op), `set_clip_loop_count` (raises). Path point editing: no API.
- Motion Director via UI: not automatable; RLPy2 `MotionDirector` exists - unexplored (see rlpy2.md).
- `AiPosing.LoadPreset` needs the AccuPOSE plug-in. `BakeFkToIk`: unverified.

## Control passes for AI video (2026-10-16)
- EVERY `RenderImageSequence*` call (beauty, depth, normal, OpenPose) projects with the VIEWPORT aspect (here
  1571x1168) and stretches to the render size (1920x1080) -> squashed/stretched frames that disagree with `RenderImage`
  (single frame, correct) and with each other. `render_control_pass` / `previz_export` resize the viewport to the render
  aspect for the pass and restore it (`_viewport_matching_render_aspect`); raw RLPy sequence calls must do the same.
  Verify with the OpenPose-over-beauty tile of `previz_export`'s check sheet (zoom on a walker).
- Re-rendering over existing frames pops a blocking "Found N files that will be overwritten" modal (posted keys don't
  reach it; WM_CLOSE cancels). `render_control_pass` deletes its own previous frames first.
- Render paths are file PREFIXES: a folder path writes `<parent>\<folder>_00240.png`. The tool maps a folder to
  `folder\<pass>.png`.
- Depth includes the ground gradient (people read faint against the near ground).
- For AI conditioning keep subjects big: a wide 40 mm shot at 11.5 m gave ~25 % frame-height people and 1-2 px
  skeletons; 35 mm at 7.6 m + `gizmo_scale` 12 reads well.

## QML panels (2026-10-16)
- MD Controls, MotionLIVE, Video Mocap etc. are QML in QQuickWindows (invisible to QWidget searches). `qml_inspect`
  dumps a panel; `tools/qml_ui.py` finds items by text/tooltip and clicks with a synthetic QMouseEvent (invokeMethod
  'clicked' does nothing). Panels rebuild after actions: re-find items every time.
- A C++ dialog behind a QML panel often has Q_INVOKABLEs: list them with metaObject (methodType 0 = method) and call
  through `QtQml.QJSEngine().newQObject(dock)` + `evaluate("JSON.stringify(dlg.fn(...))")` (PySide2 lacks Q_RETURN_ARG).

