# Character-performance implementations: reviewer handoff

This is an implementation follow-up to the manual-based feature review. It is
stacked on draft PR #1 (`codex/previz-reliability`), not deployed to Windows.
Existing `CLAUDE-NOTE` code is unchanged. New registrations are appended in
`main._tool_registry`, with implementations in three separate modules.

## What is implemented

| Tools | Behavior |
| --- | --- |
| `capture_pose`, `set_pose_keys`, `apply_pose` | Read/write explicitly masked FK layer channels. Scene time is converted through the containing clip, including retimed clips. Partial-axis writes preserve unmentioned channels. Absolute means absolute **layer channel value**, not absolute world pose. |
| `save_pose_preset`, `load_pose_preset`, `apply_hand_pose` | Validated named JSON presets and explicit rig-specific finger masks. Hand application permits rotation channels only. No guessed finger names, axes or universal grip shapes. |
| `inspect_clip_transition`, `set_clip_transition` | Read/write fade-in range, curve and strength (0–100) with native readback. `duration_sdk_s` is a literal native RTime duration in seconds; no assumption about retiming compensation. |
| `split_motion_clip`, `trim_motion_clip`, `merge_motion_clips` | Guarded native clip operations with clip-count/duration readback. Trim only shortens; merge requires touching adjacent clips. |
| `hold_motion_pose` | The repository's measured near-hold workaround: split and stretch one source frame. Explicitly **not an exact freeze**. Discards the remaining tail of the source clip; must fit its original interval. |
| `plan_contact`, `apply_contact_interval` | Target/release sequence with full input preflight and reach-key conflict checks. Checks key timestamps around the interval; it does not reconstruct earlier held reach state or other keys’ transition envelopes. Uses an existing, pre-positioned offset target prop. No automatic anchor creation or native keep-current-pose invocation. |
| `check_contact_pose` | Full-precision sampled target-local positional AND quaternion drift. Compensates for target rotation. Optional expected bone-origin separation exposes an initial gap. Restores the paused playhead. |
| `plan_actor_gaze` | Bone-to-bone world/local directions at an explicit time for eyeline planning. Read-only, not an automatic head/eye solver. |
| `inspect_performance_capabilities` | Actual symbol availability and clear native Look-at/Motion Director limitations. Symbol presence is not proof of native compatibility. |
| `validate_shot_list`, `build_shot_list_verified` | Full shot-list preflight before the existing camera builder clears any keys. Requires frame-aligned, nonoverlapping intervals and valid camera vectors/lenses. Switch clearing defaults to false; the existing builder still clears each named camera's transform keys. |
| `schedule_face_performance` | Explicit-time expression beats on existing facial clips. All expression names, weights and clip coverage are checked before writes; editing sessions end in `finally`. |
| `export_previz_bundle` | Verified PNG pass sequences plus frame/checksum manifest in a new folder. Requires output FPS equal to project FPS and inclusive frame counts. Restores camera, playhead and changed render settings. Depth uses unnormalized raw PNG, avoiding inherited per-frame contrast stretching. |
| `inspect_glb`, `export_animation_package` | GLB header/chunk/JSON inspection and an export/checksum metadata wrapper. Caller must explicitly attest constraints were prebaked; the plugin does not claim to bake them. |

There are 23 new tools. They extend existing camera/render/export abilities,
rather than replacing the measured implementations.

## Editing contract

All **scene edit/export** wrappers default to `execute:false`. A dry run returns
its plan and does not save a project or edit animation. Execution requires
`execute:true` and a `backup_path` ending in `.iProject` that does not exist,
under an existing directory. The native save must succeed and produce a
nonempty file before the first edit. Playback must be paused.

A native failure reports the backup location, completed steps and failed step.
There is no claimed automatic rollback. The failed step can itself have
partially changed state. Inspect the scene or restore the backup before retrying.
Pose-preset saving is a separate file operation; it creates a new JSON file and
never overwrites one. These files reside on the Windows host running the plugin.

Layer keys require a containing clip; overlapping clips and uncovered time
points are rejected. Duplicate channel/time writes are rejected after 6000 Hz
time quantization. Limits: 240 pose beats, 200 masked bones, 5000 channel writes
per call. FK layer positions use cm; rotation inputs use degrees, converted to
radians internally. FK offsets do not equal solved world-space poses.

## Examples

The following values are illustrative; use exact names from your scene.

### A partial arm edit

Call `set_pose_keys` first without execution:

```json
{
  "avatar": "Eli",
  "mode": "delta",
  "keys": [
    {"seconds": 2.5, "bones": {"CC_Base_R_Forearm": {"rotation_degrees": {"x": 12}}}}
  ]
}
```

For execution, add `execute:true` and a new backup file such as
`G:/Previz/Backups/arm_edit_001.iProject`. Only that axis of that bone's Layer
control changes; no actor transform keys or reach keys are authored.

### Capture and reuse a preset

1. `capture_pose` with `avatar`, `seconds` and an explicit `bones` list.
2. `save_pose_preset` with `name`, a new `.json` path and the returned `pose`
   data (the complete capture result is accepted as `pose`).
3. `load_pose_preset` returns the named preset. Pass its `pose` to `apply_pose`
   with `avatar`, destination `seconds` and an explicit `bones` mask.
4. For `apply_hand_pose`, pass `finger_bones` and a pose containing exactly those
   bones with rotation channels only. Remove captured position channels first.

The preset stores layer offsets, not retargetable world poses. Start from a
compatible base motion and rig; verify appearance on camera.

### Contact interval

```json
{
  "avatar": "Eli",
  "effector": "right_hand",
  "target_object": "Soldier_Wrist_Grip_Anchor",
  "start_s": 3,
  "end_s": 4.5,
  "transition_s": 0.2,
  "rotation": true
}
```

Use `plan_contact`, then `apply_contact_interval` with execution and backup.
The anchor must already be placed/linked with the intended position and
orientation offset. The existing `link_to_bone` and placement tools provide
those ingredients. Native reach transitions can begin before their key time;
preview both the approach and release. The planner does not prove reachability.

### Verify rotating contact

```json
{
  "source": {"avatar": "Eli", "bone": "CC_Base_R_Hand"},
  "target": {"avatar": "Old Soldier", "bone": "CC_Base_L_Forearm"},
  "seconds": [3, 3.25, 3.5, 3.75, 4],
  "tolerance_cm": 2,
  "tolerance_deg": 10,
  "expected_distance_cm": 5
}
```

`expected_distance_cm` is optional and describes **bone-origin** separation,
not skin contact. Samples between the listed times, mesh penetration and IK
reachability are not certified. Quaternion sign changes are treated as the
same orientation.

### Render a repeatable review bundle

```json
{
  "camera": "Cam_Grab",
  "output_dir": "G:/Previz/Grab_Review_001",
  "start_frame": 72,
  "end_frame": 96,
  "fps": 24,
  "width": 1280,
  "height": 720,
  "passes": ["beauty", "openpose", "depth"]
}
```

Preflight first; execute with a new project backup. The folder must be new.
This first implementation intentionally requires matching project/output FPS,
inclusive counts, numeric contiguous render indices and identical indices across
passes. A native off-by-one or pass-index discrepancy is an error, not a silently
invented mapping. `manifest.json` lists relative files, native render indices,
source-frame/time maps and SHA-256 hashes. Image decoding/dimensions are checked;
this does not prove that every frame is visually useful. Existing pass functions
also perform their measured mid-frame visibility check. There is no video or
contact-sheet encoder in this PR.

## What remains intentionally unimplemented

- Native actor Look-at keys, separate head/body influence tracks and automatic
  eye/head aiming. The verified iClone 8 facial API page lacks `AddHeadKey` and
  `AddEyeKey`; historical documentation is not sufficient to call them blindly.
  `plan_actor_gaze` supplies diagnostic directions. Calibrated head/eye bone
  Layer keys can be authored through `set_pose_keys` if the rig exposes them.
- Native Motion Director recording/control, automatic gait generation, NavMesh,
  surface snapping and native Motion Correction orchestration. Capability
  reporting does not pretend these are callable.
- Automatic contact anchor offsets, exact pose freeze, automatic retargeting and
  surface collision correction.
- Filmback setters, physical f-stop mapping, automatic rack-focus following,
  facial clip creation, blink scheduling and viseme readback.
- Automatic all-constraint flattening, export clip-range/preset selection,
  texture/mesh optimization and full glTF validation. `constraints_prebaked:true`
  is a **caller attestation**, not independent proof. Test export/reimport.

## Host validation

Run:

```text
python -m unittest discover -s tests -v
python -m compileall -q .
python -m ruff check --isolated --select E,F,I --ignore E501 tools/performance.py tools/motion_analysis.py tools/delivery.py tests/performance_support.py tests/test_performance.py tests/test_motion_analysis.py tests/test_delivery.py tests/test_performance_registry.py
```

The 84 host tests include the earlier dispatcher/MCP tests, SDK stand-ins,
actual temporary files and PNG/GLB fixtures, plus full registry reload and an MCP
adapter call. They verify conversion at nonzero clip starts with non-unit speed,
masked edits, preflight failures, readback rejection, partial failures, backup
requirements, quaternion-relative contacts, playhead/settings restoration,
facial editing cleanup, frame mapping and structural export checks.

**No native Windows RLPy execution or visual animation-quality test was performed.**
Stand-ins verify our control flow and math, not SDK correctness. This PR should
remain a draft until the following tests pass on a disposable project.

## Required native reviewer tests

1. Confirm all 23 tools register on server reload. Probe the installed build;
   capture exact FK control names, RFloatControl signatures and supported bones.
2. Confirm `SaveProject(new_path)` creates a usable recovery copy and how it
   affects iClone's current filename. The helper deliberately does not rewrite
   the existing plugin's tracked current-project path. Check later checkpoints.
3. On a clip beginning at nonzero scene time with speed != 1, key one arm axis.
   Inspect the result and prove other axes/bones/actor transforms are unchanged.
4. Apply a captured finger preset on the same rig and base motion. Save/reload;
   verify native layer offsets and update behavior. Do not assume cross-rig poses.
5. Split, trim and merge known clips; verify SDK statuses and actual counts,
   layer preservation and boundaries. Confirm native transition RTime units
   at different speeds before treating `duration_sdk_s` as scene duration.
6. Verify the one-source-frame near-hold's speed/length/loop semantics. Check
   that the tool detects clamping. Confirm the discarded tail is intentional.
7. Use a pre-positioned wrist anchor; author contact/release and verify timing,
   angular offsets and reachability in the shot. Never call methods on the
   object returned by `RReachKey.GetTargetObject()` (known native crash).
8. Compare rotating-contact QA to viewport motion. Confirm solver refresh,
   quaternion conventions and restoration to the exact original playhead.
9. Test facial beats in an existing expression clip; confirm names and weights,
   editing-session cleanup, untouched vocal timing and unchanged playhead.
10. Build a two-shot plan with an invalid second shot; original keys must survive.
    Then test a valid plan, including frame-0 keys, camera creation and switches.
11. Render 24 fps sequences with a 24 fps project. Confirm inclusive counts,
    numeric naming, dimensions, pass-index consistency and restoration after a
    deliberate failure. Native canny calls remain avoided by the existing tool.
12. Export a manually constraint-baked avatar, then reimport into Blender and
    the target AR runtime. Compare bone motion, units, duration and materials.
    Run the Khronos glTF Validator separately for GLB; the built-in inspector is
    deliberately limited.

## Source references

- [RIClip layer controls, time conversion and transitions](https://wiki.reallusion.com/IC8_Python_API:RLPy_RIClip)
- [Skeleton split/merge and experimental operations](https://wiki.reallusion.com/IC8_Python_API:RLPy_RISkeletonComponent)
- [iClone 8 facial API](https://wiki.reallusion.com/IC8_Python_API:RLPy_RIFaceComponent)
- [HIK reach API](https://wiki.reallusion.com/IC8_Python_API:RLPy_RIHikEffectorComponent)
- [Maintaining reach offsets](https://manual.reallusion.com/iClone-8/Content/ENU/8.21/50-Animation/Reach-Target/Maintain-Object-Offset.htm)
- [Clip/key layering](https://manual.reallusion.com/iClone-8/Content/ENU/8.0/51-Animation-Timeline-Editing/Clips_and_Keys.htm)
- [FBX and constraint flattening](https://manual.reallusion.com/iClone-8/Content/ENU/8.0/83-FBX/Exporting_FBX_from_iClone.htm)
- Repository's measured `ICLONE8_AGENT_REFERENCE.md` and existing choreography,
  camera, render and export source. Measured warnings override legacy examples.
