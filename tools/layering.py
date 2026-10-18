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


def register(registry):
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
