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


def carry_keys(p0, p1, t0, t1, lift_cm=8.0):
    """[(t, point)] for a hand carrying something from p0 (grab) to p1 (set down): lift straight up, travel level at
    the higher of the two heights + lift, lower onto p1. The lift/lower phases take a quarter of the time each (<= 0.4 s)."""
    up = min(0.4, (t1 - t0) / 4.0)
    z = max(p0[2], p1[2]) + lift_cm
    return [(t0, tuple(p0)), (round(t0 + up, 3), (p0[0], p0[1], z)), (round(t1 - up, 3), (p1[0], p1[1], z)), (t1, tuple(p1))]


def keep_point(hip, facing, sh_z, hand="right", fwd_cm=26.0, side_cm=14.0, below_sh_cm=40.0):
    """Where a hand holds a picked thing in front of the body: fwd_cm ahead of the hip along `facing`, side_cm out
    toward that hand's side, below_sh_cm under the shoulder (about the belly). CC front is -Y at turn 0 and the right
    hand is on the -X side, so the body's right is (fy, -fx)."""
    fx, fy = facing[0], facing[1]
    s = side_cm if hand == "right" else -side_cm
    return (hip[0] + fx * fwd_cm + fy * s, hip[1] + fy * fwd_cm - fx * s, sh_z - below_sh_cm)


def clear_of(pt, hang_cm, half_xy, boxes, gap_cm=3.0):
    """Hand point pt holding a thing that hangs hang_cm below the hand (half_xy = its half footprint): raise pt so the
    thing's bottom clears every box [(lo, hi)] whose footprint it overlaps (a counter, a table). Returns the new point."""
    z = pt[2]
    for lo, hi in boxes:
        if lo[0] - half_xy < pt[0] < hi[0] + half_xy and lo[1] - half_xy < pt[1] < hi[1] + half_xy \
                and z - hang_cm < hi[2] + gap_cm and z > lo[2]:
            z = hi[2] + gap_cm + hang_cm
    return (pt[0], pt[1], z)


def keep_frames(f0, f1, step=3):
    """Sample frames f0..f1 (both ends included) every `step` frames."""
    out = list(range(f0, f1, max(1, step)))
    return out + [f1] if not out or out[-1] != f1 else out


def _destination(args, find_by_name):
    """Where a put-down object's base centre goes: `point` [x,y,z] or the top centre of the prop `onto`."""
    if args.get("onto"):
        mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
        find_by_name(args["onto"]).GetBounds(mx, c, mn)
        return (c.x, c.y, mx.z)
    if args.get("point"):
        return tuple(float(v) for v in args["point"])
    raise ValueError("needs `point` [x,y,z] (where the object's base goes) or `onto` (a prop name)")


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
    placing = None
    if action == "place":
        # CLAUDE-NOTE (2026-10-18): place = put a CARRIED object (picked / hold_prop'd, linked to the hand) down so its
        # base centre lands on `point` (or the top centre of the prop `onto`): the hand target is that spot plus the
        # hand's current offset from the object's base; at at_s the object is UNLINKED (RIObject.UnLink(time)) and
        # snapped upright onto the spot, then the reach releases and the arm goes back to its clip.
        if obj is None:
            raise ValueError("place needs `object` = the carried prop")
        placing = _destination(args, find_by_name)
        mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
        obj.GetBounds(mx, c, mn)
        hb = next(b for b in av.GetSkeletonComponent().GetSkinBones()
                  if b.GetName() == ("CC_Base_R_Hand" if hand == "right" else "CC_Base_L_Hand"))
        W = hb.WorldTransform(); H = W.T()
        p = (placing[0] + H.x - c.x, placing[1] + H.y - c.y, placing[2] + H.z - mn.z)
    elif action == "carry":
        # CLAUDE-NOTE (2026-10-18, measured): pick + place leaves the arm in its clip between them, so a carried box
        # dangled at the hip tilted ~70 deg (ShopCounter). carry keeps ONE reach active from grab to set-down: the hidden
        # target lifts, travels level and lowers onto the destination (carry_keys); link at at_s, unlink at until_s.
        if obj is None or args.get("until_s") is None:
            raise ValueError("carry needs `object` and `until_s` (when it is set down)")
        placing = _destination(args, find_by_name)
        mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
        obj.GetBounds(mx, c, mn)
        p = (c.x, c.y, mx.z)
        p_end = (placing[0], placing[1], placing[2] + (mx.z - mn.z))
    elif args.get("point"):
        p = tuple(float(v) for v in args["point"])
    elif obj is not None:
        mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
        obj.GetBounds(mx, c, mn)
        p = (c.x, c.y, mx.z)                      # top centre (a tabletop, a cup's rim)
    else:
        raise ValueError("give `point` [x,y,z] or `object` (a prop name)")
    off = args.get("offset_cm") or [0, 0, 3.0 if action == "wipe" else 0]
    if placing:
        off = [0, 0, 0]
    p = (p[0] + off[0], p[1] + off[1], p[2] + off[2])
    L = landmarks(av)
    sh = L["r_sh" if hand == "right" else "l_sh"]
    gap = math.dist(sh, p)
    if gap > float(args.get("max_reach_cm", 65.0)):
        raise ValueError(f"{av.GetName()}'s {hand} shoulder is {gap:.0f} cm from the target (arm reach ~55-65 cm): "
                         f"move the person closer or the target nearer")
    keep = args.get("keep_until_s") if action == "pick" else None
    if keep is not None and float(keep) <= at + 0.5:
        raise ValueError("keep_until_s must be at least 0.5 s after at_s")
    if action == "carry":
        until = float(args["until_s"])
        if until <= at + 0.3:
            raise ValueError("until_s must be at least 0.3 s after at_s")
        f2 = int(round(until * fps.ToFloat()))
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f2 + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f2))
        gap2 = math.dist(landmarks(av)["r_sh" if hand == "right" else "l_sh"], p_end)
        if gap2 > float(args.get("max_reach_cm", 65.0)):
            raise ValueError(f"at until_s {av.GetName()}'s {hand} shoulder is {gap2:.0f} cm from the set-down spot "
                             f"(arm reach ~55-65 cm): put it down nearer")
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
    # CLAUDE-NOTE (2026-10-18, measured): one hidden target PER REACH (named by its frame). A shared per-hand name made a
    # second reach (pick then place) delete and recreate the first one's target, so the pick reached for the place spot.
    name = f"_reach_{av.GetName()}_{hand}_{f}"
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
    if action == "carry":
        # CLAUDE-NOTE (2026-10-18, measured ShopCounter): default key transitions overshot (the parcel passed its mark
        # by 11 cm and came back) and the wrist rolled as the arm extended (box tilted ~35 deg). Keys are LINEAR and the
        # target carries the hand's own rotation at the grab, with the reach's rotation switched on, so it stays level.
        hb = next(b for b in av.GetSkeletonComponent().GetSkinBones()
                  if b.GetName() == ("CC_Base_R_Hand" if hand == "right" else "CC_Base_L_Hand"))
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
        Wh = hb.WorldTransform(); Rh = Wh.R()
        Qh = RLPy.RQuaternion(RLPy.RVector4(Rh.x, Rh.y, Rh.z, Rh.w))
        for t, q in carry_keys(p, p_end, at, until, float(args.get("lift_cm", 8.0))):
            ctrl.SetValue(_secs_time(t), RLPy.RTransform(S, Qh, RLPy.RVector3(*q)))
            ctrl.SetKeyTransition(_secs_time(t), RLPy.ETransitionType_Linear, 50.0)
    keep_keys = []
    if keep is not None:
        # CLAUDE-NOTE (2026-10-19): pick released the reach right after the grab, so the arm went back to its clip and
        # the parcel hung tilted at the hip (ShopCounter customer). keep_until_s keeps the reach on: the target lifts,
        # comes in front of the belly (keep_point) over bring_s and then FOLLOWS the hip, sampled every 3 frames, so it
        # also works while the body walks or turns. The hand's grab rotation is kept relative to the body's facing
        # (yaw only) with the reach's rotation on, so the thing stays level instead of rolling with the wrist.
        from tools.seating import qmul
        hb = next(b for b in av.GetSkeletonComponent().GetSkinBones()
                  if b.GetName() == ("CC_Base_R_Hand" if hand == "right" else "CC_Base_L_Hand"))
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
        Wh = hb.WorldTransform(); Rh = Wh.R()
        fx0, fy0 = _facing(av)[:2]
        yaw0 = math.atan2(fy0, fx0)
        q_rel = qmul((0.0, 0.0, math.sin(-yaw0 / 2.0), math.cos(-yaw0 / 2.0)), (Rh.x, Rh.y, Rh.z, Rh.w))
        fk = int(round(float(keep) * fps.ToFloat()))
        fb = min(fk, f + max(1, int(round(float(args.get("bring_s", 0.6)) * fps.ToFloat()))))
        lift = (p[0], p[1], p[2] + float(args.get("lift_cm", 8.0)))
        # CLAUDE-NOTE (2026-10-19, measured ShopCounter): a customer standing AT the counter held the parcel inside it
        # (belly height 86 cm < counter top 95). Furniture under the hold point (props whose top is below the
        # shoulder) pushes the hold up so the kept thing rides just above it.
        mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
        obj.GetBounds(mx, c, mn)
        hang, half = p[2] - mn.z, max(mx.x - mn.x, mx.y - mn.y) / 2.0
        boxes = []
        for pr in RLPy.RScene.GetProps():
            if pr.GetID() == obj.GetID() or pr.GetName().startswith("_reach"):
                continue
            bx, bc, bn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
            pr.GetBounds(bx, bc, bn)
            if 5.0 < bx.z < L["r_sh" if hand == "right" else "l_sh"][2] - 10.0:
                boxes.append(((bn.x, bn.y, bn.z), (bx.x, bx.y, bx.z)))
        keep_keys.append((f, p, (Rh.x, Rh.y, Rh.z, Rh.w)))
        keep_keys.append((f + max(1, (fb - f) // 3), lift, (Rh.x, Rh.y, Rh.z, Rh.w)))
        for fr in keep_frames(fb, fk):
            RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fr + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fr))
            L2 = landmarks(av)
            fx, fy = _facing(av)[:2]
            yaw = math.atan2(fy, fx)
            q = qmul((0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)), q_rel)
            kp = keep_point(L2["hip"], (fx, fy), L2["r_sh" if hand == "right" else "l_sh"][2], hand,
                            float(args.get("hold_forward_cm", 26.0)), float(args.get("hold_side_cm", 14.0)),
                            float(args.get("hold_below_shoulder_cm", 40.0)))
            keep_keys.append((fr, clear_of(kp, hang, half, boxes), q))
        for fr, q3, qq in keep_keys:
            t = fps.IndexedFrameTime(fr)
            ctrl.SetValue(t, RLPy.RTransform(S, RLPy.RQuaternion(RLPy.RVector4(*qq)), RLPy.RVector3(*q3)))
            ctrl.SetKeyTransition(t, RLPy.ETransitionType_Linear, 50.0)
    tgt.SetVisible(RLPy.RTime.FromValue(0), False)
    eff = hand + "_hand"
    hold_end = at + (float(args.get("carry_after_s", 0.15)) if action in ("pick", "place") else dur)
    if action == "carry":
        hold_end = until + float(args.get("carry_after_s", 0.15))
    if keep is not None:
        hold_end = float(keep)
    reach_key({"avatar": av.GetName(), "effector": eff, "seconds": max(0.0, at - ramp), "key_type": "release",
               "transition_s": 0.1})
    reach_key({"avatar": av.GetName(), "effector": eff, "seconds": at, "key_type": "target", "target_object": name,
               "transition_s": ramp, "rotation": action == "carry" or keep is not None})
    reach_key({"avatar": av.GetName(), "effector": eff, "seconds": hold_end, "key_type": "release",
               "transition_s": ramp})
    out = {"ok": True, "action": action, "target": name, "shoulder_to_target_cm": round(gap, 1)}
    bone = next(b for b in av.GetSkeletonComponent().GetSkinBones()
                if b.GetName() == ("CC_Base_R_Hand" if hand == "right" else "CC_Base_L_Hand"))
    if action in ("pick", "carry"):
        # CLAUDE-NOTE (2026-10-18): pick = reach the object, then link it to the hand where it is (align None keeps
        # the current world offset, evidence #40) and release the reach so the arm carries it back into the clip.
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
        st = obj.LinkTo(bone, RLPy.ELinkObjectAlignType__None, _t(f))
        out["linked"] = st == RLPy.RStatus.Success
    if placing:
        fd = f2 if action == "carry" else f
        out["unlinked"] = obj.UnLink(_t(fd)) == RLPy.RStatus.Success
        out["placed_base_error_cm"] = _snap_down(obj, placing, fd, fps)
    if action == "carry":
        # the hand must still be on the target at the set-down (the carry stayed within reach)
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f2 + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f2))
        a2, b2 = bone.WorldTransform(), tgt.WorldTransform()
        t2a, t2b = a2.T(), b2.T()
        out["hand_to_target_at_setdown_cm"] = round(math.dist((t2a.x, t2a.y, t2a.z), (t2b.x, t2b.y, t2b.z)), 1)
    if keep_keys:
        # the hand must stay with the target while it is kept (worst sampled frame after the bring)
        worst = 0.0
        for fr, _, _ in keep_keys[2::4]:
            RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fr + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fr))
            a3, b3 = bone.WorldTransform(), tgt.WorldTransform()
            t3a, t3b = a3.T(), b3.T()
            worst = max(worst, math.dist((t3a.x, t3a.y, t3a.z), (t3b.x, t3b.y, t3b.z)))
        out["hand_to_target_while_kept_cm"] = round(worst, 1)
    # verify: hand on the target at the middle of the hold (pick/place: at the grab / release)
    fm = f if action in ("pick", "place", "carry") else int(round((at + dur / 2.0) * fps.ToFloat()))
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fm + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fm))
    a, b = bone.WorldTransform(), tgt.WorldTransform()
    ta, tb = a.T(), b.T()
    out["hand_to_target_cm"] = round(math.dist((ta.x, ta.y, ta.z), (tb.x, tb.y, tb.z)), 1)
    out["ok"] = out["hand_to_target_cm"] < 15.0 and out.get("linked", True) and out.get("unlinked", True)         and out.get("placed_base_error_cm", 0.0) < 1.0 and out.get("hand_to_target_at_setdown_cm", 0.0) < 15.0 \
        and out.get("hand_to_target_while_kept_cm", 0.0) < 15.0
    return out


def _snap_down(obj, base_pt, f, fps):
    """Key obj at frame f (and hold it) upright with its base centre on base_pt; returns the residual error (cm)."""
    def nudge(fr):
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fr + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(fr))

    def base():
        mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
        obj.GetBounds(mx, c, mn)
        return (c.x, c.y, mn.z)
    ctrl = obj.GetControl("Transform")
    t = fps.IndexedFrameTime(f)
    nudge(f)
    W = obj.WorldTransform(); S = W.S(); R = W.R(); T = W.T()
    S, T = RLPy.RVector3(S.x, S.y, S.z), (T.x, T.y, T.z)
    yaw = math.atan2(2.0 * (R.w * R.z + R.x * R.y), 1.0 - 2.0 * (R.y * R.y + R.z * R.z))
    up = RLPy.RQuaternion(RLPy.RVector4(0, 0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)))
    for _ in range(2):                            # upright first, then move the base onto the spot (bounds re-read)
        ctrl.SetValue(t, RLPy.RTransform(S, up, RLPy.RVector3(*T)))
        nudge(f)
        b = base()
        T = (T[0] + base_pt[0] - b[0], T[1] + base_pt[1] - b[1], T[2] + base_pt[2] - b[2])
    ctrl.SetValue(t, RLPy.RTransform(S, up, RLPy.RVector3(*T)))
    nudge(f)
    return round(math.dist(base(), base_pt), 2)


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
                       "hand at at_s, the arm then returns to its clip), place (put the carried `object` down: its base "
                       "lands on `point` or on top of the prop `onto`, unlinked at at_s and left there upright), carry (pick "
                       "`object` at at_s and keep the hand on it - lift lift_cm, travel level, lower - until until_s, "
                       "then set it down on `point`/`onto`: move a thing across a counter or table). pick + keep_until_s: after the "
                       "grab the hand brings it in front of the belly (bring_s, hold_forward_cm / hold_side_cm / "
                       "hold_below_shoulder_cm) and keeps it there, following the body even while it walks, until keep_until_s "
                       "(a later place can set it down). Target: `point` [x,y,z] or `object` (its top "
                       "centre) + offset_cm. hand right|left, at_s, seconds, ramp_s. Refuses targets beyond arm reach. "
                       "Verifies the hand reaches the target (< 15 cm).",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "hand": {"type": "string", "enum": ["right", "left"]},
            "action": {"type": "string", "enum": ["touch", "wipe", "pick", "place", "carry"]},
            "point": {"type": "array", "items": {"type": "number"}}, "object": {"type": "string"}, "onto": {"type": "string"},
            "offset_cm": {"type": "array", "items": {"type": "number"}}, "at_s": {"type": "number"},
            "seconds": {"type": "number"}, "ramp_s": {"type": "number"}, "width_cm": {"type": "number"},
            "stroke_s": {"type": "number"}, "carry_after_s": {"type": "number"}, "max_reach_cm": {"type": "number"},
            "until_s": {"type": "number"}, "lift_cm": {"type": "number"}, "keep_until_s": {"type": "number"},
            "bring_s": {"type": "number"}, "hold_forward_cm": {"type": "number"}, "hold_side_cm": {"type": "number"},
            "hold_below_shoulder_cm": {"type": "number"}},
            "required": ["avatar"]}}
