"""Acting beats: chain clips on one character (idle -> turn -> step -> talk ...) so the blocking reads as a sequence.
Tool: perform_sequence.
# CLAUDE-NOTE (2026-10-17): clips loaded with LoadFile at the end of the previous clip + 1 frame CONTINUE from where
# it ended (measured 2026-10-16 on walks), so root-motion beats (Standing Pack 1 turns/steps) accumulate correctly.
# Each action may repeat (`until_s`) or start later (`at_s`, the gap holds the previous clip's last pose).
"""
import math
import os

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

LIB = [os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Documents", "Reallusion", *p) for p in (
    ("Reallusion Templates", "Animation", "Motion"),
    ("Reallusion Templates", "Animation", "Motion Plus"),
    ("Reallusion Templates", "Animation"),
    ("Template", "iClone 7 Template", "iClone Template", "Motion"),
    ("Template", "iClone 7 Template", "iClone Template", "MotionPlus"))]
EXTS = (".rlMotion", ".iMotion", ".iMotionPlus", ".iMotionplus", ".rlmotion", ".imotion", ".imotionplus")


def resolve_clip(name, roots=None):
    """Absolute path, a path relative to a library root, or a bare file stem searched under the roots."""
    if os.path.isfile(name):
        return name
    roots = roots or LIB
    for r in roots:
        for cand in [os.path.join(r, name)] + [os.path.join(r, name + e) for e in EXTS]:
            if os.path.isfile(cand):
                return os.path.normpath(cand)
    stem = os.path.splitext(os.path.basename(name))[0].lower()
    for r in roots:
        for d, _, files in os.walk(r):
            for f in files:
                if os.path.splitext(f)[0].lower() == stem and f.lower().endswith(tuple(e.lower() for e in EXTS)):
                    return os.path.join(d, f)
    raise FileNotFoundError(f"motion clip not found: {name!r}")


def plan(actions, fps, lengths):
    """Pure timing: [(action index, start_frame)] given each action's clip length in frames (lengths[i]).
    Actions run back to back (previous end + 1 frame); at_s starts later (never earlier than the previous end + 1);
    until_s repeats the clip until that time."""
    out, t = [], 0
    for i, a in enumerate(actions):
        if a.get("at_s") is not None:
            t = max(t, int(round(float(a["at_s"]) * fps)))
        n = max(1, int(lengths[i]))
        stop = int(round(float(a["until_s"]) * fps)) if a.get("until_s") is not None else None
        while True:
            out.append((i, t))
            t = t + n + 1
            if stop is None or t >= stop:
                break
    return out


def last_active(rows, move_cm=1.0, turn_deg=2.0):
    """Last frame where the hip moved > move_cm or turned > turn_deg since the previous sample; rows = [(f, x, y, yaw)]."""
    last = None
    for a, b in zip(rows, rows[1:]):
        if math.hypot(b[1] - a[1], b[2] - a[2]) > move_cm or abs(b[3] - a[3]) > turn_deg:
            last = b[0]
    return last


def _last_active_frame(av, t0, n, step=6):
    from tools.framing import _facing
    fps = RLPy.RGlobal.GetFps()
    hip = next(b for b in av.GetSkeletonComponent().GetSkinBones() if b.GetName() == "CC_Base_Hip")
    now = RLPy.RGlobal.GetTime()
    rows = []
    try:
        for f in range(t0, t0 + n + 1, step):
            RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
            w = hip.WorldTransform(); p = w.T(); fc = _facing(av)
            rows.append((f, p.x, p.y, math.degrees(math.atan2(fc[0], -fc[1]))))
    finally:
        RLPy.RGlobal.SetTime(now)
    return last_active(rows)


def continuity_fix(P, yaw_q, hip_next, hip_end, dyaw_deg):
    """New avatar transform (P', yaw quaternion') so that, rotated by dyaw about the vertical through hip_next and moved
    so hip_next lands on hip_end, the next clip starts where the previous one ended. Pure math (z unchanged)."""
    a = math.radians(dyaw_deg)
    c, s = math.cos(a), math.sin(a)
    rx, ry = P[0] - hip_next[0], P[1] - hip_next[1]
    nx = c * rx - s * ry + hip_end[0]
    ny = s * rx + c * ry + hip_end[1]
    from tools.seating import qmul
    qz = (0.0, 0.0, math.sin(a / 2), math.cos(a / 2))
    return (nx, ny, P[2]), qmul(qz, yaw_q)


def _hip_and_yaw(av, f):
    from tools.framing import _facing
    fps = RLPy.RGlobal.GetFps()
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
    hip = next(b for b in av.GetSkeletonComponent().GetSkinBones() if b.GetName() == "CC_Base_Hip")
    w = hip.WorldTransform(); p = w.T(); fc = _facing(av)
    return (p.x, p.y, p.z), math.degrees(math.atan2(fc[0], -fc[1]))


def _carry_over(av, f_end, f_next):
    """Key the avatar so the clip starting at f_next continues the pose at f_end (position + heading).
    # CLAUDE-NOTE (2026-10-17, measured): a clip loaded after another continues the root POSITION but not its
    # ROTATION: two Right_Turn_090 in a row both ended at -98 deg (the 2nd started at -5). Keys on f_end (hold) and
    # f_next (corrected) make the jump within one frame."""
    from tools.icmcp_extra import _t
    fps = RLPy.RGlobal.GetFps()
    h_end, y_end = _hip_and_yaw(av, f_end)
    h_next, y_next = _hip_and_yaw(av, f_next)
    d = (y_end - y_next + 180.0) % 360.0 - 180.0
    if abs(d) < 3.0 and math.hypot(h_end[0] - h_next[0], h_end[1] - h_next[1]) < 3.0:
        return 0.0
    ctrl = av.GetControl("Transform")
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f_end))
    cur = av.LocalTransform()
    ctrl.SetValue(_t(f_end), RLPy.RTransform(cur.S(), cur.R(), cur.T()))           # hold the pose up to f_end
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f_next))
    cur = av.LocalTransform()
    T, Q = cur.T(), cur.R()
    (nx, ny, nz), q = continuity_fix((T.x, T.y, T.z), (Q.x, Q.y, Q.z, Q.w), h_next, h_end, d)
    ctrl.SetValue(_t(f_next), RLPy.RTransform(cur.S(), RLPy.RQuaternion(RLPy.RVector4(*q)), RLPy.RVector3(nx, ny, nz)))
    return round(d, 1)


def perform_sequence(args):
    from tools.icmcp_extra import _avatar
    from tools.common import load_motion_clip
    av = _avatar(args["avatar"])
    fps = RLPy.RGlobal.GetFps()
    F = fps.ToFloat() if hasattr(fps, "ToFloat") else 30.0
    tick = fps.IndexedFrameTime(1).ToInt()
    actions = args["actions"]
    paths = [resolve_clip(a["clip"]) for a in actions]
    placed, lengths, t = [], {}, 0
    proj_end = fps.GetFrameIndex(RLPy.RGlobal.GetProjectLength())
    for i, a in enumerate(actions):
        if a.get("at_s") is not None:
            t = max(t, int(round(float(a["at_s"]) * F)))
        stop = int(round(float(a["until_s"]) * F)) if a.get("until_s") is not None else None
        while True:
            # CLAUDE-NOTE (2026-10-17, measured): HD Idle_M is 41 s long; the next beat landed past the 14 s project end,
            # the playhead clamped there and later loads replaced each other. Refuse instead; `seconds` trims a clip.
            if t >= proj_end:
                raise ValueError(f"action {i} ({os.path.basename(paths[i])}) would start at {t / F:.2f} s, after the "
                                 f"project end ({proj_end / F:.2f} s): trim long clips with 'seconds' or extend the project")
            clip = load_motion_clip(av, paths[i], RLPy.RTime.FromValue(t * tick), allow_unchanged=True)
            n = max(1, int(round(clip.GetClipLength().ToInt() / tick))) if clip else 1
            want = None
            if a.get("seconds") is not None:
                want = int(round(float(a["seconds"]) * F))
            elif a.get("trim", args.get("trim")) == "auto" and clip:
                # CLAUDE-NOTE (2026-10-17, measured): Standing Pack 1 turns/steps are ~10.9 s with the move mid-clip
                # (Right_Turn_090 active 0.2-6.6 s, Step_Forward_Right_Small 4.2-7.6 s). The head cannot be trimmed
                # (RIClip has no start-offset setter); auto trims the idle TAIL 0.5 s after hip motion/rotation stops.
                last = _last_active_frame(av, t, n)
                want = min(n, last - t + int(0.5 * F)) if last is not None else None
            if clip and want is not None and 0 < want < n:
                n = max(1, want)
                clip.SetLength(RLPy.RTime.FromValue(int(round(n * tick * clip.GetSpeed()))))   # crop (same as walk_path)
            lengths[i] = n
            row = {"clip": os.path.basename(paths[i]), "start_s": round(t / F, 2), "seconds": round(n / F, 2)}
            if placed and args.get("carry", True) and t - 1 >= 0:
                row["carried_deg"] = _carry_over(av, t - 1, t)
            placed.append(row)
            t = t + n + 1
            if stop is None or t >= stop:
                break
    return {"ok": True, "avatar": av.GetName(), "placed": placed, "ends_s": round(t / F, 2)}


def register(registry):
    registry["perform_sequence"] = {
        "handler": perform_sequence, "main_thread": True, "timeout": 900,
        "description": "ACTING BEATS: chain clips on one avatar - actions=[{clip, at_s?, until_s?, seconds?}] run back to back "
                       "(end + 1 frame, so root-motion turns/steps accumulate), at_s starts an action later (holding the "
                       "last pose), until_s repeats it, seconds trims a long clip (HD Idle_M is 41 s), trim='auto' (per "
                       "action or for all) cuts the idle tail after the move (Standing Pack clips are ~10.9 s). Refuses "
                       "beats past the project end. clip = path, library-relative path or bare name (e.g. "
                       "'Right_Turn_090', 'Step_Forward_Right_Small' from Standing Pack 1, 'HD Talk_M', 'HD Think_M').",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "actions": {"type": "array", "items": {"type": "object"}},
            "trim": {"type": "string", "enum": ["auto", "none"]},
            "carry": {"type": "boolean", "description": "default true: each beat continues the previous one's heading"}},
            "required": ["avatar", "actions"]}}
