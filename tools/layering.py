"""Upper-body overlays: play part of one clip (arms, head) on top of whatever the body is doing (a walk, an idle).

iClone keeps a per-bone motion LAYER on every clip (`RIClip.GetControl("Layer", bone)` -> RTransformControl). A layer key
is ADDITIVE: the bone's local rotation becomes layer * clip (measured: a 40 deg Z key on the forearm composed as
off * q_clip, and one key holds for the whole clip). So to make a bone follow another clip we key, per frame,
layer = target * inverse(base), where base = the bone's current local rotation and target = the overlay clip's.
The overlay clip is read by loading it on the same avatar after the project end, sampling, and deleting it again.
# CLAUDE-NOTE (2026-10-18): built to close "texting / talking while walking" (no stock clip does both; Motion Director
# only plays locomotion). The legs keep their clip; only the chosen chains follow the overlay.
"""
import math
import os

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

from tools.seating import qmul, qconj

SIDE_CHAINS = {"arm_r": ["CC_Base_R_Clavicle"], "arm_l": ["CC_Base_L_Clavicle"],
               "arms": ["CC_Base_R_Clavicle", "CC_Base_L_Clavicle"]}
HEAD = ["CC_Base_NeckTwist01", "CC_Base_NeckTwist02", "CC_Base_Head"]      # head itself, not its face bones
PRESETS = {"arm_r": (["arm_r"], []), "arm_l": (["arm_l"], []), "arms": (["arms"], []),
           "head": ([], HEAD), "arm_r_head": (["arm_r"], HEAD), "arms_head": (["arms"], HEAD),
           "upper": (["arms"], ["CC_Base_Spine02"] + HEAD)}


# ----------------------------------------------------------------------------------------------- pure helpers
def slerp_identity(q, w):
    """Rotation q scaled by weight w in [0, 1] (slerp from identity)."""
    x, y, z, qw = q
    if qw < 0:
        x, y, z, qw = -x, -y, -z, -qw
    ang = 2.0 * math.acos(max(-1.0, min(1.0, qw)))
    s = math.sqrt(max(0.0, 1.0 - qw * qw))
    if s < 1e-6 or ang < 1e-6:
        return (0.0, 0.0, 0.0, 1.0)
    a = ang * w / 2.0
    k = math.sin(a) / s
    return (x * k, y * k, z * k, math.cos(a))


def layer_offset(target, base, w=1.0):
    """Layer rotation that turns `base` into `target` (layer * base = target), scaled by weight w."""
    return slerp_identity(qmul(target, qconj(base)), w)


def ramp(f, start, end, blend):
    """Overlay weight at frame f: 0 -> 1 over `blend` frames after start, 1 -> 0 over `blend` frames before end."""
    if blend <= 0:
        return 1.0 if start <= f <= end else 0.0
    a = (f - start) / float(blend)
    b = (end - f) / float(blend)
    w = max(0.0, min(1.0, a, b))
    return w * w * (3.0 - 2.0 * w)            # smoothstep


def angle_deg(a, b):
    d = abs(sum(x * y for x, y in zip(a, b)))
    return math.degrees(2.0 * math.acos(min(1.0, d)))


# ------------------------------------------------------------------------------------------------------ RLPy side
def _bones(sk, which):
    by = {b.GetName(): b for b in sk.GetSkinBones()}
    chains, singles = PRESETS.get(which, (None, None)) if isinstance(which, str) else ([], list(which))
    if chains is None:
        raise ValueError(f"bones must be one of {sorted(PRESETS)} or a list of bone names")
    names = []
    for c in chains:
        for root in SIDE_CHAINS[c]:
            stack = [by[root]]
            while stack:
                b = stack.pop()
                names.append(b.GetName())
                stack += list(b.GetChildren())
    names += [n for n in singles if n in by]
    missing = [n for n in singles if n not in by]
    if missing:
        raise ValueError(f"no bones {missing} on this avatar")
    # CLAUDE-NOTE (2026-10-18, measured): twist/share bones are driven (no Layer control) and hands carry accessory
    # bones (Phone_R, Cigarette on MD-ready avatars) - only the skeleton's animation bones take layer keys.
    anim = {b.GetName() for b in sk.GetAllAnimationBone()}
    return [by[n] for n in dict.fromkeys(names) if n in anim]


def _q(t):
    r = t.R()
    return (r.x, r.y, r.z, r.w)


def _sample_local(bones, frames):
    fps = RLPy.RGlobal.GetFps()
    out = {b.GetName(): [] for b in bones}
    for f in frames:
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1))       # move away first: the first read after a jump is stale
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
        for b in bones:
            lt = b.LocalTransform()
            out[b.GetName()].append(_q(lt))
    return out


def _clear_layers(sk, bones, f0, f1):
    fps = RLPy.RGlobal.GetFps()
    seen = set()
    for f in range(f0, f1 + 1, 5):
        clip = sk.GetClipByTime(fps.IndexedFrameTime(f))
        if clip is None or id(clip) in seen:
            continue
        seen.add(id(clip))
        for b in bones:
            clip.GetControl("Layer", b).ClearKeys()


def overlay_clip(args):
    from tools.acting import resolve_clip
    from tools.common import load_motion_clip
    from tools.icmcp_extra import _avatar
    av = _avatar(args["avatar"])
    sk = av.GetSkeletonComponent()
    fps = RLPy.RGlobal.GetFps()
    fpsf = fps.ToFloat()
    f0, f1 = int(args["start_frame"]), int(args["end_frame"])
    if f1 <= f0:
        raise ValueError("end_frame must be after start_frame")
    step = max(1, int(args.get("step", 2)))
    blend = int(round(float(args.get("blend_s", 0.4)) * fpsf))
    bones = _bones(sk, args.get("bones", "arm_r"))
    path = resolve_clip(args["clip"])
    src0 = int(round(float(args.get("clip_offset_s", 0.0)) * fpsf))
    frames = list(range(f0, f1 + 1, step))
    if frames[-1] != f1:
        frames.append(f1)
    now = RLPy.RGlobal.GetTime()
    proj_len = RLPy.RGlobal.GetProjectLength()
    end_f = fps.GetFrameIndex(proj_len)

    # 1. the body's own pose (without old overlays on these bones)
    _clear_layers(sk, bones, f0, f1)
    base = _sample_local(bones, frames)

    # 2. the overlay clip, loaded after everything else on this avatar, sampled, removed
    last = 0
    for i in range(sk.GetClipCount()):
        c = sk.GetClip(i)
        last = max(last, fps.GetFrameIndex(RLPy.RTime.FromValue(c.ClipTimeToSceneTime(RLPy.RTime.FromValue(0)).ToInt()
                                                                  + c.GetLength().ToInt())))
    t0 = max(end_f, last) + 30
    n_before = sk.GetClipCount()
    load_motion_clip(av, path, fps.IndexedFrameTime(t0), allow_unchanged=True)
    tmp = sk.GetClipByTime(fps.IndexedFrameTime(t0 + 1))
    if tmp is None or sk.GetClipCount() != n_before + 1:
        RLPy.RGlobal.SetProjectLength(proj_len)
        raise RuntimeError("could not load the overlay clip after the project end")
    try:
        src_len = max(1, fps.GetFrameIndex(tmp.GetLength()) - 1)
        # CLAUDE-NOTE (2026-10-18, measured): SetTime past the project length clamps to its end - the first version
        # "sampled" the walk's last frame and keyed nothing visible. Extend the project while sampling.
        RLPy.RGlobal.SetProjectLength(fps.IndexedFrameTime(t0 + src_len + 10))
        src_frames = [t0 + (src0 + (f - f0)) % src_len for f in frames]
        target = _sample_local(bones, src_frames)
    finally:
        sk.DeleteClip(tmp) if hasattr(sk, "DeleteClip") else None
        RLPy.RGlobal.SetProjectLength(proj_len)
    if sk.GetClipCount() != n_before:
        raise RuntimeError("the temporary overlay clip could not be removed")

    # 3. layer keys = target * inverse(base), weighted by the blend ramp; identity just outside the range
    keyed = 0
    edges = [(max(0, f0 - step), None), (min(end_f, f1 + step), None)]
    plan = [(f, i) for i, f in enumerate(frames)] + edges
    for f, i in plan:
        t = fps.IndexedFrameTime(f)
        clip = sk.GetClipByTime(t)
        if clip is None:
            continue
        ct = clip.SceneTimeToClipTime(t)
        w = 0.0 if i is None else ramp(f, f0, f1, blend)
        for b in bones:
            n = b.GetName()
            off = (0.0, 0.0, 0.0, 1.0) if i is None else layer_offset(target[n][i], base[n][i], w)
            key = RLPy.RTransformKey()
            key.SetTime(ct)
            key.SetTransform(RLPy.RTransform(RLPy.RVector3(1, 1, 1), RLPy.RQuaternion(RLPy.RVector4(*off)),
                                             RLPy.RVector3(0, 0, 0)))
            clip.GetControl("Layer", b).AddKey(key)
            keyed += 1

    # 4. verify at full weight: the bones should now hold the overlay's local rotations
    full = [i for i, f in enumerate(frames) if ramp(f, f0, f1, blend) >= 0.999][::max(1, len(frames) // 12)]
    got = _sample_local(bones, [frames[i] for i in full]) if full else {}
    err = max([angle_deg(got[b.GetName()][k], target[b.GetName()][i]) for b in bones for k, i in enumerate(full)] or [0.0])
    RLPy.RGlobal.SetTime(now)
    return {"ok": err < 3.0, "avatar": av.GetName(), "clip": os.path.splitext(os.path.basename(path))[0],
            "bones": len(bones), "frames": [f0, f1], "keys": keyed, "max_error_deg": round(err, 2),
            "overlay_clip_frames": src_len}


LAUGH_BONES = ["CC_Base_Spine02", "CC_Base_NeckTwist01", "CC_Base_Head", "CC_Base_R_Clavicle", "CC_Base_L_Clavicle"]


def axis_angle(axis, deg):
    h = math.radians(deg) / 2.0
    n = math.sqrt(sum(a * a for a in axis)) or 1.0
    s = math.sin(h) / n
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(h))


def laugh_angles(t, env, intensity=1.0, hz=4.5):
    """Degrees per bone at t seconds into a laugh (env = 0..1 envelope): + about the body's side axis = lean/tilt
    back; clavicles: shoulder lift. A held lean-back with a 4-5 Hz heave/bounce on top."""
    w = 2.0 * math.pi * hz * t
    k = intensity * env
    # CLAUDE-NOTE (2026-10-18, render): the first amplitudes (head 6+-3 deg) read as a gentle smile; doubled.
    return {"CC_Base_Spine02": k * (4.0 + 4.0 * math.sin(w)),
            "CC_Base_NeckTwist01": k * (5.0 + 2.5 * math.sin(w + 0.3)),
            "CC_Base_Head": k * (10.0 + 4.5 * math.sin(w + 0.6)),
            "shoulders": k * (3.0 + 4.0 * max(0.0, math.sin(w)))}


def laugh_face(t, env, intensity=1.0, hz=4.5):
    """Expression slider weights (0..1) at t: a held smile/squint with the mouth pulsing open on each 'ha'."""
    k = min(1.0, intensity) * env
    ha = max(0.0, math.sin(2.0 * math.pi * hz * t))
    # squint/cheeks high: at 0.55 the open mouth with wide eyes read as shouting (render)
    return {"Mouth_Smile": 0.95 * k, "Cheek_Raise_L": 0.9 * k, "Cheek_Raise_R": 0.9 * k, "Eye_Squint_L": 0.85 * k,
            "Eye_Squint_R": 0.85 * k, "Mouth_Open": (0.2 + 0.4 * ha) * k, "Turn_Jaw_Down": (0.15 + 0.35 * ha) * k}


def laugh(args):
    """Procedural laugh: lean/tilt back with a rhythmic heave and shoulder bounce (motion-layer keys) + a big-smile
    expression on the face."""
    from tools.icmcp_extra import _avatar
    from tools.framing import _facing
    from tools.seating import qrot
    # CLAUDE-NOTE (2026-10-18, cafe trial): no stock laugh clip exists (searched Motion/Motion Plus/Expression). Built from
    # parts: rotations are about the body's own side/forward axes (expressed in each bone's parent frame, since a layer
    # key composes as layer * local), so it works whatever the clip and heading.
    av = _avatar(args["avatar"])
    sk = av.GetSkeletonComponent()
    fps = RLPy.RGlobal.GetFps()
    fpsf = fps.ToFloat()
    f0 = int(args["start_frame"])
    f1 = f0 + int(round(float(args.get("seconds", 2.0)) * fpsf))
    blend = int(round(float(args.get("blend_s", 0.3)) * fpsf))
    inten = float(args.get("intensity", 1.0))
    by = {b.GetName(): b for b in sk.GetSkinBones()}
    anim = {b.GetName() for b in sk.GetAllAnimationBone()}
    bones = [by[n] for n in LAUGH_BONES if n in by and n in anim]
    now = RLPy.RGlobal.GetTime()
    _clear_layers(sk, bones, f0, f1)
    keyed, peak = 0, 0.0
    for f in range(max(0, f0 - 1), f1 + 2):
        t = fps.IndexedFrameTime(f)
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(t)
        clip = sk.GetClipByTime(t)
        if clip is None:
            continue
        fx, fy, _ = _facing(av)
        fwd = (fx, fy, 0.0)
        side = (fy, -fx, 0.0)                    # fwd x up: + rotation tilts the front upward (lean back)
        env = ramp(f, f0, f1, blend)
        ang = laugh_angles((f - f0) / fpsf, env, inten)
        ct = clip.SceneTimeToClipTime(t)
        for b in bones:
            n = b.GetName()
            if n == "CC_Base_R_Clavicle":
                axis, deg = fwd, -ang["shoulders"]
            elif n == "CC_Base_L_Clavicle":
                axis, deg = fwd, ang["shoulders"]
            else:
                axis, deg = side, ang[n]
            pw = b.GetParent().WorldTransform()
            pq = _q(pw)
            local_axis = qrot(qconj(pq), axis)
            off = axis_angle(local_axis, deg)
            key = RLPy.RTransformKey()
            key.SetTime(ct)
            key.SetTransform(RLPy.RTransform(RLPy.RVector3(1, 1, 1), RLPy.RQuaternion(RLPy.RVector4(*off)),
                                             RLPy.RVector3(0, 0, 0)))
            clip.GetControl("Layer", b).AddKey(key)
            keyed += 1
            if n == "CC_Base_Head":
                peak = max(peak, abs(deg))
    face = None
    if args.get("face", True):
        # CLAUDE-NOTE (2026-10-18, render): a static big-smile clip left the mouth closed; a laugh is the mouth
        # opening on every 'ha'. Key the sliders per frame (RIFaceComponent.AddExpressionKeys inside an expression
        # clip - an existing face clip at that time takes the keys, else one is added).
        fc = av.GetFaceComponent()
        have = set(fc.GetExpressionNames(""))
        names = [n for n in laugh_face(0, 1).keys() if n in have]
        t0 = fps.IndexedFrameTime(max(0, f0 - 3))
        if fc.GetClipByTime(t0) is None and fc.GetClipByTime(fps.IndexedFrameTime(f1)) is None:
            fc.AddClip(t0, "Laugh", fps.IndexedFrameTime(f1 - f0 + 10))
        fc.BeginKeyEditing()
        try:
            for f in range(max(0, f0 - 2), f1 + 3, 2):
                w = laugh_face((f - f0) / fpsf, ramp(f, f0, f1, blend), inten)
                fc.AddExpressionKeys(fps.IndexedFrameTime(f), names, [w[n] for n in names], RLPy.RTime.FromValue(0))
        finally:
            fc.EndKeyEditing()
        mid = fps.IndexedFrameTime((f0 + f1) // 2)
        face = dict(zip(names, [round(v, 2) for v in fc.GetExpressionWeights(mid, names)]))
    RLPy.RGlobal.SetTime(now)
    return {"ok": keyed > 0, "avatar": av.GetName(), "frames": [f0, f1], "keys": keyed,
            "head_tilt_peak_deg": round(peak, 1), "face": face}


FINGERS = ("Thumb", "Index", "Mid", "Ring", "Pinky")
# per finger: curl degrees at joints 1, 2, 3 (+ = toward the palm) and spread at joint 1 (+ = away from the middle)
_RELAX = (12, 22, 12, 0)
_FIST = (80, 95, 60, 0)
HAND_POSES = {
    "open": {"Thumb": (0, 0, 0, 0), **{f: (0, 0, 0, 4) for f in FINGERS[1:]}},
    "relaxed": {"Thumb": (8, 12, 8, 0), **{f: _RELAX for f in FINGERS[1:]}},
    "fist": {"Thumb": (35, 40, 35, 0), **{f: _FIST for f in FINGERS[1:]}},
    "point": {"Thumb": (35, 40, 35, 0), "Index": (0, 0, 0, 0), **{f: _FIST for f in FINGERS[2:]}},
    "grip": {"Thumb": (25, 30, 25, 0), **{f: (55, 60, 35, 0) for f in FINGERS[1:]}},
    "pinch": {"Thumb": (25, 30, 25, 0), "Index": (45, 40, 20, 0), **{f: (30, 45, 25, 0) for f in FINGERS[2:]}},
    "thumbs_up": {"Thumb": (0, 0, 0, 0), **{f: _FIST for f in FINGERS[1:]}},
    "peace": {"Thumb": (35, 40, 35, 0), "Index": (0, 0, 0, 8), "Mid": (0, 0, 0, 8),
              "Ring": _FIST, "Pinky": _FIST},
}


def _v(a):
    return (a[0], a[1], a[2])


def _vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _vnorm(a):
    n = math.sqrt(sum(x * x for x in a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def finger_targets(bind, side, pose):
    """Local rotations (x, y, z, w) of every finger joint for a pose, from the bind skeleton.
    bind: {bone name: (T, Q)} rest pose in one common space; side 'R' or 'L'.
    Curl axis per joint = finger direction x palm normal (rotating the bone toward the palm); the rotation is applied
    in the parent's frame on top of the bind local rotation, so it is independent of where the hand is."""
    p = f"CC_Base_{side}_"
    pos = {n: _v(t) for n, (t, q) in bind.items()}
    s = _vsub(pos[p + "Index1"], pos[p + "Pinky1"])                      # across the knuckles, pinky -> index
    d = _vsub(pos[p + "Mid2"], pos[p + "Mid1"])                          # along the fingers
    n = _vnorm(_vcross(s, d))
    if side == "L":                                                     # mirrored hand: flip to keep 'toward palm'
        n = (-n[0], -n[1], -n[2])
    out = {}
    for f in FINGERS:
        c1, c2, c3, spread = HAND_POSES[pose][f]
        names = [p + f + str(k) for k in (1, 2, 3)]
        mid1 = pos[p + "Mid1"]
        for k, name in enumerate(names):
            if name not in bind:
                continue
            nxt = names[k + 1] if k < 2 else None
            dk = _vnorm(_vsub(pos[nxt], pos[name]) if nxt and nxt in pos else _vsub(pos[name], pos[names[k - 1]]))
            axis = _vnorm(_vcross(dk, n))
            q = axis_angle(axis, (c1, c2, c3)[k])
            if k == 0 and spread and f != "Mid":
                e = _vnorm(_vsub(pos[name], mid1))
                sign = 1.0 if sum(a * b for a, b in zip(_vcross(n, dk), e)) > 0 else -1.0
                q = qmul(axis_angle(n, sign * spread), q)
            elif k == 0 and spread and f == "Mid":
                ei = _vnorm(_vsub(pos[p + "Index1"], mid1))                # middle leans toward the index (peace)
                sign = 1.0 if sum(a * b for a, b in zip(_vcross(n, dk), ei)) > 0 else -1.0
                q = qmul(axis_angle(n, -sign * spread * 0.5), q)
            parent_name = (p + f + str(k)) if k else p + "Hand"
            pq = bind[parent_name][1]
            bq = bind[name][1]
            world_target = qmul(q, bq)                                    # rotate the bone in world (bind) space
            out[name] = qmul(qconj(pq), world_target)                     # back to the parent's frame = local
    return out


def hand_pose(args):
    """Finger pose (fist, point, grip, ...) on one or both hands over a frame range, on top of any clip."""
    from tools.icmcp_extra import _avatar
    from tools.seating import _bind_world
    # CLAUDE-NOTE (2026-10-18, measured): applying a stock .iHand gesture with RFileIO.LoadObject (avatar selected,
    # Apply Gesture Options = Both) changed nothing, and no RLPy/RLPy2 call applies Gesture content. Finger poses are
    # built here instead: absolute joint rotations from the bind skeleton, written as motion-layer keys
    # layer = target * inverse(clip pose) (the overlay_clip mechanism), so the hand holds the pose whatever the clip.
    # CLAUDE-NOTE (2026-10-18): layer keys are cleared per clip, so a second call would wipe the first pose; a sequence
    # of poses is keyed in one call (`poses`).
    segs = args.get("poses") or [{"pose": args.get("pose", "fist"), "start_frame": args.get("start_frame"),
                                  "end_frame": args.get("end_frame")}]
    for s in segs:
        if s.get("pose") not in HAND_POSES:
            raise ValueError(f"pose must be one of {sorted(HAND_POSES)}")
        if s.get("start_frame") is None or s.get("end_frame") is None or int(s["end_frame"]) <= int(s["start_frame"]):
            raise ValueError("each pose needs start_frame < end_frame")
    segs = sorted(segs, key=lambda s: int(s["start_frame"]))
    av = _avatar(args["avatar"])
    sk = av.GetSkeletonComponent()
    fps = RLPy.RGlobal.GetFps()
    fpsf = fps.ToFloat()
    step = max(1, int(args.get("step", 3)))
    blend = int(round(float(args.get("blend_s", 0.25)) * fpsf))
    sides = {"r": ["R"], "l": ["L"], "both": ["R", "L"]}[args.get("hand", "r")]
    by = {b.GetName(): b for b in sk.GetSkinBones()}
    anim = {b.GetName() for b in sk.GetAllAnimationBone()}
    memo, binds = {}, {}
    for side in sides:
        need = [f"CC_Base_{side}_{f}{k}" for f in FINGERS for k in (1, 2, 3)] + [f"CC_Base_{side}_Hand"]
        missing = [n for n in need if n not in by]
        if missing:
            raise ValueError(f"{av.GetName()} lacks finger bones {missing[:4]} (hand_pose needs a CC3/CC4 skeleton)")
        binds[side] = {n: _bind_world(by[n], memo) for n in need}
    targets = {}
    for s in segs:
        if s["pose"] not in targets:
            targets[s["pose"]] = {}
            for side in sides:
                targets[s["pose"]].update(finger_targets(binds[side], side, s["pose"]))
    bones = [by[n] for n in next(iter(targets.values())) if n in anim]
    end_f = fps.GetFrameIndex(RLPy.RGlobal.GetProjectLength())
    # frame -> (pose, weight); identity keys just outside each segment unless another segment covers that frame
    plan = {}
    for s in segs:
        f0, f1 = int(s["start_frame"]), int(s["end_frame"])
        fr = list(range(f0, f1 + 1, step))
        if fr[-1] != f1:
            fr.append(f1)
        for f in fr:
            plan[f] = (s["pose"], ramp(f, f0, f1, blend))
    for s in segs:
        for f in (int(s["start_frame"]) - step, int(s["end_frame"]) + step):
            if 0 <= f <= end_f and not any(int(o["start_frame"]) <= f <= int(o["end_frame"]) for o in segs):
                plan[f] = (None, 0.0)
    frames = sorted(plan)
    now = RLPy.RGlobal.GetTime()
    _clear_layers(sk, bones, frames[0], frames[-1])
    base = _sample_local(bones, frames)
    keyed = 0
    for i, f in enumerate(frames):
        t = fps.IndexedFrameTime(f)
        clip = sk.GetClipByTime(t)
        if clip is None:
            continue
        ct = clip.SceneTimeToClipTime(t)
        pose, w = plan[f]
        for b in bones:
            n = b.GetName()
            off = (0.0, 0.0, 0.0, 1.0) if pose is None else layer_offset(targets[pose][n], base[n][i], w)
            key = RLPy.RTransformKey()
            key.SetTime(ct)
            key.SetTransform(RLPy.RTransform(RLPy.RVector3(1, 1, 1), RLPy.RQuaternion(RLPy.RVector4(*off)),
                                             RLPy.RVector3(0, 0, 0)))
            clip.GetControl("Layer", b).AddKey(key)
            keyed += 1
    # verify each segment at its middle (full weight)
    err = 0.0
    for s in segs:
        full = [f for f in frames if plan[f][0] == s["pose"] and plan[f][1] >= 0.999
                and int(s["start_frame"]) <= f <= int(s["end_frame"])]
        if full:
            got = _sample_local(bones, [full[len(full) // 2]])
            err = max([err] + [angle_deg(got[b.GetName()][0], targets[s["pose"]][b.GetName()]) for b in bones])
    RLPy.RGlobal.SetTime(now)
    return {"ok": err < 3.0, "avatar": av.GetName(), "hands": sides, "bones": len(bones), "keys": keyed,
            "poses": [[s["pose"], int(s["start_frame"]), int(s["end_frame"])] for s in segs],
            "max_error_deg": round(err, 2)}


BONE_ALIASES = {"head": "CC_Base_Head", "neck": "CC_Base_NeckTwist01", "chest": "CC_Base_Spine02",
                "spine": "CC_Base_Spine01", "waist": "CC_Base_Waist", "hip": "CC_Base_Hip",
                "r_shoulder": "CC_Base_R_Clavicle", "l_shoulder": "CC_Base_L_Clavicle",
                "r_upperarm": "CC_Base_R_Upperarm", "l_upperarm": "CC_Base_L_Upperarm",
                "r_forearm": "CC_Base_R_Forearm", "l_forearm": "CC_Base_L_Forearm",
                "r_hand": "CC_Base_R_Hand", "l_hand": "CC_Base_L_Hand",
                "r_thigh": "CC_Base_R_Thigh", "l_thigh": "CC_Base_L_Thigh",
                "r_calf": "CC_Base_R_Calf", "l_calf": "CC_Base_L_Calf"}


def body_rotation(fwd, yaw=0.0, pitch=0.0, roll=0.0):
    """World rotation (x, y, z, w) from degrees about the BODY's axes: yaw about up (+ = turn to the character's left,
    like `turn`), pitch about its right-pointing side axis (+ = look up / lean back), roll about its forward axis
    (+ = tilt toward the right shoulder). fwd = horizontal facing (x, y)."""
    side = (fwd[1], -fwd[0], 0.0)                    # the character's right
    f3 = (fwd[0], fwd[1], 0.0)
    q = axis_angle((0.0, 0.0, 1.0), yaw)
    q = qmul(axis_angle(side, pitch), q)
    return qmul(axis_angle(f3, roll), q)


def pose_bones(args):
    """FK posing on top of any clip: rotate named bones by yaw/pitch/roll degrees about the body's own axes over a
    frame range (eased in/out). Additive motion-layer keys, like the laugh."""
    from tools.icmcp_extra import _avatar
    from tools.framing import _facing
    from tools.seating import qrot
    # CLAUDE-NOTE (2026-10-18): the registry's FK-pose gap - the only bone posing was laugh/overlay presets. Axes are
    # the body's (from its hip facing) so "turn the head 30 left" means the same thing whatever the heading; each
    # world rotation is moved into the bone's parent frame because a layer key composes as layer * local.
    av = _avatar(args["avatar"])
    sk = av.GetSkeletonComponent()
    fps = RLPy.RGlobal.GetFps()
    fpsf = fps.ToFloat()
    f0, f1 = int(args["start_frame"]), int(args["end_frame"])
    if f1 <= f0:
        raise ValueError("end_frame must be after start_frame")
    blend = int(round(float(args.get("blend_s", 0.3)) * fpsf))
    step = max(1, int(args.get("step", 2)))
    by = {b.GetName(): b for b in sk.GetSkinBones()}
    anim = {b.GetName() for b in sk.GetAllAnimationBone()}
    want = {}
    for k, v in (args.get("bones") or {}).items():
        n = BONE_ALIASES.get(k, k)
        if n not in by or n not in anim:
            raise ValueError(f"no animatable bone {k!r} (aliases: {sorted(BONE_ALIASES)})")
        want[n] = (float(v.get("yaw", 0)), float(v.get("pitch", 0)), float(v.get("roll", 0)))
    if not want:
        raise ValueError("bones: {name: {yaw, pitch, roll}} needs at least one bone")
    bones = [by[n] for n in want]
    now = RLPy.RGlobal.GetTime()
    _clear_layers(sk, bones, f0, f1)
    frames = list(range(max(0, f0 - step), f1 + step + 1, step))
    mid = (f0 + f1) // 2
    frames = sorted(set(frames + [mid]))
    before = _local_q(bones, mid)       # local: a posed parent in the same call must not count
    keyed = 0
    for f in frames:
        t = fps.IndexedFrameTime(f)
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(t)
        clip = sk.GetClipByTime(t)
        if clip is None:
            continue
        fx, fy, _ = _facing(av)
        w = ramp(f, f0, f1, blend)
        ct = clip.SceneTimeToClipTime(t)
        for b in bones:
            yaw, pitch, roll = want[b.GetName()]
            qw = body_rotation((fx, fy), yaw * w, pitch * w, roll * w)
            pq = _q(b.GetParent().WorldTransform())
            off = qmul(qconj(pq), qmul(qw, pq))          # the same rotation expressed in the parent's frame
            key = RLPy.RTransformKey()
            key.SetTime(ct)
            key.SetTransform(RLPy.RTransform(RLPy.RVector3(1, 1, 1), RLPy.RQuaternion(RLPy.RVector4(*off)),
                                             RLPy.RVector3(0, 0, 0)))
            clip.GetControl("Layer", b).AddKey(key)
            keyed += 1
    after = _local_q(bones, mid)
    rows = {}
    for b in bones:
        n = b.GetName()
        yaw, pitch, roll = want[n]
        expect = angle_deg(body_rotation((0.0, -1.0), yaw, pitch, roll), (0.0, 0.0, 0.0, 1.0))
        got = angle_deg(before[n], after[n])
        rows[n] = {"expected_deg": round(expect, 1), "measured_deg": round(got, 1)}
    RLPy.RGlobal.SetTime(now)
    err = max(abs(r["expected_deg"] - r["measured_deg"]) for r in rows.values())
    return {"ok": err < 4.0, "avatar": av.GetName(), "frames": [f0, f1], "keys": keyed, "bones": rows}


def _local_q(bones, frame):
    fps = RLPy.RGlobal.GetFps()
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(frame + 1))
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(frame))
    return {b.GetName(): _q(b.LocalTransform()) for b in bones}


def register(registry):
    registry["pose_bones"] = {
        "handler": pose_bones, "main_thread": True,
        "description": "FK POSE on top of any clip: bones={name: {yaw, pitch, roll}} in degrees about the BODY's axes "
                       "(yaw + = turn to the character's left, pitch + = look up / lean back, roll + = tilt toward the "
                       "right shoulder) over start_frame..end_frame, eased by blend_s (0.3). Names: CC bones or "
                       "aliases " + ", ".join(sorted(BONE_ALIASES)) + ". E.g. head turn {head: {yaw: 35}}, nod "
                       "{head: {pitch: -15}}, slump {chest: {pitch: -12}}. Replaces earlier layer keys on those "
                       "bones (laugh/overlay) - pose after them only on other bones. Returns expected vs measured deg.",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "bones": {"type": "object"}, "start_frame": {"type": "integer"},
            "end_frame": {"type": "integer"}, "blend_s": {"type": "number"}, "step": {"type": "integer"}},
            "required": ["avatar", "bones", "start_frame", "end_frame"]}}
    registry["hand_pose"] = {
        "handler": hand_pose, "main_thread": True,
        "description": "FINGER POSE on top of any clip: pose " + " | ".join(sorted(HAND_POSES)) + "; hand r | l | "
                       "both; start_frame..end_frame with blend_s ease in/out (default 0.25 s), or a sequence "
                       "poses=[{pose, start_frame, end_frame}, ...] in ONE call (each call replaces that hand's "
                       "earlier poses). Use grip/pinch while holding a prop, point for pointing, fist for anger. "
                       "Motion-layer keys on the finger bones; returns max_error_deg (ok < 3).",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "pose": {"type": "string", "enum": sorted(HAND_POSES)},
            "hand": {"type": "string", "enum": ["r", "l", "both"]}, "start_frame": {"type": "integer"},
            "end_frame": {"type": "integer"}, "poses": {"type": "array", "items": {"type": "object"}},
            "blend_s": {"type": "number"}, "step": {"type": "integer"}},
            "required": ["avatar"]}}
    registry["overlay_clip"] = {
        "handler": overlay_clip, "main_thread": True,
        "description": "Play PART of a clip on top of what the body already does (e.g. texting or gesturing while "
                       "walking): the chosen bones (bones = arm_r | arm_l | arms | head | arm_r_head | arms_head | upper "
                       "| [bone names]) follow `clip` from start_frame to end_frame, blended in/out over blend_s, while "
                       "the rest keeps its clip (an MD walk, an idle). Written as motion-LAYER keys (additive, per clip), "
                       "so the base clip is untouched; re-running replaces the overlay on those bones. clip_offset_s "
                       "starts inside the overlay clip (loops if shorter). Pair with hold_prop for the phone/cup.",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "clip": {"type": "string", "description": "clip path or bare file stem"},
            "start_frame": {"type": "integer"}, "end_frame": {"type": "integer"},
            "bones": {"description": "preset name or a list of bone names"},
            "blend_s": {"type": "number"}, "clip_offset_s": {"type": "number"}, "step": {"type": "integer"}},
            "required": ["avatar", "clip", "start_frame", "end_frame"]}}
    registry["laugh"] = {
        "handler": laugh, "main_thread": True,
        "description": "LAUGH (no stock clip exists): leans back with the head tipped up, a 4-5 Hz chest heave and "
                       "shoulder bounce (motion-layer keys over whatever the body plays - sitting, standing, walking) "
                       "plus a laughing face keyed per frame (smile, squint, mouth opening on each 'ha'; face=false "
                       "to skip). "
                       "start_frame, seconds (2), intensity (1 = a hearty laugh, 0.5 = a chuckle), blend_s.",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "start_frame": {"type": "integer"}, "seconds": {"type": "number"},
            "intensity": {"type": "number"}, "blend_s": {"type": "number"}, "face": {"type": "boolean"}},
            "required": ["avatar", "start_frame"]}}
