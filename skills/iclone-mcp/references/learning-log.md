# Learning log

Newest first. Each entry: what happened, the rule it produced, evidence. Promote durable rules into SKILL.md /
gotchas.md / recipes.md; keep this file as the history.

## 2026-10-17 - AI-model output sizes (spec `render`)
- Spec `render: {width, height, fps}` -> set_render_output. A ParkReal build set 832x480 yet exported 1920x1080 (the
  size was reset in between; not reproducible on demand). set_render_output now also writes the Render panel's
  Width/Height spins, and previz_export takes width/height and enforces them right before rendering (verified: reset
  to 1920 first -> export 832x480).
- OpenPose gizmo_scale 12 suits 1920 wide; at 832 the joints were 40 px blobs over the face -> default scales with
  the output width. (A check-sheet 'pose mismatch' was an illusion: tile = frame 300 by pixel diff 0.16.)

## 2026-10-17 - worked example: evening_street.json
- frame_shot diverged on a two-shot of people 4.9 m apart (camera 1.1 km away, aim 537 m underground): the aim
  correction scaled by subject span / projected span, which grows as width pushes the camera back. Now the pinhole
  scale d * (film/2) / lens, plus clamps; regression test.
- stop_at_end first cut AT arrival: mid-stride -> feet-together idle = 38.5 cm foot jump in one frame (clip
  SetTransitionType/Range changed the frames before the cut but did not blend the switch). Now cut where MD has
  settled (lowest hip speed + foot spread within 2 s after arrival): worst jump 8.9 cm. Regression sweep of all 5
  example specs passed (builds 22 s - 9 min).
- A tracking camera passed right by a seated bystander (her head filled the foreground): blocked() also rejects a
  camera within 60 cm of anyone else's head/chest.
- Auto On Path is random travel ALONG a path: Leo reached the end at 8 s and walked back. stop_at_end (default) crops
  the take at arrival and appends a stock idle with heading carry-over. Builder takes now span the whole scene (a
  shorter take made Leo snap back to his start when the clip ended).

## 2026-10-17 - acting beats: perform_sequence (+ an outage)
- A clip loaded after another continues the root POSITION but not its HEADING: two Right_Turn_090 both ended at -98 deg.
  perform_sequence keys the avatar at each boundary (rotate about the hip by the yaw gap, put the hip back) -> two
  turns = 175 deg. Standing Pack 1 clips are ~10.9 s with the move mid-clip; trim='auto' cuts the idle tail (the head
  cannot be trimmed). HD Idle_M is 41 s; beats past the project end clamp to it -> the tool refuses.
- HD Motion Plus clips on non-HD characters pop a modal "corrective expressions" notice that froze the main thread:
  load_motion_clip now loads in silent mode (gated on real iClone; offline fakes lack GetSilentMode).
- OUTAGE: a syntax error (raw newline inside a string) in a tool module killed the server on hot reload; recovery needed
  `launch_iclone.py --restart`, which then found no MCP because this shell lacked MC_ICLONE8_MCP_DIR (autostart fell
  back to another machine's G:\ path). Launcher now passes the checkout explicitly. ALWAYS `ast.parse` / pytest before
  hot_reload.

## 2026-10-17 - hand props: hold_prop
- RLPy's "none" link alignment is `ELinkObjectAlignType__None` (double underscore; fight_tools had the wrong name).
- LinkTo(__None) keeps the object's CURRENT WORLD offset to the bone; the keyed world pose must be evaluated first
  (playhead nudge) or the link captures the old pose (prop ended 344 cm away). Keys set after an aligned link are
  ignored. Scale read right after create_primitive was stale (1,1,1) -> phone became a 1 m box; use the creation scale.
- Result: phone 9.3 cm from the wrist, constant through the clip, lying in the palm (render).

## 2026-10-17 - vehicles: drive_path
- Car along a 28 m road at 700 cm/s: measured 699-700 cm/s, end error 0 (per-second Path Position keys, Linear).
- Modify > Follow Path checkbox/axis are DISABLED while the playhead is outside the object's path range (car starting
  at frame 60, checked at frame 0 -> click ignored, car drove backwards). `_modify_follow_path(frame=...)` now moves the
  playhead into the range (also fixes late-starting walk_path walkers). Stock TSL_Roadster front = +Y ('Y Axis').

## 2026-10-17 - integration: street_scene.json
- Every builder feature in one spec builds in 2m20s (props, seated pair + faces, 3-person chat, 2 path walkers + 3
  wanderers in one MD take, establishing / couple / chat / tracking shots), QA clean but one walker pop.
- Path pick tolerance is generous: sidewalks 90 cm apart (46 px in the overview) - clicks on W picked E. Picks now go
  through a temporary camera 4.5 m above the path point (`_close_pick`), user camera restored, camera deleted after.
- load_motion_verified fixed for calm clips; `allow_unchanged` for idempotent re-runs.

## 2026-10-17 - group conversations
- Actor Group members (3Stand_MMF G1_M1/M2/F1) loaded at one origin stayed there facing -Y: clips carry no layout.
- `group_conversation`: ring facing the centre; live: heads within 4-16 deg of the centre, hips 128 cm apart, reads as
  a natural three-way chat. Re-running with the same clips hit load_motion_clip's "no change" guard -> allow_unchanged.

## 2026-10-17 - real props: ParkReal scene
- Stock props (Props/Samples: Classic Park Bench_01, bins, railings, cars, buildings) via `set[].asset` in specs.
- A real bench's bounds top is the backrest (87.5 cm); seat found from mesh vertices: highest dense z band in the front
  60% of the depth = 42.9 cm. Low-poly props: slats only have vertices at their ends (do not filter the centre).
- load_motion_verified rejected a calm seated idle (0.26 cm motion in 1 s): proof is now pose before vs after load.
- Close-up of one sitter had the other's head in half the frame -> frame_shot tries +-20/40 deg until faces are clear.
- ParkReal builds in 21 s: real bench + bin + car, Actor Group pair seated, faces, wide/medium/close-up by size.

## 2026-10-17 - facial performance: face_performance
- .iTalk via LoadFile (avatar selected, playhead) -> face-track clip; expression weights live (Awkward_F: Eye_Wide 0.75,
  Brow_Raise_Inner 0.68); body clip unchanged. 74 stock Digital Soul clips by mood (Pleased/Excited/Tender/Unhappy/
  Scared/Sad). Clips also drive Head_Turn / Eyeball_Look - may fight look-at; verify with a close-up (frame_shot).
- iClone embeds Python 3.8: no str.removesuffix (caught before shipping).

## 2026-10-17 - long main-thread tools need longer dispatch timeouts
- previz_export of an 8 s shot failed with "iClone operation timed out": main-thread tools ran under dispatch.run's
  fixed 120 s; the render kept going inside iClone. Tools now declare `timeout` (main.py sets previz_export 7200 s,
  render_control_pass 3600 s, filmstrip/motion_qa 900 s ...). If a call times out, iClone may STILL be busy - check
  with a trivial python_exec before the next call.

## 2026-10-16 - wandering crowd: md_wander
- Manual: Auto In Zone works on ANY prop (no NavMesh needed). Dialog has pickAutoBoundObject / setAutoSetting /
  getCurrentAvatarName (exact id -> name map, replacing the path-pick guessing).
- 2nd wanderer's pick hit the 1st wanderer: transform reads right after place_object were stale -> avoid the known
  start positions, try 4 pick pixels.
- setAutoSetting with a multi-key map half-applied and changed an unset key; one key per call works (read back).
- 4 wanderers / 12 s: slide 0.08-0.15, 0 pops, 100% inside the zone; short idles -> 4-11 m travelled.
- A zone slab in the scene made path walkers detour 2.5 m -> builder records wanderers first and hides the zone.
- Separate takes (wanderers, then walkers) walked through each other -> `md_crowd` records both in ONE take and hides
  zones before Start. `setAvatarsPicked` costs ~0.37 s (panel refresh): id lookups now cached (11 people: 4 s/check).
- 15-min timeouts were verification: 11 avatars x 600 frames sampled one by one; now one batched pass, every 3rd
  frame. Same-length re-takes looked like 'no new clip' -> hip fingerprint before/after. 11 people: 1m54s total.
- Diagnose slow MD calls with `tools.motion_director.TRACE` (python_exec) while the call runs.
- CrowdAvoidanceAgentRadius 39 -> 50 (setMatchingManagerSetting honoured): QA flags 4 -> 1, but two wanderers still
  walked through each other (filmstrip). MD takes are random -> md_crowd re-records while hips < 30 cm (retakes).
  Plaza: 4 -> 3 -> 1 collision runs over 3 takes (5m55s build).
- Tracking shot (`frame_shot track=follow`) in the crowd: passers-by filled the frame; per-key sight-line check with
  +-20/40 deg alternatives + 0.5 s keys + camera 60 cm above eye level kept the subject visible in every tile.

## 2026-10-16 - moving crowd: md_walk_paths (plaza test)
- Multi-walker MD take: only the last walker recorded -> `RScene.SelectObject` replaces the selection;
  `SelectObjects(list)` works. One take for 5 walkers = one walker's wall time.
- All five then followed the LAST path: blind tries of MD dialog avatar ids assigned the path to other avatars.
  Ids rise in load order = scene order of MD-enabled avatars; learn id owners from which path changed; final
  recheck re-picks drifted assignments. MD walks an avatar to its path first -> place each on its path start.
- Result: 5 walkers, slide 0.08-0.12, path deviation 20-59 cm, motion_qa clean. Early finishers idle (one sat down).
- Research (subagent): CrowdGenerator iMD mode (SetAssetMode(MD) + SetMDList) and NavMesh/zone crowds exist, but no
  scripting API creates a NavMesh, walkway width or volumes -> UI automation needed (next).

## 2026-10-16 - cameras by shot size: frame_shot
- AOV is horizontal on 36 mm film (35 mm -> 54.43 deg). Pinhole model matched renders (full shot within 0.03; close
  range offset ~0.09 = ~1.5 cm pivot/mesh slack -> chin keep-in constraint >= 0.25 above the bottom edge).
- Landmarks: head top + chin rigidly skinned from the bind mesh (chin filter: face only 4-6.6 cm in front of
  CC_Base_Head on Business_F; a 6 cm filter picked the nose). Bone reads after SetTime were NOT stale (re-tested).
- Mistakes fixed via renders: constraints must be max()-ed every iteration (else they oscillate away); close sizes
  centre on heads, not hands; OTS needs on-screen fg head radius in its occlusion test; one-frame solves lose
  moving subjects -> sample the shot (`through_frame`); body facing hides turned faces -> `facing: head`.
- Park bench edit now: wide, full->medium push, OTS on her, MCU on him - all solved from the bodies.

## 2026-10-16 - seating: fit_sitter + sit-clip catalog
- Hidden-seat renders: the stock male Sit Talk sank ~7 cm into the 46 cm seat (the opaque box hid it) with feet 8 cm
  up; bone heights could not predict it (clearance thigh-joint->seat differed 5 cm between clips).
- No deformed-vertex API: `RIMesh.GetVertices` = bind pose. `GetBoneTPosePosition` returned POSED world positions on
  one avatar (unusable). `bone.BasisTransform()` = parent-relative rest pose; composing it from RL_BoneRoot gives bind
  frames; quaternion convention verified (child.T = parent.T + parent.R * basis.T, 0.1 cm).
- `fit_sitter`: rigid lower-body skinning + pelvis/thigh blend; calibrated +2.2 cm bias from eye-level renders on two
  bodies (soles exact). Perspective trap: judge seat contact with the camera AT seat height, not from above.
- `scripts/sit_catalog.py` measured 57 stock sit clips -> `examples/catalog/sit_clips.json` (SitG ground clips read
  ~0 cm = sanity check). Found Actor Group 2Sit/3Sit pairs; park bench now uses 2Sit_Chat_G1 M+F on a 42 cm seat.
- `load_motion_clip` false failure: replacing a clip with a same-length one left the clip list unchanged -> now falls
  back to a pose fingerprint.

## 2026-10-16 - incident: scratch scene saved over ParkBench.iProject
- A scratch scene opened with LoadFile(default project) kept the MCP's tracked ParkBench path; filmstrip's checkpoint
  saved the scratch scene over the real project. Rebuilt from park_bench.py (reproducible scripts saved the day).
- Fix 6b270ba: iClone's live project path wins; default project = no path = checkpoint skipped. Regression test.
- Rule: give every scratch scene its own saved path first. Keep scenes reproducible as scripts.
- Built scripts/iclone_eyes.py: UI Automation reads popup text/buttons and presses by name (posted keys can't reach
  some Qt modals); verified on a blocking 'Reminder' modal.

## 2026-10-16 - Motion Director works (animation mastery, iteration 3)
- User signed in; `MotionDirector.Start(True)` installed the default iMD packs (info box blocked the progress bar).
- Recording: BeginCommand(bRecord) only made macros; toolbar 'Record Selected' + Start/Stop made clips.
- Path assignment needed the QML panel + the dock's Q_INVOKABLEs (QJSEngine bridge) + a posted viewport pick.
- New tools: `md_walk_path` (one call: iMD, mode, pick, record, verify) and `qml_inspect`. Live: male 10.4 s and female
  11.1 s on an 8.5 m curved path, slide 0.0-0.1, 0 pops, <= 40 cm off the path.

## 2026-10-16 - control passes (previz iteration 2)
- OpenPose skeletons were squashed toward the frame centre vs the beauty render: the pass uses the viewport aspect
  (1571x1168) and stretches to 1920x1080. Proved by projecting bones both ways (ankles 801 predicted vs 810 measured
  with viewport aspect; 885 with render aspect). Fix: resize the viewport to the render aspect during the pass.
- Second render of the same frames hung on an overwrite modal -> tool clears its previous frames first.
- Folder output paths wrote files beside the folder (prefix semantics) -> mapped to folder\<pass>.png.
- Then the first `previz_export` showed skeletons 1.25x too TALL vs beauty: the BEAUTY sequence was the distorted one.
  All RenderImageSequence* calls use the viewport aspect (beauty sequence vs RenderImage: mean diff 24 -> 0.19 with
  the viewport matched). Fix moved to every pass + RenderVideo (video: inferred, unmeasured). Earlier "depth is
  aligned" was wrong (both were distorted the same way).
- New `previz_export`: per-pass folders, MP4s via iClone's own Bin64\ffmpeg.exe, manifest, check sheet.

## 2026-10-16 - motion QA: why the walkers glided (previz polish, iteration 1)
- Goal set by the user: the MCP exists to make previz that DRIVES AI VIDEO -> motion and silhouettes must read right.
- Built `filmstrip` (rendered contact sheet, focus crop on an avatar) and `motion_qa` (foot slide / pops / overlaps).
- motion_qa on the park scene: every walker slide_ratio ~0.97 (gliding), 4 m root pops at each clip boundary,
  opposite walkers passing through each other (hips 16 cm apart).
- Root cause after elimination (6 avatars incl. Motion Dummy, 8 clips, HIK effectors, Foot Contact checkbox, playback
  vs scrub - all ruled out): `RFileIO.LoadMotion` glues feet to the floor. `LoadFile` on the selected avatar: slide
  0.04, stride 58 cm, toe lift 8 cm; the backflip flips. All tools now load through `common.load_motion_clip`.
- LoadFile clips chain (continue from the previous end) -> `walk_to` lost its boundary keys; next clip at end+1;
  stale transform keys from re-runs cleared. Live: 1400 cm walk, 4 clips, hip error 2 cm, 0 pops.
- `aim_camera` now creates a camera for an unknown `name`.
- Saved the iClone 8 manual locally (`docs/hoodtronik/manual/`, gitignored): grep it before guessing UI behaviour.

## 2026-10-16 - park-bench scene (first full scene built purely through MCP)
- `new_project(save_current=false)` blocked on the discard prompt -> fresh scene via silent `LoadFile(default project)`.
  Answered the live prompt out-of-process (Tab to "No", Space) after reading it from a capture.
- Second avatar load replaced the selected first one -> clear selection before every avatar load.
- Late walkers stood inside the bench until their start -> fixed in `walk_to` (wait at `from`), mc-iclone8-mcp d0124a2.
- Walks past the project end silently produced 12-clip garbage (playhead clamps) -> `walk_to` now refuses.
- Hot reload forgot the project path -> `current_project_path` asks `RApplication.GetCurrentProjectPath()`.
- `set_material_color` keys at the current frame (path faded white -> grey mid-shot) -> colour at frame 0.
- `.iSky` via `load_object` errors; `RFileIO.LoadFile` works. Black render background = no sky loaded.
- Sit Talk hip heights (F 56 / M 49 cm) -> lift male 7 cm on a 46 cm seat. Clip lengths 19.65 / 23.3 s -> chain.
- TTS (David/Zira) + `load_vocal` gives correct lip-sync; verified by jaw rotation spread.
- Foot bones read pinned while walking (WRONG CAUSE, see the motion-QA entry: LoadMotion glued the feet); 1 s sampling aliases the walk cycle.
- Evidence: ReverseEngineerMCP `targets/iclone8/evidence.jsonl`, renders in `Documents\Reallusion\ParkBench\renders`.

## 2026-10-16 - RLPy2 discovery and first tools
- Live dump found RLPy2 (pybind11, inside iClone.exe). Undo/redo, silent mode, crowd_scatter, list_scene_nodes added
  (mc-iclone8-mcp 25188da). AccuPOSE API blocked without the plug-in.
- In-process dialog tools freeze with the main thread -> out-of-process `retk` window tools.
- `hot_reload.py` never reloaded `main.py`; `importlib.reload` cannot re-find it (file-path module) -> re-exec spec.
- Launch popups (registration nag, late post-crash prompt) now auto-answered.
