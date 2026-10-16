# RLPy2 - the hidden second API

pybind11 module compiled into iClone.exe (no file on disk; `RLPy2.__file__` is None). 178 classes, ~1860 members, fully
typed signatures. Full dump: ReverseEngineerMCP `targets/iclone8/api/rlpy_live.json` (regenerate with
`targets/iclone8/tools/rlpy_live_dump.py`). Singletons: `RLPy2.<Class>.GetInterface()`.

## Bridge
`h = RLPy2.System.GetInterface().ToHandle(rlpy_obj.GetID())`; `RLPy2.Query.GetInterface().HandleName(h)` round-trips.
`RArrayListHandle` / `RArrayListWString` support `len`, iteration, indexing, `.Add()`.

## Verified (live)
- `System.Undo/Redo` work; `System.RecordUndoStep(True)` flushes lazily recorded UI steps; `Query.CanUndo/CanRedo`.
- `System.SetSilentMode(bool)` suppresses modal message boxes (restore the previous value!).
- `Query.GetObjectHandlesBySuperType(ENodeSuperType.X)` lists any node kind (PARTICLE, NAVMESH, LIGHT_AVATAR, ...).
- `CrowdGenerator`: `BeginMode` -> `SetSpawnRegion(ERangeMode.CreateVolume)` -> `CreateRange(RTransformf(scale,
  RQuaternionf(RVector4f(0,0,0,1)), translation))` (scale unit 200 cm) -> `SetActorPool` -> `SetProperties`
  (nCrowdNumber, nCrowdSpacing) -> `GeneratePlacement` -> `DeployActors` -> `EndMode`. Leaves no volume behind.

## Measured traps
- `CrowdGenerator.AddRangeObject` (PickObject mode) returns RL_SAFE and is ignored; placement then fails and Deploy
  reuses stale placement at the origin.
- `AiPosing.LoadPreset(.rlPose)` returns RL_GPU_HUNG without the AccuPOSE plug-in installed (needs its AI models).
- Avoid `CrowdGenerator.SetMotionLoop` / `SetRandomStartTime`: the equivalent panel checkboxes crashed iClone.

## Not yet explored (candidates for new tools)
MotionDirector / MotionPlanning / MotionMatching, ContentManager (QueryFilePathByContentID, InstallContent),
CharacterCreator, Edit (DeleteSceneObjects / SetName with RecordUndo), MDBehavior, IAiStudio. Probe read-only first.

## Motion Director (mapped 2026-10-16; NOT yet driven live)
**Update (live, later 2026-10-16):** after the user signed in, `RLPy2.MotionDirector.Start(True)` with an avatar
selected triggered the default pack install (an info box "pack is being installed" blocks the progress bar until closed;
WM_CLOSE is safe). Packs land in `Reallusion Templates\Animation\Motion Director\{Neutral,Female,Aged,...}\*.iMD`.
Apply with `RFileIO.LoadFile(iMD)` on the selected avatar -> `GetMainMDName(h)` = "Casual_Walk_M_N", `IsReady()` True.
`RIMotionDirectorManager.BeginCommand(t, [av], opt{bRecord,bAvatar})` + `Start()` ran (IsRunning True, playhead
advanced 4.07 s on timers) but `Stop()`+`EndCommand(t)` left NO new clip and no macro file. Next to try: the MD Controls
per-character Record checkbox / "Record Selected" start mode, then Macro Data > Create Clip.

Earlier status: **no iMD behaviour data installed** (`Reallusion Templates\Animation\Motion Director` empty; the
defaults in `Program Files\...\Resource\ICMotionDirector\DefaultData.ini` are content IDs, e.g. Casual_Walk_Male
`JICba5f71e5440d5abe5`, and `RLPy2.ContentManager.QueryFilePathByContentID` resolves none of them; the user is not
logged in to the content manager). MD needs that content first - ask the user; never download on their account.
Read-only probes (live): `RLPy.RGlobal.GetMotionDirector().IsReady()` False, `RLPy2.MotionDirector.IsReady()` False,
`GetMainMDName(h)` "" , `GetMotionMatchingControlMode(h)` DeviceFreeMode.

API map (signatures from `rlpy_live.json`; manual: `docs/hoodtronik/manual/ic8/50-Animation__Motion-Director__*`):
- Record to timeline (most likely route): `RLPy.RGlobal.GetMotionDirector()` -> `RIMotionDirectorManager`
  `BeginCommand(RTime, ObjectVector, RBeginCommandOption{bAvatar,bMDAcc,bPreserveOneKey,bRecord})`, `Start/Stop`,
  `EndCommand([RTime])`, `EmbedCommand(RTime, ObjectVector)`. The UI equivalent is toolbar "Record Selected" or
  Macro Data > Create Clip. Running MD is a real-time simulation: start, return, poll, stop (never block the thread).
- Modes: `RLPy2.MotionDirector.ActivateAuto{Path,Bound,Data,Follow,Planning,Scripting}Mode(RArrayListHandle)`;
  `GetAutoPathObject(h)` is a getter only - no typed setter for the path target (the UI uses a viewport pick).
- Targeting without a pick: `RLPy2.MotionPlanning` graph - `AutoMoveNodeOption{Avatar, Target, Mode=AutoOnPath|
  AutoInZone, Seconds, Width, TowardEnd, ReleaseWhenArrive, ...}`, `GoToNodeOption{Avatar, Entry, Target}`,
  `CharacterNodeOption{Avatar, MdData, Mode, Speed, Motion, ActionType, Loop}`; `PushGraph`, then
  `ActivateAutoPlanningMode`. `MotionPlanningObject.ConvertJsonToGraph(JSON, SceneInfo)` turns JSON into a graph.
- iMD data: `RLPy2.MDBehavior` (`SetCurrentiMD(str)`, `SetCurrentMode/Speed`, `SetDataSetting(EDataSetting, float)`,
  `SaveiMD`) - no avatar argument (acts on the selection, guess).
- Crowds: `CrowdGenerator.SetAssetMode(ECrowdAssetType.MD)` + `SetMDList([...iMD])`; avoid `SetMotionLoop` /
  `SetRandomStartTime` (crashed via the panel).
Until MD works, `walk_to` (LoadFile chained clips, drift-corrected) and `walk_path` are the locomotion tools.
