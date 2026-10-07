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
| Inspect/follow/release existing paths and set path position/offset | Yes | PARTIAL | Partial | UNKNOWN | UNKNOWN | OFFICIAL/OBSERVED | P1 | Existing MCP covers existing paths but not authoring. |
| Create a new path | Yes | NO | Public API documented as missing | UNKNOWN | UNKNOWN | QT or INTERNAL | P1 | Start with Qt action discovery; native archaeology only if Qt route fails. |
| Edit path curve/control points | Yes | NO | Public API documented as missing | UNKNOWN | UNKNOWN | QT or INTERNAL | P1 | Audit exact UI operation and scene/state delta. |
| Avatar Look At (head/eyes/body track a prop, camera or another avatar's bone; timed release) | Yes | SUPPORTED (`set_look_at`) | Local stub only (not on the wiki): `RISkeletonComponent.GetLookAtComponent().AddLookAtKey`, 2 SWIG overloads | n/a | n/a | OBSERVED | P1 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): CC_Base_Head world-rotation delta 27-61 deg + RenderImage proof. Weight datablocks are not a usable readback. See agent reference §8 *Look At*. |
| Load a project / new project in-session | Yes | SUPPORTED (`load_project`, `new_project`) | `RFileIO.LoadProject` (stub); no `NewProject` symbol | `menu_action "File > New Project"` (proven) | n/a | OBSERVED / QT | P1 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): load 2.2 s, new 0.7 s, NEITHER raises a save prompt on a dirty scene -> tools save the tracked project first; new_project clears the tracked path. |
| Undo / redo from the agent | Yes | NO | `RGlobal.Undo/Redo/BeginAction/EndAction` present in stub | `Edit > Undo` menu action runs | UNKNOWN | BLOCKED | P2 | Measured 2026-10-07: neither `RGlobal.Undo()` nor the menu Undo reverted an API transform write (with or without BeginAction/EndAction); an earlier SaveProject+BeginAction+Undo+Redo sequence on an API-built untitled scene CRASHED iClone (exact call unattributed). Do not expose. |
| Timeline range and project length | Yes | SUPPORTED (`set_timeline_range`) | `RGlobal.SetProjectLength`, `SetStartTime/SetEndTime`, `SetPreviewStartTime/EndTime` (stub) | n/a | n/a | OBSERVED | P1 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): all five set and read back exactly; length clamps end/preview_end; shrinking keeps keys beyond the end. |
| Clip surgery (break / merge / mirror / delete) | Yes | SUPPORTED (`edit_clip`, checkpointed) | `RISkeletonComponent.BreakClip/MergeClips/MirrorClip/DeleteClip` (Experimental, official) | n/a | n/a | OFFICIAL | P2 | PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): 1→2→1→0 clips, mirror flips pose AND world X. `BakeFkToIk` still UNVERIFIED. |
| Audio onto the scene / an object | Yes | PARTIAL (`load_vocal` = lipsync only) | Present in stub: `RAudio.CreateAudioObject`, `RAudio.LoadAudioToObject` | n/a | n/a | OBSERVED | P2 | Symbol grep 2026-10-07, runtime UNVERIFIED. |
| Project FPS set (24 for film) | Yes | NO | Confirmed absent: no `SetFps`/`SetProjectFps` in the installed stub (grep 2026-10-07) | Project Settings dialog (unproven) | UNKNOWN | QT | P2 | Workaround today: a 24 fps template project; `set_render_output` only sets the Render panel fps. |
| Motion Director (walk/run/interact commands) | Yes | NO (stub getter only) | Present in stub: `RIMotionDirectorManager.Start/Stop/BeginCommand/EndCommand/EmbedCommand` | n/a | n/a | OBSERVED | P3 | Signatures unknown; exploratory. |

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
