"""Camera moves along a curve, always aimed: crane-ups, arcs, orbits, curved dollies.
Tool: camera_path.
# CLAUDE-NOTE (2026-10-18): iClone's own route (a Path object + Follow Path + camera Look At) is not scriptable - RLPy
# has RICamera.IsLookAtMode but no setter, and Follow Path turns the camera with the path tangent. So the move is keyed
# directly: positions resampled along a Catmull-Rom curve at constant speed (optionally eased), one transform key every
# step_s with LINEAR transitions (dense TCB keys overshoot), each key re-aimed at the target - an avatar target is
# re-measured at every key, so the camera keeps a walking subject in frame.
"""
import math

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None


def _catmull(p0, p1, p2, p3, u):
    u2, u3 = u * u, u * u * u
    return tuple(0.5 * (2 * b + (-a + c) * u + (2 * a - 5 * b + 4 * c - d) * u2 + (-a + 3 * b - 3 * c + d) * u3)
                 for a, b, c, d in zip(p0, p1, p2, p3))


def curve_points(points, n):
    """n points along a Catmull-Rom curve through `points` (passes through every point), spaced by ARC LENGTH."""
    pts = [tuple(float(v) for v in p) for p in points]
    if len(pts) < 2:
        raise ValueError("a camera path needs at least 2 points")
    ext = [tuple(2 * a - b for a, b in zip(pts[0], pts[1]))] + pts + [tuple(2 * a - b for a, b in zip(pts[-1], pts[-2]))]
    dense = []
    for i in range(1, len(ext) - 2):
        for k in range(40):
            dense.append(_catmull(ext[i - 1], ext[i], ext[i + 1], ext[i + 2], k / 40.0))
    dense.append(pts[-1])
    acc = [0.0]
    for a, b in zip(dense, dense[1:]):
        acc.append(acc[-1] + math.dist(a, b))
    total = acc[-1] or 1.0
    out, j = [], 0
    for k in range(n):
        s = total * k / max(1, n - 1)
        while j < len(acc) - 2 and acc[j + 1] < s:
            j += 1
        seg = acc[j + 1] - acc[j] or 1.0
        u = min(1.0, max(0.0, (s - acc[j]) / seg))
        out.append(tuple(a + (b - a) * u for a, b in zip(dense[j], dense[j + 1])))
    return out, total


def orbit_points(center, radius, from_deg, to_deg, height, n=9):
    """Points on a circle around center [x, y]: azimuth 0 = on the -Y side (in front of someone facing -Y), + = CCW
    seen from above (the turn convention)."""
    out = []
    for k in range(n):
        a = math.radians(from_deg + (to_deg - from_deg) * k / (n - 1))
        out.append((center[0] + radius * math.sin(a), center[1] - radius * math.cos(a), float(height)))
    return out


def ease(u, mode):
    if mode == "linear":
        return u
    return u * u * (3 - 2 * u)            # smoothstep: starts and lands softly


def angle_deg(fwd, to):
    n = math.sqrt(sum(v * v for v in to)) or 1.0
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b / n for a, b in zip(fwd, to))))))


def _target_point(tgt):
    from tools.framing import landmarks
    if isinstance(tgt, (list, tuple)):
        return tuple(float(v) for v in tgt[:3])
    av = next((a for a in RLPy.RScene.GetAvatars() if a.GetName() == tgt), None)
    if av is not None:
        h = landmarks(av)
        return tuple(0.5 * (a + b) for a, b in zip(h["head"], h["chest"])) if "chest" in h else h["head"]
    obj = next((o for o in RLPy.RScene.GetProps() if o.GetName() == tgt), None)
    if obj is None:
        raise ValueError(f"camera_path target {tgt!r} is not an avatar, a prop or [x,y,z]")
    W = obj.WorldTransform(); T = W.T()                  # hold W (dangling T(), measured)
    return (T.x, T.y, T.z)


def camera_path(args):
    from PySide2 import QtWidgets
    from tools.icmcp_extra import _camera_named, _look_quaternion
    from tools.lighting import quat_forward
    fps = RLPy.RGlobal.GetFps()
    F = fps.ToFloat() if hasattr(fps, "ToFloat") else 30.0
    if args.get("orbit"):
        o = args["orbit"]
        pts = orbit_points(o["center"], float(o["radius"]), float(o.get("from_deg", 0)), float(o.get("to_deg", 90)),
                           float(o.get("height", 160)), n=max(3, int(abs(float(o.get("to_deg", 90)) - float(o.get("from_deg", 0))) // 15) + 2))
    else:
        pts = args["points"]
    f0, f1 = int(round(float(args["start_s"]) * F)), int(round(float(args["end_s"]) * F))
    if f1 <= f0:
        raise ValueError("end_s must be after start_s")
    step = max(1, int(round(float(args.get("step_s", 0.25)) * F)))
    frames = sorted(set(list(range(f0, f1, step)) + [f1]))
    dense, length = curve_points(pts, 400)
    mode = args.get("timing", "ease")
    cam = _camera_named(args["camera"])
    ctrl = cam.GetControl("Transform")
    if args.get("clear_keys", True):
        ctrl.ClearKeys()
    now = RLPy.RGlobal.GetTime()
    rows = []
    try:
        for i, f in enumerate(frames):
            u = ease((f - f0) / float(f1 - f0), mode)
            P = dense[min(len(dense) - 1, int(round(u * (len(dense) - 1))))]
            RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); QtWidgets.QApplication.processEvents()
            RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f)); QtWidgets.QApplication.processEvents()
            T = _target_point(args["target"])
            tr = RLPy.RTransform(RLPy.RVector3(1, 1, 1), _look_quaternion(list(P), list(T), float(args.get("roll_degrees", 0))),
                                 RLPy.RVector3(*P))
            if i == 0 and f != 0 and args.get("clear_keys", True):
                ctrl.SetValue(fps.IndexedFrameTime(0), tr)       # first key at frame 0 (auto-key rule)
            ctrl.SetValue(fps.IndexedFrameTime(f), tr)
            ctrl.SetKeyTransition(fps.IndexedFrameTime(f), RLPy.ETransitionType_Linear, 50.0)
            rows.append((f, P, T))
        if args.get("lens_mm"):
            cam.SetFocalLength(fps.IndexedFrameTime(0), float(args["lens_mm"]))
            cam.SetFocalLength(fps.IndexedFrameTime(f0), float(args["lens_mm"]))
        # verify between keys: the camera must sit on the curve and still point at the target
        errs, offs = [], []
        for (fa, Pa, _), (fb, Pb, _) in zip(rows, rows[1:]):
            fm = (fa + fb) // 2
            RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fm + 1)); QtWidgets.QApplication.processEvents()
            RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fm)); QtWidgets.QApplication.processEvents()
            W = cam.WorldTransform(); t, r = W.T(), W.R()
            C = (t.x, t.y, t.z)
            T = _target_point(args["target"])
            errs.append(angle_deg(quat_forward(r.x, r.y, r.z, r.w), [b - a for a, b in zip(C, T)]))
            u = (fm - fa) / float(fb - fa)
            offs.append(math.dist(C, [a + (b - a) * u for a, b in zip(Pa, Pb)]))
    finally:
        RLPy.RGlobal.SetTime(now)
    if args.get("make_current", False):
        RLPy.RScene.SetCurrentCamera(cam)
    aim = max(errs) if errs else 0.0
    return {"ok": aim < 3.0, "camera": cam.GetName(), "keys": len(rows), "path_length_cm": round(length, 1),
            "frames": [f0, f1], "max_aim_error_deg": round(aim, 2), "max_off_path_cm": round(max(offs) if offs else 0.0, 1),
            "start": [round(v, 1) for v in rows[0][1]], "end": [round(v, 1) for v in rows[-1][1]]}


def register(registry):
    registry["camera_path"] = {
        "handler": camera_path, "main_thread": True, "timeout": 600,
        "description": "CAMERA MOVE ALONG A CURVE, always aimed: camera (created if missing), points [[x,y,z],...] (a smooth "
                       "curve through every point, constant speed) OR orbit {center [x,y], radius, from_deg, to_deg, height} "
                       "(azimuth 0 = the -Y side, + = counter-clockwise from above), target (avatar = re-aimed at the body "
                       "every key, follows a walker; prop name; or [x,y,z]), start_s, end_s, timing ease (default) | linear, "
                       "step_s (0.25), lens_mm, roll_degrees. Clears the camera's transform keys first (clear_keys). "
                       "Verifies aim and path between keys.",
        "inputSchema": {"type": "object", "properties": {
            "camera": {"type": "string"}, "points": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
            "orbit": {"type": "object"}, "target": {}, "start_s": {"type": "number"}, "end_s": {"type": "number"},
            "timing": {"type": "string", "enum": ["ease", "linear"]}, "step_s": {"type": "number"},
            "lens_mm": {"type": "number"}, "roll_degrees": {"type": "number"}, "clear_keys": {"type": "boolean"},
            "make_current": {"type": "boolean"}},
            "required": ["camera", "target", "start_s", "end_s"]}}
