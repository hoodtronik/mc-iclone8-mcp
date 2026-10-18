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


def wipe_keys(center, side, t0, seconds, width_cm=40.0, stroke_s=0.6):
    """[(t, point)] for a wiping hand: from the centre, alternating +-width/2 along `side` every stroke, back at the end."""
    keys, t, sign = [(t0, center)], t0 + stroke_s / 2.0, 1
    h = width_cm / 2.0
    while t < t0 + seconds - stroke_s / 2.0:
        keys.append((round(t, 3), (center[0] + side[0] * h * sign, center[1] + side[1] * h * sign, center[2])))
        sign = -sign
        t += stroke_s
    keys.append((round(t0 + seconds, 3), center))
    return keys


def hand_reach(args):
    """One hand reaches a point or object: touch (hold there), wipe (strokes across a surface), pick (grab and carry)."""
    from tools.icmcp_extra import _avatar, _t
    from tools.fight_tools import reach_key, _secs_time
    from tools.framing import landmarks, _facing
    from tools.project import create_primitive
    from tools.objects import find_by_name
    av = _avatar(args["avatar"])
    hand = args.get("hand", "right")
    action = args.get("action", "touch")
    at, dur = float(args.get("at_s", 1.0)), float(args.get("seconds", 2.0))
    ramp = float(args.get("ramp_s", 0.5))
    fps = RLPy.RGlobal.GetFps()
    f = int(round(at * fps.ToFloat()))
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
    obj = find_by_name(args["object"]) if args.get("object") else None
    if args.get("point"):
        p = tuple(float(v) for v in args["point"])
    elif obj is not None:
        mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
        obj.GetBounds(mx, c, mn)
        p = (c.x, c.y, mx.z)                      # top centre (a tabletop, a cup's rim)
    else:
        raise ValueError("give `point` [x,y,z] or `object` (a prop name)")
    off = args.get("offset_cm") or [0, 0, 3.0 if action == "wipe" else 0]
    p = (p[0] + off[0], p[1] + off[1], p[2] + off[2])
    L = landmarks(av)
    sh = L["r_sh" if hand == "right" else "l_sh"]
    gap = math.dist(sh, p)
    if gap > float(args.get("max_reach_cm", 65.0)):
        raise ValueError(f"{av.GetName()}'s {hand} shoulder is {gap:.0f} cm from the target (arm reach ~55-65 cm): "
                         f"move the person closer or the target nearer")
    name = f"_reach_{av.GetName()}_{hand}"
    try:
        RLPy.RScene.RemoveObject(find_by_name(name))
    except Exception:
        pass
    create_primitive({"type": "box", "name": name, "scale": {"x": 0.02, "y": 0.02, "z": 0.02}})
    tgt = find_by_name(name)
    ctrl = tgt.GetControl("Transform")
    ctrl.ClearKeys()
    S = RLPy.RVector3(0.02, 0.02, 0.02)
    Q = RLPy.RQuaternion(RLPy.RVector4(0, 0, 0, 1))
    ctrl.SetValue(_t(0), RLPy.RTransform(S, Q, RLPy.RVector3(*p)))
    if action == "wipe":
        fx, fy = _facing(av)[:2]
        side = (-fy, fx)                          # perpendicular to the body: strokes across in front of it
        for t, q in wipe_keys(p, side, at, dur, float(args.get("width_cm", 40.0)), float(args.get("stroke_s", 0.6))):
            ctrl.SetValue(_secs_time(t), RLPy.RTransform(S, Q, RLPy.RVector3(*q)))
    tgt.SetVisible(RLPy.RTime.FromValue(0), False)
    eff = hand + "_hand"
    hold_end = at + (float(args.get("carry_after_s", 0.15)) if action == "pick" else dur)
    reach_key({"avatar": av.GetName(), "effector": eff, "seconds": max(0.0, at - ramp), "key_type": "release",
               "transition_s": 0.1})
    reach_key({"avatar": av.GetName(), "effector": eff, "seconds": at, "key_type": "target", "target_object": name,
               "transition_s": ramp})
    reach_key({"avatar": av.GetName(), "effector": eff, "seconds": hold_end, "key_type": "release",
               "transition_s": ramp})
    out = {"ok": True, "action": action, "target": name, "shoulder_to_target_cm": round(gap, 1)}
    bone = next(b for b in av.GetSkeletonComponent().GetSkinBones()
                if b.GetName() == ("CC_Base_R_Hand" if hand == "right" else "CC_Base_L_Hand"))
    if action == "pick":
        # CLAUDE-NOTE (2026-10-18): pick = reach the object, then link it to the hand where it is (align None keeps
        # the current world offset, evidence #40) and release the reach so the arm carries it back into the clip.
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
        st = obj.LinkTo(bone, RLPy.ELinkObjectAlignType__None, _t(f))
        out["linked"] = st == RLPy.RStatus.Success
    # verify: hand on the target at the middle of the hold (pick: at the grab)
    fm = f if action == "pick" else int(round((at + dur / 2.0) * fps.ToFloat()))
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fm + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fm))
    a, b = bone.WorldTransform(), tgt.WorldTransform()
    ta, tb = a.T(), b.T()
    out["hand_to_target_cm"] = round(math.dist((ta.x, ta.y, ta.z), (tb.x, tb.y, tb.z)), 1)
    out["ok"] = out["hand_to_target_cm"] < 15.0 and out.get("linked", True)
    return out


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
    registry["hand_reach"] = {
        "handler": hand_reach, "main_thread": True, "checkpoint": True,
        "description": "A hand reaches a spot via reach IK, over whatever clip the body plays: action touch (rest the "
                       "hand there: push a door, touch a shoulder, lean on a counter), wipe (strokes across a surface "
                       "in front of the body: width_cm, stroke_s), pick (grab `object` and carry it - linked to the "
                       "hand at at_s, the arm then returns to its clip). Target: `point` [x,y,z] or `object` (its top "
                       "centre) + offset_cm. hand right|left, at_s, seconds, ramp_s. Refuses targets beyond arm reach. "
                       "Verifies the hand reaches the target (< 15 cm).",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "hand": {"type": "string", "enum": ["right", "left"]},
            "action": {"type": "string", "enum": ["touch", "wipe", "pick"]},
            "point": {"type": "array", "items": {"type": "number"}}, "object": {"type": "string"},
            "offset_cm": {"type": "array", "items": {"type": "number"}}, "at_s": {"type": "number"},
            "seconds": {"type": "number"}, "ramp_s": {"type": "number"}, "width_cm": {"type": "number"},
            "stroke_s": {"type": "number"}, "carry_after_s": {"type": "number"}, "max_reach_cm": {"type": "number"}},
            "required": ["avatar"]}}
