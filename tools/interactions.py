"""Two-person contact via reach IK (no stock interaction clips exist): handshake.
Tool: handshake.
# CLAUDE-NOTE (2026-10-17): the stock library has no handshake/hug clips (searched), so contact is made with HIK reach
# keys (verified 2026-09-26: AddReachKey(effector, RReachKey), targets must be OBJECTS, arm reach ~55-60 cm). Two tiny
# target props meet between the pair (offset 3 cm toward each person so palms meet instead of overlapping) and shake.
"""
import math

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None


def meet_points(chest_a, chest_b, hip_z_a, hip_z_b, palm_gap_cm=6.0, lift_cm=18.0):
    """Target points for A's and B's right hands: midway between the chests, at the mean hip height + lift_cm,
    pulled palm_gap/2 toward each person."""
    mx, my = (chest_a[0] + chest_b[0]) / 2.0, (chest_a[1] + chest_b[1]) / 2.0
    z = (hip_z_a + hip_z_b) / 2.0 + lift_cm
    dx, dy = chest_b[0] - chest_a[0], chest_b[1] - chest_a[1]
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    h = palm_gap_cm / 2.0
    return (mx - ux * h, my - uy * h, z), (mx + ux * h, my + uy * h, z), n


def shake_keys(t0, seconds, amp_cm=3.5, period_s=0.5):
    """[(t, dz)] for an up-down shake: rest, then alternating +amp/-amp every half period, back to rest at the end."""
    keys, t, sign = [(t0, 0.0)], t0 + period_s / 2.0, 1
    while t < t0 + seconds - period_s / 2.0:
        keys.append((round(t, 3), sign * amp_cm))
        sign = -sign
        t += period_s / 2.0
    keys.append((round(t0 + seconds, 3), 0.0))
    return keys


def handshake(args):
    from tools.icmcp_extra import _avatar, _t
    from tools.fight_tools import reach_key, _secs_time
    from tools.framing import landmarks
    from tools.project import create_primitive
    from tools.objects import find_by_name
    a, b = _avatar(args["a"]), _avatar(args["b"])
    at, dur = float(args.get("at_s", 1.0)), float(args.get("seconds", 2.0))
    fps = RLPy.RGlobal.GetFps()
    f = int(round(at * fps.ToFloat()))
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
    La, Lb = landmarks(a), landmarks(b)
    pa, pb, dist = meet_points(La["chest"], Lb["chest"], La["hip"][2], Lb["hip"][2])
    if dist > float(args.get("max_gap_cm", 100.0)):
        raise ValueError(f"{a.GetName()} and {b.GetName()} are {dist:.0f} cm apart (chest to chest); a handshake needs "
                         f"<= ~100 cm (arm reach ~55-60 cm each) - move them closer and facing each other")
    targets = []
    for who, p in ((a, pa), (b, pb)):
        name = f"_hs_{who.GetName()}"
        try:
            RLPy.RScene.RemoveObject(find_by_name(name))
        except Exception:
            pass
        create_primitive({"type": "box", "name": name, "scale": {"x": 0.02, "y": 0.02, "z": 0.02}})
        o = find_by_name(name)
        ctrl = o.GetControl("Transform")
        ctrl.ClearKeys()
        S = RLPy.RVector3(0.02, 0.02, 0.02)
        Q = RLPy.RQuaternion(RLPy.RVector4(0, 0, 0, 1))
        ctrl.SetValue(_t(0), RLPy.RTransform(S, Q, RLPy.RVector3(*p)))
        if args.get("shake", True):
            for t, dz in shake_keys(at, dur):
                ctrl.SetValue(_secs_time(t), RLPy.RTransform(S, Q, RLPy.RVector3(p[0], p[1], p[2] + dz)))
        o.SetVisible(RLPy.RTime.FromValue(0), False)
        targets.append(name)
    ramp = float(args.get("ramp_s", 0.5))
    for who, tname in ((a, targets[0]), (b, targets[1])):
        reach_key({"avatar": who.GetName(), "effector": "right_hand", "seconds": max(0.0, at - ramp), "key_type": "release",
                   "transition_s": 0.1})
        reach_key({"avatar": who.GetName(), "effector": "right_hand", "seconds": at, "key_type": "target",
                   "target_object": tname, "transition_s": ramp})
        reach_key({"avatar": who.GetName(), "effector": "right_hand", "seconds": at + dur, "key_type": "release",
                   "transition_s": ramp})
    # verify: right hands together mid-hold
    fm = int(round((at + dur / 2.0) * fps.ToFloat()))
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fm + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fm))
    ha = landmarks(a)["r_hand"]; hb = landmarks(b)["r_hand"]
    gap = math.dist(ha, hb)
    return {"ok": gap < 20.0, "chest_gap_cm": round(dist, 1), "hands_gap_mid_hold_cm": round(gap, 1),
            "targets": targets, "hold_s": [at, at + dur]}


def register(registry):
    registry["handshake"] = {
        "handler": handshake, "main_thread": True, "checkpoint": True,
        "description": "HANDSHAKE via reach IK: a and b (standing, facing each other, chests <= ~100 cm apart) shake right "
                       "hands from at_s for `seconds` (hidden target props + reach keys with ramp_s in/out, optional "
                       "up-down shake). Verifies the hands meet (gap mid-hold < 20 cm).",
        "inputSchema": {"type": "object", "properties": {
            "a": {"type": "string"}, "b": {"type": "string"}, "at_s": {"type": "number"}, "seconds": {"type": "number"},
            "ramp_s": {"type": "number"}, "shake": {"type": "boolean"}, "max_gap_cm": {"type": "number"}},
            "required": ["a", "b"]}}
