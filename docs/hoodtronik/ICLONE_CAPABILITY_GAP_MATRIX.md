# iClone Capability Gap Matrix

This is the living backlog for capabilities that matter to the creator's actual iClone previz workflow.

Read ICLONE_AUTOMATION_ARCHAEOLOGY_STRATEGY.md before editing this file.

## Status vocabulary

- SUPPORTED: current MCP tool exists and is runtime-proven on a documented build.
- PARTIAL: some required behavior exists but the workflow is incomplete.
- RLPY-CANDIDATE: installed/official RLPy appears to expose it; wrapper/runtime proof still needed.
- QT-CANDIDATE: likely accessible through a stable in-process Qt/UI command; proof needed.
- NATIVE-CANDIDATE: public/local Python surfaces appear insufficient; targeted native archaeology may be justified.
- BLOCKED: no safe route currently known.
- NEEDS-CREATOR: technical options exist but creator workflow/taste must choose.
- UNKNOWN: not audited yet.

## Priority

- P0: blocks active creator work.
- P1: high-frequency/high-leverage previz automation.
- P2: valuable but not currently blocking.
- P3: exploratory/nice-to-have.

## Matrix

| Capability | Human UI? | Current MCP | Official/local RLPy | Qt route | Native route | Tier target | Priority | Evidence / next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Travel along a path (position keys), follow/release | Yes | SUPPORTED (`path_position_key`; `follow_path`/`release_path` upstream) | `FollowPath` works; `PathPosition.SetValue` → Success but no key; `AddKey(RFloatKey)` CRASHES | Modify > Attribute > Path section spin box (`qtDoubleSpinBox` next to label "Path Position (%)") creates the key | n/a | QT | P1 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): 50 % @ frame 60 → key 1→2, prop at quarter/half circle. Found via the docs notebook + manual (values 0–100 %, 200 = two loops). |
| Create a new path | Yes | SUPPORTED (`draw_path` free-form through ground points; template `.iPath` + `set_transform` also works) | `RFileIO.LoadFile(.iPath)`; RIPath has no point API | `Create > Path` click mode driven by projected clicks posted to the viewport HWND | n/a | QT/WIN32 (posted messages) | P1 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): 4-point route, start/end within 2.3 / 3.1 cm. Ground plane only (z from clicks = grid). |
| Edit path curve/control points | Yes | NO | Public API documented as missing | UNKNOWN | UNKNOWN | QT or INTERNAL | P1 | Audit exact UI operation and scene/state delta. |
| Avatar Look At (head/eyes/body track a prop, camera or another avatar's bone; timed release) | Yes | SUPPORTED (`set_look_at`) | Local stub only (not on the wiki): `RISkeletonComponent.GetLookAtComponent().AddLookAtKey`, 2 SWIG overloads | n/a | n/a | OBSERVED | P1 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): CC_Base_Head world-rotation delta 27-61 deg + RenderImage proof. Weight datablocks are not a usable readback. See agent reference §8 *Look At*. |
| Load a project / new project in-session | Yes | SUPPORTED (`load_project`, `new_project`) | `RFileIO.LoadProject` (stub); no `NewProject` symbol | `menu_action "File > New Project"` (proven) | n/a | OBSERVED / QT | P1 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): load 2.2 s, new 0.7 s, NEITHER raises a save prompt on a dirty scene -> tools save the tracked project first; new_project clears the tracked path. |
| Undo / redo from the agent | Yes | NO | `RGlobal.Undo/Redo/BeginAction/EndAction` present in stub | `Edit > Undo` menu action runs | UNKNOWN | BLOCKED | P2 | Measured 2026-10-07: neither `RGlobal.Undo()` nor the menu Undo reverted an API transform write (with or without BeginAction/EndAction); an earlier SaveProject+BeginAction+Undo+Redo sequence on an API-built untitled scene CRASHED iClone (exact call unattributed). Do not expose. |
| Timeline range and project length | Yes | SUPPORTED (`set_timeline_range`) | `RGlobal.SetProjectLength`, `SetStartTime/SetEndTime`, `SetPreviewStartTime/EndTime` (stub) | n/a | n/a | OBSERVED | P1 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): all five set and read back exactly; length clamps end/preview_end; shrinking keeps keys beyond the end. |
| Clip surgery (break / merge / mirror / delete) | Yes | SUPPORTED (`edit_clip`, checkpointed) | `RISkeletonComponent.BreakClip/MergeClips/MirrorClip/DeleteClip` (Experimental, official) | n/a | n/a | OFFICIAL | P2 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): 1→2→1→0 clips, mirror flips pose AND world X. `BakeFkToIk` still UNVERIFIED. |
| Audio onto an object's sound track + mixed audio export | Yes | SUPPORTED (`load_audio`, `render_audio`) | `RAudio.LoadAudioToObject`, `RGlobal.RenderAudio` (stub) | n/a | n/a | OBSERVED | P2 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): rendered window non-silent after load. The API's float return is NOT a success flag (same value for a missing file) → tool proves by before/after render. Loading onto a CAMERA crashed iClone twice → refused by the tool. |
| Project FPS set (24 for film) | Yes | SUPPORTED (`set_project_fps`) | Confirmed absent: no `SetFps`/`SetProjectFps` in the installed stub | 'Project' QDockWidget → `qtFpsComboBox` (setCurrentIndex + activated) | n/a | QT | P2 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): `RGlobal.GetFps()` 60 → 24, project length 1800 → 720 frames, no prompt. First Qt-tier capability. |
| Motion Director (walk/run/interact commands) | Yes | NO (stub getter only) | `RIMotionDirectorManager.Start/Stop/BeginCommand(t, objects, RBeginCommandOption)/EndCommand/EmbedCommand` = a session-RECORD model, not "walk to X" | n/a | n/a | OBSERVED | P3 | Read 2026-10-07; superseded for blocking by `walk_to`. |
| Blocking move: walk from A to B | Yes (Motion Director / path) | SUPPORTED (`walk_to`) | Composition of proven calls: Step Transform keys + root-motion `Walk.iMotion` (iClone 7 set) calibrated per avatar, chained with boundary keys, last clip trimmed via SetLength | n/a | n/a | OFFICIAL/OBSERVED | P1 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): 566 cm at 120 cm/s → 2.9 cm error, 1000 cm over 3 clips → 2.3 cm. `RIClip.SetLoopCount` does not exist on 8.75. See reference §8 *Walking*. |

| External motion conversion (Mixamo / Rokoko / Xsens FBX, BVH → .rlMotion) | Yes (File > Import > Convert External Motion, auto-detected profile) | SUPPORTED (`convert_external_motion`) | `ConvertFbxFileToRLMotion` FAILS on skinless Mixamo FBX; `LoadFbxFile` imports the rig as a prop | Native "Open" dialog typed via SendInput (HTTP thread) + Qt "Motion Import Settings" driven in-process | n/a | QT + WIN32 | P1 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): fight_idle.fbx → .rlMotion, plays on an ActorCore avatar. Ilyas pointed at the UI feature. |

| Camera / spotlight follows a moving target (Look At over a frame range) | Yes (Modify > Look At > Pick Target, Set Free) | SUPPORTED (`track_target`, baked rotation keys) | `RICamera.IsLookAtMode` read-only; no setter | Look At section needs a viewport pick | n/a | OBSERVED (bake) | P1 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): aim error ≤ 0.02° over 300 frames, head centred in render. |

| Multi-camera cuts (Switcher track) that actually drive playback/renders | Yes (Timeline Project > Switcher + toolbar camera list "Switch") | SUPPORTED (`camera_cuts`; `build_shot_list` fixed) | `AddSwitchCameraKey` / `GetSwitchCameraFrameIndexs` / `ClearSwitchCameraKeys` | toolbar combo `qtCameraSwitchAction` → "Switch" | n/a | OFFICIAL + QT | P1 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): without Switch mode renders ignored the cuts; with it, live camera and render follow them. |

## Ranking (audit of 2026-10-07)

Scored with the strategy's formula (creator value x frequency x leverage / cost) after grepping the installed `RLPy.py`
against the 112-tool registry. Done: **Avatar Look At** (chosen first: every dialogue/blocking shot needs eye-lines, nothing
else in the MCP could produce them, and the stub already had the call). Next in order: in-session load project / undo,
timeline range + project length, clip surgery, audio, then the true gaps (path authoring, project FPS) which need the Qt tier.

## Audit queue

Add creator-important features here before deep work. Do not mark a feature as missing from RLPy until installed RLPy.py, official docs, samples, and runtime have been checked.

Candidate categories to audit:
- Motion Layer editing
- Reach / IK authoring
- clip creation / split / merge / reposition / transition editing
- animation curve editing
- timeline track editing
- camera creation / switch tracks / deeper camera controls
- Motion Director
- Crowd Simulation
- physics / constraints
- facial editing
- render settings / passes
- retargeting / motion conversion
- Content Manager operations

These are audit categories, not claims that the APIs are missing.
