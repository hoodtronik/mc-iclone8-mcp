"""Tools on RLPy2: iClone's second, undocumented Python API.

# CLAUDE-NOTE (2026-10-16, measured on 8.75.5630.1): RLPy2 is a pybind11 module compiled into iClone.exe (no .py/.pyd on
# disk, __file__ is None), so static stub reading never finds it; a live introspection dump did (hoodtronik/
# ReverseEngineerMCP targets/iclone8/api/rlpy_live.json: 178 classes with typed signatures). RLPy objects bridge to RLPy2
# handles with RLPy2.System.GetInterface().ToHandle(obj.GetID()). Each tool below was verified live before it was added.
"""
import contextlib
import os
import time

import RLPy


def _r2():
    import RLPy2
    return RLPy2


def _pump(n):
    from PySide2 import QtWidgets
    for _ in range(n):
        QtWidgets.QApplication.processEvents()
        time.sleep(0.05)


def _ok(result, step):
    if str(result) != "RL_OK":
        raise RuntimeError(f"{step} returned {result}")


@contextlib.contextmanager
def undo_step(label):
    """Group every edit inside into ONE undo step.
    # CLAUDE-NOTE (measured): edits made through RLPy are NOT recorded for undo on their own (Query.CanUndo stays false);
    # inside RGlobal.BeginAction/EndAction they become a single step that System.Undo/Redo reverts and reapplies."""
    RLPy.RGlobal.BeginAction(label)
    try:
        yield
    finally:
        RLPy.RGlobal.EndAction()


@contextlib.contextmanager
def silent_mode(enabled=True):
    """Suppress iClone's modal message boxes for the duration.
    # CLAUDE-NOTE (measured): with silent mode off, RFileIO.LoadFile on a missing file opens a modal 'Failed to open'
    # box that blocks the main thread (and with it every main-thread MCP call); with it on, the call returns at once.
    # Never make it a global default: it also answers data prompts (save/discard) without asking anyone."""
    if not enabled:
        yield
        return
    system = _r2().System.GetInterface()
    previous = RLPy.RGlobal.GetSilentMode()
    system.SetSilentMode(True)
    try:
        yield
    finally:
        system.SetSilentMode(previous)


def _history(action, args):
    R2 = _r2()
    system, query = R2.System.GetInterface(), R2.Query.GetInterface()
    can, step = (query.CanUndo, system.Undo) if action == "undo" else (query.CanRedo, system.Redo)
    steps = max(1, int(args.get("steps", 1)))
    if action == "undo":
        # CLAUDE-NOTE (measured): iClone records UI/menu undo steps lazily; right after a menu action CanUndo was still
        # false and Undo did nothing, until RecordUndoStep(Immediate=True) flushed the pending step.
        system.RecordUndoStep(True)
    done = 0
    for _ in range(steps):
        if not can():
            break
        _ok(step(), action)
        done += 1
    out = {"ok": done > 0, "action": action, "done": done, "requested": steps,
           "can_undo": query.CanUndo(), "can_redo": query.CanRedo()}
    if done == 0:
        out["note"] = (f"nothing to {action}. Menu/UI actions record undo steps; RLPy edits only do when made through "
                       "python_exec with undo_label.")
    return out


def undo(args):
    return _history("undo", args)


def redo(args):
    return _history("redo", args)


def crowd_scatter(args):
    """Scatter a crowd through RLPy2.CrowdGenerator (no panel, viewport pick, camera or file dialog).
    # CLAUDE-NOTE (measured 2026-10-16): the spawn region must be ERangeMode.CreateVolume + CreateRange(RTransformf).
    # PickObject + AddRangeObject always returned RL_SAFE and was ignored (actors landed at the origin), and then
    # GeneratePlacement returned RL_FAIL while DeployActors still 'succeeded' from stale placement, hence _ok() on every
    # step. Volume scale unit = 200 cm (scale 2 -> actors within +-200 cm). SetMotionLoop/SetRandomStartTime are NOT
    # used: ticking those options crashed iClone through the panel (see generate_crowd)."""
    R2 = _r2()
    actors = [os.path.normpath(p) for p in args["actors"]]
    if not actors:
        raise ValueError("actors must list at least one .iAvatar path")
    for p in actors:
        if not os.path.isfile(p):
            raise FileNotFoundError(p)
    amount = int(args.get("amount", 10))
    spacing = int(args.get("spacing_cm", 90))
    c = args.get("center", {})
    cx, cy, cz = float(c.get("x", 0)), float(c.get("y", 0)), float(c.get("z", 0))
    sz = args.get("size", {"x": 600, "y": 400})
    sx, sy = float(sz["x"]), float(sz["y"])
    cg = R2.CrowdGenerator.GetInterface()
    before = {a.GetName() for a in RLPy.RScene.GetAvatars()}
    with silent_mode(True):
        cg.BeginMode()
        _pump(5)
        try:
            _ok(cg.SetSpawnRegion(R2.ERangeMode.CreateVolume), "SetSpawnRegion")
            volume = R2.RTransformf(R2.RVector3f(sx / 200.0, sy / 200.0, 1.0),
                                    R2.RQuaternionf(R2.RVector4f(0, 0, 0, 1)), R2.RVector3f(cx, cy, cz))
            _ok(cg.CreateRange(volume), "CreateRange")
            _pump(5)
            pool = R2.RArrayListWString()
            for p in actors:
                pool.Add(p)
            _ok(cg.SetActorPool(pool), "SetActorPool")
            props = cg.GetProperties()
            props.nCrowdNumber, props.nCrowdSpacing = amount, spacing
            _ok(cg.SetProperties(props), "SetProperties")
            _ok(cg.GeneratePlacement(), "GeneratePlacement")
            _pump(10)
            _ok(cg.DeployActors(), "DeployActors")
            _pump(30)
        finally:
            cg.EndMode()
    new = [a for a in RLPy.RScene.GetAvatars() if a.GetName() not in before]
    inside = 0
    for a in new:
        T = a.WorldTransform().T()
        inside += abs(T.x - cx) <= sx / 2 + spacing and abs(T.y - cy) <= sy / 2 + spacing
    return {"ok": len(new) == amount, "deployed": len(new), "requested": amount, "inside_region": inside,
            "region": {"center": [cx, cy, cz], "size": [sx, sy]}, "actors": [a.GetName() for a in new][:100]}


def list_scene_nodes(args):
    """List scene nodes by RLPy2 super type, including kinds RLPy cannot enumerate (particles, navmesh, crowd volumes...)."""
    R2 = _r2()
    names = list(R2.ENodeSuperType.__members__)
    st = args.get("super_type")
    query = R2.Query.GetInterface()
    if not st:
        counts = {}
        for n in names:
            if n == "NONE":
                continue
            k = len(query.GetObjectHandlesBySuperType(getattr(R2.ENodeSuperType, n)))
            if k:
                counts[n] = k
        return {"counts": counts, "super_types": names}
    if st not in names:
        raise ValueError(f"unknown super_type {st!r}; one of {names}")
    handles = query.GetObjectHandlesBySuperType(getattr(R2.ENodeSuperType, st))
    return {"super_type": st, "count": len(handles), "names": [query.HandleName(h) for h in handles][:500]}


def register(registry):
    def reg(name, fn, desc, props, req, main_thread=True):
        registry[name] = {"handler": fn, "main_thread": main_thread, "description": desc,
                          "inputSchema": {"type": "object", "properties": props, "required": req}}
    steps = {"steps": {"type": "integer", "description": "how many steps (default 1)"}}
    reg("undo", undo, "Undo the last iClone undo step(s) via RLPy2. Menu/UI actions record steps; RLPy edits only when made through python_exec with undo_label. Returns can_undo/can_redo.", steps, [])
    reg("redo", redo, "Redo iClone undo step(s) via RLPy2. Returns can_undo/can_redo.", steps, [])
    reg("crowd_scatter", crowd_scatter, "CROWD via the native CrowdGenerator API (fast; no panel, camera or dialogs): scatter `amount` light actors from `actors` (.iAvatar paths) in a `size` {x,y} cm region at `center` {x,y,z}. spacing_cm default 90. No motion pool: use generate_crowd for motions. Proof: deployed count and how many stand in the region.",
        {"actors": {"type": "array", "items": {"type": "string"}}, "amount": {"type": "integer"}, "spacing_cm": {"type": "integer"},
         "center": {"type": "object"}, "size": {"type": "object"}}, ["actors"])
    reg("list_scene_nodes", list_scene_nodes, "List scene nodes by RLPy2 super type (CHARACTER, PROP, LIGHT, CAMERA, PARTICLE, POPCORNFX, NAVMESH, CROWDGEN_ROOT, MDPROP, LIGHT_AVATAR (crowd actors), ...). No super_type = non-zero counts per type.",
        {"super_type": {"type": "string"}}, [])
