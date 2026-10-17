"""Groups: arrange people for a conversation and play their (Actor Group) clips.
Tool: group_conversation.
# CLAUDE-NOTE (2026-10-17, measured): Actor Group member clips (Motion Plus/Actor Group/.../3Stand_MMF/*_M1/M2/F1) are
# IN PLACE - loaded on three avatars at the same origin, all hips stayed at (0, 0) facing ~-Y (head yaw -16..+8 deg).
# The group layout is ours to make: members on a circle facing its centre (2 people: face to face).
"""
import math

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

DEFAULT_RADIUS = {2: 55.0, 3: 75.0, 4: 85.0}      # cm; 2 people stand ~110 cm apart (social distance)


def ring(n, center=(0.0, 0.0), radius=None, start_deg=0.0):
    """[(x, y, heading_deg)] for n people on a circle facing its centre. start_deg places member 0 (0 = on the -Y side
    of the centre, i.e. nearest a camera at -Y); members go counter-clockwise. CC front = -Y, so heading =
    atan2(dx, -dy) of the direction to the centre."""
    r = float(radius or DEFAULT_RADIUS.get(n, 60.0 + 10.0 * n))
    out = []
    for i in range(n):
        a = math.radians(start_deg + 360.0 * i / n)
        x, y = center[0] + r * math.sin(a), center[1] - r * math.cos(a)
        dx, dy = center[0] - x, center[1] - y
        out.append((x, y, math.degrees(math.atan2(dx, -dy))))
    return out


def group_conversation(args):
    """members=[{avatar, clip?}] placed on a ring around `at` and (optionally) given their clips, chained to `until_s`."""
    from tools.icmcp_extra import place_object, _avatar
    from tools.common import load_motion_clip
    members = args["members"]
    at = args.get("at", [0.0, 0.0])
    spots = ring(len(members), (float(at[0]), float(at[1])), args.get("radius_cm"), float(args.get("start_deg", 0.0)))
    fps = RLPy.RGlobal.GetFps()
    tick = fps.IndexedFrameTime(1).ToInt()
    until = int(round(float(args["until_s"]) * 6000)) if args.get("until_s") is not None else None
    out = []
    for m, (x, y, hd) in zip(members, spots):
        av = _avatar(m["avatar"])
        place_object({"name": av.GetName(), "frame": 0, "position": {"x": x, "y": y, "z": float(args.get("floor_z", 0))},
                      "rotation_degrees": {"x": 0, "y": 0, "z": hd}})
        row = {"avatar": av.GetName(), "at": [round(x, 1), round(y, 1)], "heading_deg": round(hd, 1), "clips": 0}
        if m.get("clip"):
            path = m["clip"]
            t = int(round(float(args.get("start_s", 0)) * 6000))
            while True:
                clip = load_motion_clip(av, path, RLPy.RTime.FromValue(t), allow_unchanged=True)
                row["clips"] += 1
                clen = clip.GetClipLength().ToInt() if clip else 0
                if until is None or clen <= tick or t + clen >= until:
                    break
                t = t + clen + tick                         # next copy at end + 1 frame
        out.append(row)
    # verification: hips apart and faces toward the centre a little into the clips
    from tools.framing import landmarks, _facing
    f = fps.GetFrameIndex(RLPy.RTime.FromValue(int(round((float(args.get("start_s", 0)) + 1.0) * 6000))))
    now = RLPy.RGlobal.GetTime()
    try:
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
        hips, faced = {}, {}
        for row in out:
            av = _avatar(row["avatar"])
            L = landmarks(av)
            hips[row["avatar"]] = L["hip"]
            fx, fy, _ = _facing(av, "CC_Base_Head")
            cx, cy = float(at[0]) - L["hip"][0], float(at[1]) - L["hip"][1]
            n = math.hypot(cx, cy) or 1.0
            faced[row["avatar"]] = round(math.degrees(math.acos(max(-1.0, min(1.0, (fx * cx + fy * cy) / n)))), 1)
    finally:
        RLPy.RGlobal.SetTime(now)
    names = list(hips)
    gaps = [math.hypot(hips[a][0] - hips[b][0], hips[a][1] - hips[b][1]) for i, a in enumerate(names) for b in names[i + 1:]]
    for row in out:
        row["face_off_centre_deg"] = faced[row["avatar"]]
    return {"ok": (min(gaps) if gaps else 999) > 45.0, "members": out,
            "min_hip_gap_cm": round(min(gaps), 1) if gaps else None, "checked_frame": f}


def register(registry):
    registry["group_conversation"] = {
        "handler": group_conversation, "main_thread": True, "timeout": 600,
        "description": "GROUP CONVERSATION: place members=[{avatar, clip?}] on a ring around `at` [x, y] facing its "
                       "centre (2 people face to face ~110 cm apart; radius_cm, start_deg: 0 = member 0 on the -Y/camera "
                       "side), load each member's clip (e.g. Actor Group 2Stand/3Stand_Chat_* members - they are in-place, "
                       "so the layout is this tool's job) chained until until_s. Returns spacing and how far each head "
                       "points off the centre.",
        "inputSchema": {"type": "object", "properties": {
            "members": {"type": "array", "items": {"type": "object"}}, "at": {"type": "array"},
            "radius_cm": {"type": "number"}, "start_deg": {"type": "number"}, "start_s": {"type": "number"},
            "until_s": {"type": "number"}, "floor_z": {"type": "number"}}, "required": ["members"]}}
