"""Clip-level fixes driven through the Timeline clip menu, measured before and after.

# CLAUDE-NOTE (2026-10-19, measured on _ClipLab Walk Relaxed_1Start -> _2Loop): chained clips can pop at the seam (the
# hip, both feet jumped ~10 cm in one frame). The clip menu's Align > <body part> on the LATER clip moves that clip so
# the part matches the previous clip's last pose: aligning to the planted (left) foot made the seam steps 0.0 / 2.4 /
# 0.8 cm (left foot / right foot / hip) - ordinary walking steps. There is no RLPy call for it, so this goes through
# timeline_clip_action (in-process Qt events on the Timeline).
"""
import math

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

ALIGN_PARTS = {"left_foot": "Left Foot", "right_foot": "Right Foot", "root": "Root", "head": "Head",
               "left_hand": "Left Hand", "right_hand": "Right Hand", "left_toe": "L Toe", "right_toe": "R Toe"}
_TRACK = ("CC_Base_Hip", "CC_Base_L_Foot", "CC_Base_R_Foot")


def planted_foot(left_path, right_path):
    """Which foot is planted over the last frames before a seam: the one that moves less (then the lower one)."""
    def travel(p):
        return sum(math.dist(p[i], p[i + 1]) for i in range(len(p) - 1))
    lt, rt = travel(left_path), travel(right_path)
    if abs(lt - rt) < 0.5:
        return "left_foot" if left_path[-1][2] <= right_path[-1][2] else "right_foot"
    return "left_foot" if lt < rt else "right_foot"


def seam_jump(before, at):
    """Largest one-frame displacement (cm) across the seam among the tracked bones: {bone: point}."""
    return max(math.dist(before[n], at[n]) for n in before)


def window_jump(frames_points):
    """Largest one-frame step over consecutive samples [(frame, {bone: point})] -> (cm, frame it lands on)."""
    best = (0.0, None)
    for (fa, a), (fb, b) in zip(frames_points, frames_points[1:]):
        j = seam_jump(a, b)
        if j > best[0]:
            best = (j, fb)
    return best


def _points(by, f, fps):
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
    out = {}
    for n in _TRACK:
        w = by[n].WorldTransform(); t = w.T()
        out[n] = (t.x, t.y, t.z)
    return out


def align_clip_seams(args):
    from tools.icmcp_extra import _avatar, timeline_clip_action
    av = _avatar(args["avatar"])
    sk = av.GetSkeletonComponent()
    by = {b.GetName(): b for b in sk.GetSkinBones()}
    fps = RLPy.RGlobal.GetFps()
    part = args.get("part", "auto")
    if part != "auto" and part not in ALIGN_PARTS:
        raise ValueError(f"part must be auto or one of {sorted(ALIGN_PARTS)}")
    min_jump = float(args.get("min_jump_cm", 4.0))
    now = RLPy.RGlobal.GetTime()
    rows = []
    for i in range(1, sk.GetClipCount()):
        c = sk.GetClip(i)
        start = fps.GetFrameIndex(c.ClipTimeToSceneTime(RLPy.RTime.FromValue(0)))
        length = fps.GetFrameIndex(c.GetClipLength())
        # CLAUDE-NOTE (2026-10-19, measured): the pop can land one frame after ClipTimeToSceneTime(0) (a trimmed
        # clip's seam read 0.1 cm at start-1 -> start while the 37 cm jump was at start -> start+1): scan a window.
        win = range(start - 3, start + 4)
        jump, at = window_jump([(f, _points(by, f, fps)) for f in win])
        row = {"clip": i, "seam_frame": at if at is not None else start, "jump_before_cm": round(jump, 1)}
        if jump < min_jump:
            row["skipped"] = "seam already smooth"
            rows.append(row)
            continue
        use = part
        if use == "auto":
            tail = [_points(by, f, fps) for f in range(start - 4, start)]
            use = planted_foot([p["CC_Base_L_Foot"] for p in tail], [p["CC_Base_R_Foot"] for p in tail])
        r = timeline_clip_action({"avatar": av.GetName(), "frame": start + max(1, length // 2),
                                  "action": "Align/" + ALIGN_PARTS[use]})
        if not r.get("ok"):
            raise RuntimeError(f"Align/{ALIGN_PARTS[use]} on clip {i} failed: {r.get('error')}")
        row.update({"aligned_to": use,
                    "jump_after_cm": round(window_jump([(f, _points(by, f, fps)) for f in win])[0], 1)})
        rows.append(row)
    RLPy.RGlobal.SetTime(now)
    worst = max([r.get("jump_after_cm", r["jump_before_cm"]) for r in rows], default=0.0)
    return {"ok": worst < float(args.get("tolerance_cm", 5.0)), "avatar": av.GetName(), "seams": rows}


def register(registry):
    registry["align_clip_seams"] = {
        "handler": align_clip_seams, "main_thread": True, "checkpoint": True,
        "description": "REMOVE POPS BETWEEN CHAINED CLIPS: for every clip after the first, measure the one-frame jump "
                       "of the hip and feet at its start; above min_jump_cm (4) run the Timeline clip menu Align > "
                       "<part> on that clip so the part matches the previous clip's last pose. part=auto picks the "
                       "foot planted over the seam (or give left_foot / right_foot / root / head / left_hand / "
                       "right_hand / left_toe / right_toe). Returns jump_before_cm / jump_after_cm per seam (ok when "
                       "every seam < tolerance_cm 5). Measured: 10.3 cm walk-start -> loop pop -> 0.8 cm hip step.",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "part": {"type": "string", "enum": ["auto"] + sorted(ALIGN_PARTS)},
            "min_jump_cm": {"type": "number"}, "tolerance_cm": {"type": "number"}},
            "required": ["avatar"]}}
