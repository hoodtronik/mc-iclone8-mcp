"""IK effector posing baked to motion-layer keys: put a hand, foot or the head on a world point over a clip.

# CLAUDE-NOTE (2026-10-19, measured): RIHikEffectorComponent.Solve(effector, RMatrix4) returns the WHOLE-BODY solved pose
# as world matrices (53 animation bones, no twist/finger-share bones) with the effector exactly on the goal - but only
# while that effector is SetActive(.., Translate, True); inactive it returns an empty map. Solve itself leaves the scene
# alone. SetPosition is NOT usable: it moved the hand somewhere else and the change stuck (survived re-timing and
# SetActive False) until the project was reloaded. So: Solve per sampled frame, convert each solved bone to a local
# rotation (inverse solved parent * solved world) and key the difference as an ADDITIVE layer key (layer * local),
# like pose_bones. Unlike hand_reach this needs no hidden target prop and works for feet and the head.
"""
import math

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

from tools.seating import qmul, qconj

EFFECTORS = {"right_hand": "EHikEffector_RightHand", "left_hand": "EHikEffector_LeftHand",
             "right_foot": "EHikEffector_RightFoot", "left_foot": "EHikEffector_LeftFoot", "head": "EHikEffector_Head",
             "right_elbow": "EHikEffector_RightElbow", "left_elbow": "EHikEffector_LeftElbow"}
EFFECTOR_BONE = {"right_hand": "CC_Base_R_Hand", "left_hand": "CC_Base_L_Hand", "right_foot": "CC_Base_R_Foot",
                 "left_foot": "CC_Base_L_Foot", "head": "CC_Base_Head", "right_elbow": "CC_Base_R_Forearm", "left_elbow": "CC_Base_L_Forearm"}
# the limb each effector moves when body=false (the rest of the body keeps its clip)
LIMB = {"right_hand": ["CC_Base_R_Clavicle", "CC_Base_R_Upperarm", "CC_Base_R_Forearm", "CC_Base_R_Hand"],
        "left_hand": ["CC_Base_L_Clavicle", "CC_Base_L_Upperarm", "CC_Base_L_Forearm", "CC_Base_L_Hand"],
        "right_foot": ["CC_Base_R_Thigh", "CC_Base_R_Calf", "CC_Base_R_Foot"],
        "left_foot": ["CC_Base_L_Thigh", "CC_Base_L_Calf", "CC_Base_L_Foot"],
        "head": ["CC_Base_NeckTwist01", "CC_Base_NeckTwist02", "CC_Base_Head"]}
LIMB["right_elbow"], LIMB["left_elbow"] = LIMB["right_hand"][:3], LIMB["left_hand"][:3]
# CLAUDE-NOTE (2026-10-19, measured on Stand Wait_M): leg layer keys (a 65 deg thigh key) left the foot where it was -
# MotionPlus clips pin the feet with their own IK - so feet are posed through a reach key on a hidden target instead
# (reach overrides the clip's foot IK, as pin_effector showed).
REACH_ROUTE = ("right_foot", "left_foot")
_FINGERS = ("Thumb", "Index", "Mid", "Ring", "Pinky")


def same_hemisphere(q, prev):
    """q or -q, whichever is nearer prev: consecutive layer keys must not flip sign or iClone interpolates the long way
    round (measured: keys exact, the frames between them 16 cm off)."""
    if prev is not None and sum(x * y for x, y in zip(q, prev)) < 0:
        return tuple(-v for v in q)
    return q


def lerp3(a, b, w):
    return tuple(a[i] + (b[i] - a[i]) * w for i in range(3))


def slerp(a, b, w):
    """Shortest-path slerp between unit quaternions (x, y, z, w)."""
    d = sum(x * y for x, y in zip(a, b))
    if d < 0:
        b, d = tuple(-v for v in b), -d
    if d > 0.9995:
        q = tuple(a[i] + (b[i] - a[i]) * w for i in range(4))
    else:
        th = math.acos(d)
        s = math.sin(th)
        ka, kb = math.sin((1 - w) * th) / s, math.sin(w * th) / s
        q = tuple(a[i] * ka + b[i] * kb for i in range(4))
    n = math.sqrt(sum(v * v for v in q))
    return tuple(v / n for v in q)


def new_layer(target_local, composed_local, old_layer):
    """Layer key that makes the bone's local rotation target_local: the composed local is old_layer * clip, so the new
    layer is (target * inverse(composed)) * old_layer."""
    return qmul(qmul(target_local, qconj(composed_local)), old_layer)


def _mq(M):
    m3 = RLPy.RMatrix3()
    M.GetSimpleRotate(m3)
    q = RLPy.RQuaternion().FromRotationMatrix(m3)
    return (q.x, q.y, q.z, q.w)


def _tq(t):
    r = t.R()
    return (r.x, r.y, r.z, r.w)


def key_bones(which, end_bone, body):
    """Bones an IK pose keys: the effector's limb; with body=True also its chain down to the hip and both legs
    (so the feet stay planted when the hip turns). The other arm and the head keep their clip and simply ride along,
    so a second ik_pose on another limb at the same time does not undo this one."""
    names = set(LIMB[which])
    if body:
        b = end_bone
        while b is not None:
            names.add(b.GetName())
            if b.GetName() == "CC_Base_Hip":
                break
            b = b.GetParent()
        for side in ("L", "R"):
            names |= {f"CC_Base_{side}_Thigh", f"CC_Base_{side}_Calf", f"CC_Base_{side}_Foot", f"CC_Base_{side}_ToeBase"}
    return names


def _solve_and_key(hik, E, aim, clip, ct, by, keyset, last):
    m = RLPy.RMatrix4(); m.MakeIdentity(); m.SetTranslate(RLPy.RVector3(*aim))
    hik.SetActive(E, RLPy.EHikEffectorType_Translate, True)
    try:
        solved = hik.Solve(E, m).asdict()
    finally:
        hik.SetActive(E, RLPy.EHikEffectorType_Translate, False)
    if not solved:
        raise RuntimeError("HIK Solve returned no bones (is this a CC3/CC4 character?)")
    sw = {n: _mq(M) for n, M in solved.items()}
    rows = []
    for n in keyset:
        if n not in sw or n not in by:
            continue
        b = by[n]
        p = b.GetParent()
        pn = p.GetName() if p is not None else None
        if pn in sw and pn in keyset:
            pq = sw[pn]
        else:
            pw = p.WorldTransform()
            pq = _tq(pw)
        lt = b.LocalTransform()
        rows.append((b, qmul(qconj(pq), sw[n]), _tq(lt)))
    keyed = 0
    for b, target_local, composed in rows:
        ctrl = clip.GetControl("Layer", b)
        if ctrl is None:
            continue
        old = RLPy.RTransform()
        ctrl.GetValue(ct, old)
        lq = same_hemisphere(new_layer(target_local, composed, _tq(old)), last.get(b.GetName()))
        last[b.GetName()] = lq
        key = RLPy.RTransformKey()
        key.SetTime(ct)
        key.SetTransform(RLPy.RTransform(RLPy.RVector3(1, 1, 1), RLPy.RQuaternion(RLPy.RVector4(*lq)),
                                         RLPy.RVector3(0, 0, 0)))
        ctrl.AddKey(key)
        keyed += 1
    return keyed


def ik_pose(args):
    from tools.icmcp_extra import _avatar
    from tools.objects import find_by_name
    from tools.layering import ramp
    av = _avatar(args["avatar"])
    sk = av.GetSkeletonComponent()
    hik = av.GetHikEffectorComponent()
    which = args.get("effector", "right_hand")
    if which not in EFFECTORS:
        raise ValueError(f"effector must be one of {sorted(EFFECTORS)}")
    E = getattr(RLPy, EFFECTORS[which])
    fps = RLPy.RGlobal.GetFps()
    fpsf = fps.ToFloat()
    at, hold = float(args.get("at_s", 1.0)), float(args.get("hold_s", 1.0))
    blend = max(1, int(round(float(args.get("blend_s", 0.4)) * fpsf)))
    step = max(1, int(args.get("step", 1)))
    fa, fe = int(round(at * fpsf)), int(round((at + hold) * fpsf))
    f0, f1 = max(0, fa - blend), fe + blend
    if args.get("point"):
        goal = tuple(float(v) for v in args["point"])
    elif args.get("object"):
        mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
        find_by_name(args["object"]).GetBounds(mx, c, mn)
        goal = (c.x, c.y, mx.z)
    else:
        raise ValueError("give `point` [x,y,z] or `object` (a prop name; its top centre)")
    off = args.get("offset_cm") or [0, 0, 0]
    goal = (goal[0] + off[0], goal[1] + off[1], goal[2] + off[2])
    by = {b.GetName(): b for b in sk.GetSkinBones()}
    end_bone = by[EFFECTOR_BONE[which]]
    body = bool(args.get("body", True))
    if which in REACH_ROUTE:
        return _foot_by_reach(av, which, goal, at, hold, float(args.get("blend_s", 0.4)), end_bone, fps,
                              float(args.get("tolerance_cm", 4.0)))
    keyset = key_bones(which, end_bone, body)
    last = {}
    now = RLPy.RGlobal.GetTime()
    frames = sorted(set(list(range(f0, f1 + 1, step)) + [f1, fa, fe]))
    keyed, skipped = 0, 0
    for f in frames:
        t = fps.IndexedFrameTime(f)
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(t)
        clip = sk.GetClipByTime(t)
        if clip is None:
            skipped += 1
            continue
        w = ramp(f, f0, f1, blend)
        ct = clip.SceneTimeToClipTime(t)
        ew = end_bone.WorldTransform(); et = ew.T()
        cur = (et.x, et.y, et.z)
        # CLAUDE-NOTE: blend the GOAL (current effector position -> goal), not the bone offsets, so the effector
        # travels in a straight line and every solved frame is a real IK pose.
        g = lerp3(cur, goal, w)
        aim = g
        for _ in range(int(args.get("iterations", 3))):
            keyed += _solve_and_key(hik, E, aim, clip, ct, by, keyset, last)
            RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(t)
            ew = end_bone.WorldTransform(); et = ew.T()
            got = (et.x, et.y, et.z)
            miss = tuple(g[i] - got[i] for i in range(3))
            if math.sqrt(sum(v * v for v in miss)) < 0.5:
                break
            # CLAUDE-NOTE (2026-10-19, measured): only part of the solved body is keyed (the solver also shifts the
            # hip, which a rotation layer cannot), so the effector can land short; re-solve from the keyed pose
            # with the goal pushed by the miss.
            aim = tuple(aim[i] + miss[i] for i in range(3))
    # verify: the effector bone on the goal through the hold
    errs = []
    for f in sorted(set([fa, (fa + fe) // 2, fe])):
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
        ew = end_bone.WorldTransform(); et = ew.T()
        errs.append(round(math.dist((et.x, et.y, et.z), goal), 1))
    RLPy.RGlobal.SetTime(now)
    tol = float(args.get("tolerance_cm", 4.0))
    return {"ok": max(errs) < tol, "avatar": av.GetName(), "effector": which, "goal": [round(v, 1) for v in goal],
            "frames": [f0, f1], "keys": keyed, "frames_without_clip": skipped,
            "effector_to_goal_cm": errs, "body": body}


def _foot_by_reach(av, which, goal, at, hold, blend, bone, fps, tol):
    from tools.fight_tools import reach_key
    from tools.project import create_primitive
    from tools.objects import find_by_name
    from tools.icmcp_extra import _t
    fa, fe = int(round(at * fps.ToFloat())), int(round((at + hold) * fps.ToFloat()))
    name = f"_ik_{av.GetName()}_{which}_{fa}"
    try:
        RLPy.RScene.RemoveObject(find_by_name(name))
    except Exception:
        pass
    create_primitive({"type": "box", "name": name, "scale": {"x": 0.02, "y": 0.02, "z": 0.02}})
    tgt = find_by_name(name)
    ctrl = tgt.GetControl("Transform")
    ctrl.ClearKeys()
    ctrl.SetValue(_t(0), RLPy.RTransform(RLPy.RVector3(0.02, 0.02, 0.02), RLPy.RQuaternion(RLPy.RVector4(0, 0, 0, 1)),
                                         RLPy.RVector3(*goal)))
    tgt.SetVisible(RLPy.RTime.FromValue(0), False)
    reach_key({"avatar": av.GetName(), "effector": which, "seconds": max(0.0, at - blend), "key_type": "release",
               "transition_s": 0.1})
    reach_key({"avatar": av.GetName(), "effector": which, "seconds": at, "key_type": "target", "target_object": name,
               "transition_s": blend})
    reach_key({"avatar": av.GetName(), "effector": which, "seconds": at + hold, "key_type": "target",
               "target_object": name, "transition_s": 0.1})
    reach_key({"avatar": av.GetName(), "effector": which, "seconds": at + hold + blend, "key_type": "release",
               "transition_s": blend})
    errs = []
    for f in sorted(set([fa, (fa + fe) // 2, fe])):
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
        w = bone.WorldTransform(); t = w.T()
        errs.append(round(math.dist((t.x, t.y, t.z), goal), 1))
    return {"ok": max(errs) < tol, "avatar": av.GetName(), "effector": which, "goal": [round(v, 1) for v in goal],
            "route": "reach", "target": name, "effector_to_goal_cm": errs}


def register(registry):
    registry["ik_pose"] = {
        "handler": ik_pose, "main_thread": True, "checkpoint": True,
        "description": "IK POSE over any clip: put an effector (" + ", ".join(sorted(EFFECTORS)) + ") on a world "
                       "point [x,y,z] (or the top centre of `object` + offset_cm) at at_s, hold it hold_s, eased in "
                       "and out over blend_s (0.4). iClone's full-body HumanIK solves each frame (step 1) and "
                       "the result is baked as additive motion-layer keys - no hidden target prop, and it works for "
                       "feet (a foot up on a step or chair rung), elbows and the head (lean in to look); feet go through a reach key on a hidden target (stock clips pin feet with their own IK). "
                       "body=false moves only that limb (the spine keeps its clip): small adjustments only - a neck-only head missed an 8 cm lean by ~15 cm. Overlapping poses on one body share the spine: the LAST call is exact. Returns "
                       "effector_to_goal_cm at the start, middle and end of the hold (ok < tolerance_cm 4).",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "effector": {"type": "string", "enum": sorted(EFFECTORS)},
            "point": {"type": "array", "items": {"type": "number"}}, "object": {"type": "string"},
            "offset_cm": {"type": "array", "items": {"type": "number"}}, "at_s": {"type": "number"},
            "hold_s": {"type": "number"}, "blend_s": {"type": "number"}, "step": {"type": "integer"},
            "body": {"type": "boolean"}, "tolerance_cm": {"type": "number"}, "iterations": {"type": "integer"}},
            "required": ["avatar"]}}
