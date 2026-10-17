"""Vehicles (or any prop) moving along a path at a speed: cars, bikes, buses in previz.
Tool: drive_path.
# CLAUDE-NOTE (2026-10-17): reuses walk_path's measured mechanics without the walk clips: FollowPath, Path Position
# keyed once per second (RLPy's PathPosition setter never keys; the Modify spin box does) with Linear transitions for an
# even speed, and Modify > Follow Path with the prop's front axis (stock TSL_Roadster: +Y, so 'Y Axis' is the default;
# '-Y Axis' drove it backwards).
"""
import math

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None


def key_plan(length_cm, speed_cm_s, fps, start_frame, step_s=1.0):
    """[(frame, percent)] keys for constant speed: one key per step_s, last key exactly at 100 %."""
    dur = length_cm / max(1e-6, speed_cm_s)
    end = start_frame + int(round(dur * fps))
    n = max(2, int(math.ceil(dur / step_s)))
    return [(start_frame + (end - start_frame) * k // n, 100.0 * k / n) for k in range(n + 1)]


def drive_path(args):
    from tools.icmcp_extra import _path_length, path_position_key, _modify_follow_path, _t
    from tools.objects import find_by_name
    from PySide2 import QtWidgets
    obj = find_by_name(args["object"])
    path = find_by_name(args["path"])
    fps = RLPy.RGlobal.GetFps()
    F = fps.ToFloat() if hasattr(fps, "ToFloat") else 30.0
    start = int(round(float(args.get("start_s", 0)) * F))
    length, pts = _path_length(path)
    speed = float(args.get("speed_cm_s", 800.0))
    plan = key_plan(length, speed, F, start)
    end = plan[-1][0]
    proj_end = fps.GetFrameIndex(RLPy.RGlobal.GetProjectLength())
    if end > proj_end and not args.get("allow_past_end", False):
        raise ValueError(f"the drive ends at frame {end} after the project end ({proj_end}); raise speed_cm_s, start "
                         f"earlier or extend the project")
    old = obj.GetControl("PathPosition")
    if old is not None:
        old.ClearKeys()
    st = obj.FollowPath(path, _t(start))
    if hasattr(st, "IsError") and st.IsError():
        raise RuntimeError("FollowPath failed")
    for f, pct in plan:
        path_position_key({"object": obj.GetName(), "percent": pct, "frame": f})
    pc = obj.GetControl("PathPosition")
    if pc is not None:
        for f, _ in plan:
            pc.SetKeyTransition(_t(f), RLPy.ETransitionType_Linear, 50.0)
    follow = _modify_follow_path(obj, args.get("front_axis", "Y Axis"), frame=start + 1)

    def pos(f):
        RLPy.RGlobal.SetTime(_t(f + 1)); QtWidgets.QApplication.processEvents()
        RLPy.RGlobal.SetTime(_t(f)); QtWidgets.QApplication.processEvents()
        W = obj.WorldTransform(); v = W.T()
        return (v.x, v.y)
    now = RLPy.RGlobal.GetTime()
    try:
        mids = [start + (end - start) * k // 4 for k in range(5)]
        ps = [pos(f) for f in mids]
    finally:
        RLPy.RGlobal.SetTime(now)
    speeds = [math.dist(a, b) / max(1e-6, (fb - fa) / F) for (a, fa), (b, fb) in zip(zip(ps, mids), zip(ps[1:], mids[1:]))]
    end_err = math.dist(ps[-1], pts[-1][:2])
    return {"ok": end_err < 30 and all(abs(s - speed) < 0.25 * speed for s in speeds), "object": obj.GetName(),
            "path_length_cm": round(length, 1), "start_frame": start, "end_frame": end, "keys": len(plan),
            "measured_speed_cm_s": [round(s) for s in speeds], "end_error_cm": round(end_err, 1),
            "follow_path": follow}


def register(registry):
    registry["drive_path"] = {
        "handler": drive_path, "main_thread": True, "timeout": 600,
        "description": "VEHICLE / PROP ALONG A PATH at a constant speed: object (a prop, e.g. a stock car), path (draw_path), "
                       "start_s, speed_cm_s (default 800 = 29 km/h), front_axis for Follow Path (stock cars face +Y: "
                       "'Y Axis' default, measured on TSL_Roadster; other props may differ - try '-Y Axis' / 'X Axis' / "
                       "'-X Axis' if it drives sideways or backwards, and check a render). Verifies measured speed and arrival at the path end.",
        "inputSchema": {"type": "object", "properties": {
            "object": {"type": "string"}, "path": {"type": "string"}, "start_s": {"type": "number"},
            "speed_cm_s": {"type": "number"}, "front_axis": {"type": "string"}, "allow_past_end": {"type": "boolean"}},
            "required": ["object", "path"]}}
