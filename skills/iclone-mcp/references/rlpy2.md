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
