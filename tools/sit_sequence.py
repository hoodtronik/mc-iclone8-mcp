"""Sit down on a seat and (optionally) stand up again: one tool that chains the stock transitions and lands the body on
the seat.

# CLAUDE-NOTE (2026-10-19, measured on _ClipLab, Casual_M_0055):
# - stock rlMotion 'Stand to Sit' moves the hip 41 cm BACK (the person starts in front of the seat) and down to ~50 cm;
#   'Sit to Stand' brings it 38 cm forward again. Both exist for 1.Human Male and 2.Human Female.
# - a MotionPlus seated idle after 'Stand to Sit' restarts at the avatar origin (58 cm seam jump) and sits ~10 cm
#   HIGHER (a different seat height), so even after Align a 17 cm pop remains. The same-library rlMotion idles
#   ('Sit Talk', male 'Relax_Sit') keep the transition's hip height (50 -> 50), so only XY needs aligning.
# - chained clips keep the previous clip's pose only when the Timeline Align moves them (align_clip_seams); any rest
#   is blended with RIClip.SetTransitionRange (17 cm pop -> ~1 cm/frame over 20 frames).
"""
import math

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

LIB = "Reallusion Templates/Animation/Motion/"
CLIPS = {"M": {"stand_to_sit": "1.Human Male/Perform/Stand to Sit.rlMotion",
               "sit_to_stand": "1.Human Male/Perform/Sit to Stand.rlMotion",
               "talk": "1.Human Male/Perform/Sit Talk.rlMotion", "relax": "1.Human Male/Idle/Relax_Sit.rlMotion",
               "stand_idle": "1.Human Male/Idle/Relax.rlMotion"},
         "F": {"stand_to_sit": "2.Human Female/Perform/Stand to Sit.rlMotion",
               "sit_to_stand": "2.Human Female/Perform/Sit to Stand.rlMotion",
               "talk": "2.Human Female/Perform/Sit Talk.rlMotion", "relax": "2.Human Female/Perform/Sit Talk.rlMotion",
               "stand_idle": "2.Human Female/Idle/Female Idle_1.rlMotion"}}


def body_of(name, given=None):
    """'M' / 'F' from an explicit value or a stock-style name (Casual_F_0019, Business_M_0001)."""
    if given in ("M", "F"):
        return given
    for tag, b in (("_F_", "F"), ("_M_", "M"), ("Female", "F"), ("Male", "M")):
        if tag in (name or ""):
            return b
    raise ValueError(f"can't tell the body type of {name!r}: pass body 'M' or 'F'")


def plan_clips(sit_f, stand_f, end_f, lens):
    """Clip layout [(kind, start_frame, length_frames)] for: standing idle until sit_f, stand_to_sit, seated idle
    (looped, last copy trimmed) until stand_f (or end_f), sit_to_stand, standing idle to end_f. lens: frames per kind."""
    out = []
    if sit_f > 2:
        out.append(("stand_idle", 0, sit_f))
    t = sit_f
    out.append(("stand_to_sit", t, lens["stand_to_sit"]))
    t += lens["stand_to_sit"]
    until = stand_f if stand_f is not None else end_f
    while t < until:
        n = min(lens["idle"], until - t)
        out.append(("idle", t, n))
        t += n
    if stand_f is not None:
        out.append(("sit_to_stand", t, lens["sit_to_stand"]))
        t += lens["sit_to_stand"]
        if t < end_f:
            out.append(("stand_idle", t, end_f - t))
    return out


def lift_keys(sit_f, sat_f, stand_f, up_f, dz):
    """Vertical offset keys [(frame, dz)] that put the seated body dz higher/lower ONLY while seated: 0 until the sit
    starts, dz once seated, back to 0 once standing (stand_f None = stays seated)."""
    keys = [(0, 0.0), (sit_f, 0.0), (sat_f, dz)]
    if stand_f is not None:
        keys += [(stand_f, dz), (up_f, 0.0)]
    return keys


def front_shift(stand_hips, contact, front, clear=12.0, keep_in=8.0):
    """How far (cm, >= 0) to slide a sit sequence toward the seat's front edge. Positions are distances along the
    facing direction: stand_hips = the standing hip (before / after), contact = seated contact, front = the seat's front
    edge. Enough for every standing hip to be `clear` past the edge, capped so the contact stays keep_in inside it."""
    need = max([0.0] + [clear - (h - front) for h in stand_hips])
    room = max(0.0, (front - keep_in) - contact)
    return min(need, room)


def _shift_keys(ctrl, dx, dy):
    """Move every transform key of a control by (dx, dy) cm: the whole performance moves, headings kept."""
    for i in range(ctrl.GetKeyCount()):
        k = RLPy.RTransformKey()
        ctrl.GetTransformKeyAt(i, k)
        tr = k.GetTransform()
        T = tr.T()
        ctrl.SetValueAt(i, RLPy.RTransform(tr.S(), tr.R(), RLPy.RVector3(T.x + dx, T.y + dy, T.z)))


def _key_lift(av, ctrl, fps, f, dz):
    """Key the avatar's current transform at frame f raised to z=dz (linear), keeping its position and heading."""
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
    cur = av.LocalTransform()
    T = cur.T()
    t = fps.IndexedFrameTime(f)
    ctrl.SetValue(t, RLPy.RTransform(cur.S(), cur.R(), RLPy.RVector3(T.x, T.y, dz)))
    ctrl.SetKeyTransition(t, RLPy.ETransitionType_Linear, 50.0)


def _frames(t):
    return RLPy.RGlobal.GetFps().GetFrameIndex(t)


def sit_sequence(args):
    import os
    from tools.icmcp_extra import _avatar
    from tools.common import load_motion_clip, euler_degrees_to_quaternion
    from tools.fight_tools import _delete_all_clips
    from tools.seating import fit_sitter, _seat_info
    from tools.clip_ops import align_clip_seams
    av = _avatar(args["avatar"])
    sk = av.GetSkeletonComponent()
    fps = RLPy.RGlobal.GetFps()
    fpsf = fps.ToFloat()
    body = body_of(args.get("avatar_file") or av.GetName(), args.get("body"))
    idle = args.get("idle", "talk")
    if idle not in ("talk", "relax"):
        raise ValueError("idle must be talk or relax")
    from tools.icmcp_extra import CONTENT_ROOT
    paths = {k: os.path.join(CONTENT_ROOT, LIB, v) for k, v in CLIPS[body].items()}
    paths["idle"] = paths[idle]
    end_f = _frames(RLPy.RGlobal.GetProjectLength())
    sit_f = int(round(float(args.get("sit_at_s", 1.0)) * fpsf))
    stand_f = int(round(float(args["stand_at_s"]) * fpsf)) if args.get("stand_at_s") is not None else None
    turn = float(args.get("turn", 0.0))
    seat = args["seat"]
    # 1. clips: load each kind once to learn its length
    _delete_all_clips(sk)
    lens = {}
    for k in ("stand_to_sit", "idle", "sit_to_stand"):
        c = load_motion_clip(av, paths[k], fps.IndexedFrameTime(0))
        lens[k] = _frames(c.GetClipLength())
        _delete_all_clips(sk)
    ctrl = av.GetControl("Transform")
    W = av.WorldTransform(); T0 = W.T()
    q = euler_degrees_to_quaternion(0, 0, turn)
    ctrl.ClearKeys()
    plan = plan_clips(sit_f, stand_f, end_f, lens)
    if stand_f is not None and stand_f < sit_f + lens["stand_to_sit"] + 10:
        raise ValueError(f"stand_at_s is too early: sitting down takes {lens['stand_to_sit'] / fpsf:.1f} s")
    if plan[-1][1] + plan[-1][2] > end_f + 1:
        raise ValueError(f"the sequence runs past the project end ({end_f / fpsf:.1f} s): standing up takes "
                         f"{lens['sit_to_stand'] / fpsf:.1f} s (sitting down {lens['stand_to_sit'] / fpsf:.1f} s) - "
                         f"stand up by {(end_f - lens['sit_to_stand']) / fpsf:.1f} s or lengthen the project")
    for kind, f0, n in plan:
        c = load_motion_clip(av, paths[kind], fps.IndexedFrameTime(f0))
        if n < _frames(c.GetClipLength()):
            c.SetLength(fps.IndexedFrameTime(n))
    # 2. face `turn` at the current spot, then fix the seams (Align to the planted foot, blend the rest)
    ctrl.SetValue(fps.IndexedFrameTime(0), RLPy.RTransform(RLPy.RVector3(1, 1, 1), q, RLPy.RVector3(T0.x, T0.y, 0.0)))
    seams = align_clip_seams({"avatar": av.GetName(), "min_jump_cm": 3.0})["seams"]
    blend = int(round(float(args.get("blend_s", 0.5)) * fpsf))
    for sm in seams:
        if sm.get("jump_after_cm", 0.0) > 3.0:
            sk.GetClip(sm["clip"]).SetTransitionRange(fps.IndexedFrameTime(blend))
            sm["blended_frames"] = blend
    # 3. land the seat contact on the seat: measure while seated, shift the whole body in XY
    sat_f = sit_f + lens["stand_to_sit"]
    m_end = (stand_f if stand_f is not None else end_f) - 2
    probe = {"avatar": av.GetName(), "seat": seat, "apply": False, "start_frame": sat_f + 5,
             "end_frame": max(sat_f + 6, min(m_end, sat_f + 90)), "samples": 6}
    r = fit_sitter(probe)
    _, rect = _seat_info({"seat": seat})
    fx, fy = -math.sin(math.radians(turn)), -math.cos(math.radians(turn))    # turn 0 faces -Y
    back = float(args.get("seat_back_cm", 0.0))           # + = sit further back on the seat
    want = ((rect[0] + rect[1]) / 2.0 - fx * back, (rect[2] + rect[3]) / 2.0 - fy * back)
    got = r["contact_point_xy"]
    _shift_keys(ctrl, want[0] - got[0], want[1] - got[1])
    # CLAUDE-NOTE (2026-10-19, WaitingRoom render): the female Sit to Stand brings the hip only ~28 cm forward, so with
    # the contact on the seat centre she stood with her legs inside the seat. Slide the whole sequence toward the
    # front edge until the standing hip (before sitting and after standing) clears it - never so far that the seated
    # contact gets within 8 cm of that edge.
    corners = [(x, y) for x in rect[:2] for y in rect[2:]]
    front = max(cx * fx + cy * fy for cx, cy in corners)
    hipb = next(b for b in sk.GetSkinBones() if b.GetName() == "CC_Base_Hip")
    stands = [sit_f] + ([stand_f + lens["sit_to_stand"] - 1] if stand_f is not None else [])
    stands = [f for f in stands if f <= end_f]
    hips = []
    for f in stands:
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
        w = hipb.WorldTransform(); t = w.T()
        hips.append((t.x, t.y))
    shift = front_shift([h[0] * fx + h[1] * fy for h in hips], want[0] * fx + want[1] * fy, front,
                        float(args.get("stand_clear_cm", 12.0)))
    if shift > 0:
        _shift_keys(ctrl, fx * shift, fy * shift)
    # 4. height: the clip sits at its own seat height; offset only the seated span (feet move by the same amount)
    r = fit_sitter(probe)
    dz = float(r["dz_cm"])
    up_f = (stand_f + lens["sit_to_stand"] // 2) if stand_f is not None else None
    down_f = sit_f + int(lens["stand_to_sit"] * 0.6)
    if abs(dz) >= 0.5:
        for f, z in lift_keys(down_f, sat_f, stand_f, up_f, dz)[1:]:
            _key_lift(av, ctrl, fps, f, z)
    feet = {}
    if abs(dz) >= 2.0:
        # CLAUDE-NOTE (2026-10-19, measured): the stock transitions sit at a ~34 cm seat (Casual_M_0055); on a 45 cm
        # seat the lifted body left the feet 11 cm in the air. Each foot reaches back down to the floor (a hidden
        # target dz below where it is while seated) for the seated span, so the knees open instead.
        from tools.ik_pose import _foot_by_reach
        mid = (sat_f + (stand_f if stand_f is not None else end_f)) // 2
        hold_end = stand_f if stand_f is not None else end_f
        ramp = max(1, sat_f - down_f) / fpsf
        by = {b.GetName(): b for b in sk.GetSkinBones()}
        for which, bn in (("left_foot", "CC_Base_L_Foot"), ("right_foot", "CC_Base_R_Foot")):
            RLPy.RGlobal.SetTime(fps.IndexedFrameTime(mid + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(mid))
            w = by[bn].WorldTransform(); t = w.T()
            g = (t.x, t.y, t.z - dz)
            fr = _foot_by_reach(av, which, g, sat_f / fpsf, (hold_end - sat_f) / fpsf, ramp, by[bn], fps, 4.0)
            feet[which] = fr["effector_to_goal_cm"]
    r = fit_sitter(probe)
    out = {"ok": True, "avatar": av.GetName(), "body": body, "clips": [list(x) for x in plan],
           "seams": seams, "turn": turn, "sit_frame": sit_f,
           "seat_height_offset_cm": round(dz, 1), "contact_z_now": r["contact_z_now"],
           "contact_point_xy": r["contact_point_xy"], "seat_top_cm": r["seat_top_cm"],
           "contact_inside_seat": r.get("contact_inside_seat")}
    if feet:
        out["feet_pinned_to_floor_cm"] = feet
    if abs(dz) > 15.0:
        out["advice"] = (f"the seat is {dz:+.0f} cm off the height these clips sit at ({r['seat_top_cm'] - dz:.0f} cm); "
                         f"the legs cannot make up that much - use a seat nearer that height")
    worst = max([s.get("jump_after_cm", s["jump_before_cm"]) if not s.get("blended_frames") else 0.0 for s in seams],
                default=0.0)
    feet_ok = all(max(v) < 6.0 for v in feet.values())
    out["ok"] = bool(r.get("contact_inside_seat", True)) and worst < 5.0 and abs(dz) <= 15.0 and feet_ok
    return out


def register(registry):
    registry["sit_sequence"] = {
        "handler": sit_sequence, "main_thread": True, "checkpoint": True, "timeout": 300,
        "description": "SIT DOWN (and optionally STAND UP) on a seat prop with the stock transitions: standing idle -> "
                       "Stand to Sit at sit_at_s -> seated idle (talk | relax; same library, so the hip height matches) "
                       "-> Sit to Stand at stand_at_s -> standing idle. REPLACES the avatar's clips and transform keys. "
                       "turn = the way the sitter faces (0 = -Y). The body is placed so its measured seat contact lands "
                       "on the seat centre (seat_back_cm moves it back), seams are aligned and blended, and a seat "
                       "higher/lower than the clip's (~34 cm for the stock M) is met by lifting only the seated span while both feet reach back to the floor (up to 15 cm). body M/F from the avatar "
                       "name or `body`. Returns contact height vs seat_top_cm and per-seam jumps.",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "seat": {"type": "string"}, "turn": {"type": "number"},
            "sit_at_s": {"type": "number"}, "stand_at_s": {"type": "number"}, "idle": {"type": "string", "enum": ["talk", "relax"]},
            "body": {"type": "string", "enum": ["M", "F"]}, "avatar_file": {"type": "string"},
            "seat_back_cm": {"type": "number"}, "blend_s": {"type": "number"}},
            "required": ["avatar", "seat"]}}
