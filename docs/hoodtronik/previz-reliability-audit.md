# Previz reliability audit and additions

Audited `hoodtronik/mc-iclone8-mcp` main at `dc25262b3bc497be8f475adc266e7d7f68fefe73`.
The retired `hoodtronik/iCloneMCP` repository explicitly points here.

## Findings and changes

| Finding | Change | Practical effect |
| --- | --- | --- |
| `motion_track` clears existing motion before checking the entire replacement list. A missing later file can leave the character partly rebuilt. | New `safe_motion_track` preflights every file, exact avatar identity, nested field, numeric value and minimum clip length before calling the existing loader. | Invalid plans fail before deleting or loading clips. Dry run and append are the defaults. |
| An HTTP command can time out while queued, then execute on a later timer tick. Retrying can duplicate edits. | Dispatcher cancels commands that have not started, with a lock protecting the start/cancel race. | A cancelled queued command cannot mutate the scene later. Already running operations report uncertain completion explicitly. |
| Dispatcher falls back to running RLPy on the calling worker if not initialized; a main-thread call after initialization waits for its own timer. | Worker fallback refused; owner-thread calls execute directly; timer startup requires the Python main thread. | Avoids wrong-thread SDK calls and owner-thread deadlock. |
| Tools pump Qt events during sampling/rendering, which can re-enter the timer and start another queued edit. | Dispatcher callback rejects nested timer entry while busy. | HTTP edits remain serialized even when a tool processes UI events. |
| Existing `bone_track` gives useful positional samples, but changes the playhead and leaves interpretation to the agent. | New `check_contact` validates inputs, preflights bones, samples through the measured existing tool and restores the playhead in `finally`. | Reports planted-foot drift or translation relative to a moving character, tolerance failures and the worst sample time. |
| The baseline handler test sends a name its own fixture schema does not declare. | Fix the test fixture schema. | Tests exercise the actual strict argument contract rather than failing against it. |

`CLAUDE-NOTE` code and the original choreography tools are preserved. New tools live in `tools/previz.py`; `main.py` registers them after existing tools. The original `motion_track` still has its original behavior: agents should prefer `safe_motion_track`.

## Motion planning

First preflight; no animation is edited:

```json
{"avatar":"Actor","clips":[{"path":"F:/iCLONE/Motions/Walk.iMotion","start_s":0,"speed":1,"length_s":2}]}
```

Call `safe_motion_track` again with `execute:true` to append, or with both `execute:true` and `replace:true` to rebuild the motion layer. The same full preflight runs on execution. Paths are checked on the Windows host running iClone, and are normalized like the existing loader. `length_s` denotes scene seconds; `length_s * speed` must reach one project frame because the existing measured notes document silent rejection of shorter clip lengths. Input plans allow up to 100 clips and must be nonempty.

Preflight does **not** load the asset to prove format compatibility. File changes between preflight and loading, SDK load failures, overlapping clips and rejected speed/length adjustments can still cause partial edits. Execution delegates to the original loader, including its SDK status handling and clip selection. Save a separate project backup before replacement. This is input validation, not a transactional animation system.

## Contact measurement

Pause the timeline and obtain exact avatar/bone names with scene and skin-bone tools. Use `check_contact` only across an interval when contact is intended to remain held:

```json
{"source":{"avatar":"Actor","bone":"CC_Base_L_Foot"},"seconds":[0,0.25,0.5,0.75,1],"tolerance_cm":2}
```

For a hand held against another character, add a target:

```json
{"source":{"avatar":"Actor","bone":"CC_Base_R_Hand"},"target":{"avatar":"Partner","bone":"CC_Base_L_Forearm"},"seconds":[1,1.25,1.5,1.75,2],"tolerance_cm":2}
```

Without a target, drift is the source's world displacement from the first sample. With a target, drift is the change in the source-minus-target translation vector from the first sample, so shared translation is discounted. `distance_cm` still exposes an initial gap between bone origins. `passed` means only that sampled drift stays within tolerance.

This is positional QA, not IK, retargeting or animation repair. Bone origins are not mesh contact surfaces. It does not compensate for target rotation or prove initial contact, finger pose, orientation, penetration, or behavior between samples. The existing sampler rounds positions to 0.1 cm. Use dense times for short contacts, a suitable tolerance and viewport inspection. Limits: 2–240 increasing nonnegative times within the timeline end marker. The existing sampler's solver-refresh nudge is reused; native evaluation needs live confirmation. Playback must be paused.

## Timeout recovery

- **Before execution:** the queued job is cancelled and makes no changes. A later request can be retried.
- **After execution starts:** Python cannot safely interrupt the native operation. The timeout says it may still complete. Wait and inspect scene state before retrying an edit.
- A completed job racing its timeout returns its actual result instead of inventing a failure.
- SDK code must enter through the dispatcher. Uninitialized worker calls are refused.

## Validation and Windows smoke test

Host checks: `python -m unittest discover -s tests -v` and `python -m compileall -q .`. Tests use SDK stand-ins, including real Python threads; they cover cancelled work, started timeouts, owner-thread dispatch, missing later assets, malformed numeric inputs, dry-run defaults, moving targets, sliding feet, sampling failures and playhead restoration. They do not run native RLPy or prove visual animation quality.

Before merging/deploying, use a disposable Windows iClone project:

1. Load this branch through the existing installation route and restart the server. Confirm `safe_motion_track` and `check_contact` appear in `tools/list`.
2. On an avatar with existing clips, execute a replacement list with a missing second path. Confirm the call fails and the original clip list is unchanged.
3. Preflight real motion assets, then append a known motion and confirm speed, scene duration and transform/reach preservation. Test replacement only on a saved copy.
4. Sample a planted foot and a known sliding segment. Confirm reported drift against viewport behavior and that the exact original playhead is restored. Repeat for two translating characters and inspect the initial distance.
5. Confirm startup accepts iClone's embedded Python main thread and ordinary HTTP tool calls execute through the timer. A modal dialog can delay the timer: a queued timeout must not perform a delayed edit after the dialog closes.

## Remaining animation bottlenecks

The MCP has motion placement, reach, bone inspection and renders already. The weak point is giving the agent dependable feedback and recoverable operations. This change helps that loop; it does not make the agent a skilled animator. Further work should use live iClone measurements for clip-load/setter verification and rotation-aware contacts before attempting automatic correction. Existing native reach crash warnings and project checkpoints remain intact; those checkpoints save the current project in place rather than creating a separate recovery copy.

API references: [RGlobal time/playback](https://wiki.reallusion.com/IC_Python_API:RLPy_RGlobal), [iClone 8 custom FPS](https://wiki.reallusion.com/IC_8_Python_API:Dealing_With_Custom_FPS). The repository's `ICLONE8_AGENT_REFERENCE.md` supplies measured 6000-ticks-per-second and clip-length behavior; legacy API examples should not override those iClone 8 measurements.
