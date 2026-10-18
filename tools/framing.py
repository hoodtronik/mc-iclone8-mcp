"""Framing: place a camera by SHOT SIZE from the subjects' real posed bodies (wide, full, medium, close-up, OTS...).
Tool: frame_shot.
# CLAUDE-NOTE (2026-10-16): previz shots were hand-typed camera coordinates, re-guessed after every blocking change and
# easy to get wrong (tiny figures, cut-off heads). frame_shot measures landmarks (head top from the skinned bind mesh,
# chest/waist/knees/soles from bones) at the shot's frame and solves camera distance + aim with a pinhole model so the
# requested landmarks land exactly at the frame edges. iClone's camera: 36 mm film width, AOV is HORIZONTAL (35 mm ->
# 54.43 deg, measured), image height = width / render aspect. Pure math is unit-tested offline.
"""
import math

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

FILM_W = 36.0
# shot size -> (bottom landmark, fraction of frame height the top..bottom span fills, headroom above head top as a
# fraction of frame height, top landmark). "sole"-based sizes keep a margin under the feet.
SIZES = {
    "extreme_wide": ("sole", 0.22, None, "head_top"),
    "wide": ("sole", 0.5, None, "head_top"),
    "full": ("sole", 0.86, 0.07, "head_top"),
    "medium_wide": ("knee", 1.0, 0.07, "head_top"),
    "medium": ("waist", 1.0, 0.07, "head_top"),
    "medium_closeup": ("chest", 1.0, 0.06, "head_top"),
    "closeup": ("collar", 1.0, 0.03, "head_top"),
    "extreme_closeup": ("chin", 1.0, -0.06, "head_top"),
}


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a))
    return _mul(a, 1.0 / n) if n > 1e-9 else a


def camera_basis(pos, aim):
    f = _norm(_sub(aim, pos))
    up = (0.0, 0.0, 1.0) if abs(f[2]) < 0.999 else (0.0, 1.0, 0.0)
    r = _norm(_cross(f, up))
    return f, r, _cross(r, f)


def project(p, pos, aim, lens_mm, aspect):
    """Point -> normalised image coords (x right, y up; frame edges at +-1). None if behind the camera."""
    f, r, u = camera_basis(pos, aim)
    d = _sub(p, pos)
    z = _dot(d, f)
    if z <= 1e-6:
        return None
    half_w = FILM_W / 2.0
    half_h = half_w / aspect
    return (_dot(d, r) * lens_mm / z / half_w, _dot(d, u) * lens_mm / z / half_h)


def solve_framing(top_pts, bottom_pts, all_pts, cam_dir, cam_z, centre, lens_mm, aspect, fill, headroom,
                  h_place=0.0, h_margin=0.08, iters=40, keep_pts=None, keep_ymin=-0.75):
    """Find camera distance d (along -cam_dir from `centre`, horizontal) and aim so that the highest top point sits at
    1 - 2*headroom (normalised y) and the span top..bottom fills `fill` of the frame height; widen if any point leaves
    the frame sideways. cam_dir: horizontal unit vector the camera looks along. Returns (pos, aim, report)."""
    cx, cy, _ = centre
    hd = _norm((cam_dir[0], cam_dir[1], 0.0))
    side = (-hd[1], hd[0], 0.0)                   # image-left in world (camera right = -side)
    top_z = max(p[2] for p in top_pts)
    bot_z = min(p[2] for p in bottom_pts)
    d = max(50.0, (top_z - bot_z) * lens_mm / (FILM_W / aspect) / max(fill, 0.05))
    aim_z = 0.5 * (top_z + bot_z)
    shift = 0.0                                   # sideways aim offset (composition)
    widened = False
    for _ in range(iters):
        pos = (cx - hd[0] * d, cy - hd[1] * d, cam_z)
        aim = (cx + side[0] * shift, cy + side[1] * shift, aim_z)
        ys_top = [project(p, pos, aim, lens_mm, aspect) for p in top_pts]
        ys_bot = [project(p, pos, aim, lens_mm, aspect) for p in bottom_pts]
        if any(v is None for v in ys_top + ys_bot):
            d *= 1.5
            continue
        yt = max(v[1] for v in ys_top)
        yb = min(v[1] for v in ys_bot)
        want_top = 1.0 - 2.0 * headroom if headroom is not None else fill
        want_bot = want_top - 2.0 * fill
        span = yt - yb
        d_v = d * span / (want_top - want_bot)                    # distance scales the projected span ~linearly
        xs = [project(p, pos, aim, lens_mm, aspect) for p in all_pts]
        xs = [v[0] for v in xs if v is not None]
        d_h = 0.0
        if xs:
            mid = (max(xs) + min(xs)) / 2.0
            shift -= (mid - h_place) * d * (FILM_W / 2.0) / lens_mm * 0.9
            room = 2.0 * (1.0 - h_margin) - 2.0 * abs(h_place)
            d_h = d * (max(xs) - min(xs)) / room
        # CLAUDE-NOTE: the frame must satisfy BOTH constraints, so take the larger distance; when width wins the subjects
        # get smaller than the size asked for and we keep the head line (headroom) instead of centring the span.
        d_k = 0.0
        if keep_pts:                                  # e.g. the chin must stay visible in a close-up
            ks = [project(p, pos, aim, lens_mm, aspect) for p in keep_pts]
            yk = min(v[1] for v in ks if v is not None) if any(ks) else keep_ymin
            d_k = d * (yt - yk) / max(yt - keep_ymin, 1e-6)    # distance that puts the point exactly at keep_ymin
        widened = max(d_h, d_k) > d_v * 1.001
        d = max(d_v, d_h, d_k)
        # world cm per normalised-y unit at the subjects' distance (pinhole). CLAUDE-NOTE (2026-10-17, EveningStreet):
        # the old estimate (subject span / projected span) grew without bound once width forced the camera back, and
        # the aim ran 537 m underground (camera 1.1 km away). Clamp aim and distance as a backstop.
        k = d * (FILM_W / aspect / 2.0) / lens_mm
        if widened and headroom is not None:
            aim_z += (yt - want_top) * k * 0.9
        else:
            aim_z += ((yt + yb) / 2.0 - (want_top + want_bot) / 2.0) * k * 0.9
        aim_z = min(max(aim_z, bot_z - 50.0), top_z + 50.0)
        d = min(max(d, 30.0), 20000.0)
    pos = (cx - hd[0] * d, cy - hd[1] * d, cam_z)
    aim = (cx + side[0] * shift, cy + side[1] * shift, aim_z)
    pts = [project(p, pos, aim, lens_mm, aspect) for p in all_pts]
    pts = [v for v in pts if v is not None]
    rep = {"distance_cm": round(d, 1), "widened_to_fit": widened,
           "image_bounds": [round(min(v[0] for v in pts), 3), round(max(v[0] for v in pts), 3),
                            round(min(v[1] for v in pts), 3), round(max(v[1] for v in pts), 3)] if pts else None}
    return pos, aim, rep


# ------------------------------------------------------------------------------------------------------ RLPy side
LANDMARK_BONES = {"head": "CC_Base_Head", "neck": "CC_Base_NeckTwist01", "chest": "CC_Base_Spine02",
                  "waist": "CC_Base_Waist", "hip": "CC_Base_Hip", "l_knee": "CC_Base_L_Calf", "r_knee": "CC_Base_R_Calf",
                  "l_thigh": "CC_Base_L_Thigh", "r_thigh": "CC_Base_R_Thigh", "l_sh": "CC_Base_L_Upperarm",
                  "r_sh": "CC_Base_R_Upperarm", "l_hand": "CC_Base_L_Hand", "r_hand": "CC_Base_R_Hand",
                  "l_foot": "CC_Base_L_Foot", "r_foot": "CC_Base_R_Foot", "l_toe": "CC_Base_L_ToeBase",
                  "r_toe": "CC_Base_R_ToeBase"}
_HEAD_TOP_CACHE = {}


def _head_points_local(av, bone_nodes):
    """Head top (highest bind vertex over the head) and chin (lowest FRONT vertex of the face) in the Head bone's bind
    frame, cached per avatar. Rigid to the head bone, so they follow a bowed/turned head."""
    from tools.seating import _bind_world, _vec, qrot, qconj
    key = av.GetID() if hasattr(av, "GetID") else av.GetName()
    if key not in _HEAD_TOP_CACHE:
        T, Q = _bind_world(bone_nodes["CC_Base_Head"], {})
        verts = [_vec(v) for m in av.GetMeshes() for v in m.GetVertices()]
        near = [v for v in verts if abs(v[0] - T[0]) < 15 and abs(v[1] - T[1]) < 18 and v[2] > T[2]]
        top = max(near, key=lambda v: v[2]) if near else (T[0], T[1], T[2] + 18.0)
        # chin: lowest midline vertex in FRONT of the head bone. CLAUDE-NOTE (2026-10-16, profile of Business_F bind
        # mesh): the face is only 4-6.6 cm in front of CC_Base_Head and the chin sits ~6 cm below it; a 6 cm "front"
        # filter picked the nose and cut chins off close-ups. Under the jaw the profile swings back behind the bone.
        face = [v for v in verts if abs(v[0] - T[0]) < 3 and v[1] < T[1] - 3 and T[2] - 12 < v[2] < T[2] + 2]
        chin = min(face, key=lambda v: v[2]) if face else (T[0], T[1] - 8.0, T[2] - 9.0)
        _HEAD_TOP_CACHE[key] = (qrot(qconj(Q), _sub(top, T)), qrot(qconj(Q), _sub(chin, T)))
    return _HEAD_TOP_CACHE[key]


def landmarks(av):
    """World landmark points of an avatar at the current time."""
    from tools.seating import qrot
    sk = av.GetSkeletonComponent()
    nodes = {b.GetName(): b for b in sk.GetSkinBones()}
    pts = {}
    for k, bn in LANDMARK_BONES.items():
        if bn in nodes:
            wt = nodes[bn].WorldTransform()
            t = wt.T()
            pts[k] = (t.x, t.y, t.z)
            if k == "head":
                q = wt.R()
                pts["_head_q"] = (q.x, q.y, q.z, q.w)
    if "CC_Base_Head" not in nodes or "head" not in pts:
        raise ValueError(f"{av.GetName()} has no CC_Base_Head bone (frame_shot needs a CC3/CC4 skeleton)")
    hq = pts.pop("_head_q")
    top_l, chin_l = _head_points_local(av, nodes)
    pts["head_top"] = _add(pts["head"], qrot(hq, top_l))
    pts["chin"] = _add(pts["head"], qrot(hq, chin_l))
    h = pts["head"]
    pts["collar"] = _mul(_add(pts["neck"], pts["chest"]), 0.5) if "neck" in pts and "chest" in pts else (h[0], h[1], h[2] - 20)
    pts["knee"] = _mul(_add(pts.get("l_knee", h), pts.get("r_knee", h)), 0.5)
    feet = [pts[k] for k in ("l_foot", "r_foot", "l_toe", "r_toe") if k in pts]
    s = min(feet, key=lambda p: p[2]) if feet else (h[0], h[1], 0.0)
    pts["sole"] = (s[0], s[1], max(0.0, s[2] - 8.0))      # foot bone sits ~8-10 cm above the sole
    return pts


def _facing(av, bone="CC_Base_Hip"):
    """Horizontal world direction the avatar's body (or, bone=CC_Base_Head, face) points (CC front = local -Y), from
    the bone's rest-relative turn."""
    from tools.seating import qrot, qconj, qmul, _bind_world
    sk = av.GetSkeletonComponent()
    hip = next(b for b in sk.GetSkinBones() if b.GetName() == bone)
    wt = hip.WorldTransform()
    q = wt.R()
    _, bq = _bind_world(hip, {})
    rel = qmul((q.x, q.y, q.z, q.w), qconj(bq))           # world rotation relative to the rest pose
    f = qrot(rel, (0.0, -1.0, 0.0))
    return _norm((f[0], f[1], 0.0))


def _render_aspect():
    from tools.icmcp_extra import _render_size
    w, h = _render_size()
    return float(w) / float(h)


def smooth(points, window=3):
    """Centered moving average of a list of 3-tuples (ends use the available neighbours)."""
    h = window // 2
    out = []
    for i in range(len(points)):
        seg = points[max(0, i - h): i + h + 1]
        out.append(tuple(sum(p[k] for p in seg) / len(seg) for k in range(3)))
    return out


def occluded(cam, target, others, radius=30.0, body_cm=55.0):
    """True if any other person (2D hip positions) stands between cam and target (within radius of the sight line,
    strictly between them) or the camera is inside a person (closer than body_cm)."""
    cx, cy = cam[0], cam[1]
    tx, ty = target[0], target[1]
    dx, dy = tx - cx, ty - cy
    L = dx * dx + dy * dy
    for ox, oy in others:
        if math.hypot(ox - cx, oy - cy) < body_cm:
            return True
        if L < 1e-6:
            continue
        t = ((ox - cx) * dx + (oy - cy) * dy) / L
        if 0.0 < t < 0.97 and math.hypot(cx + t * dx - ox, cy + t * dy - oy) < radius:
            return True
    return False


def _track_shot(args):
    """Moving camera keyed every track_step_s from `frame` to `through_frame`.
    follow: the camera keeps the first key's world angle and moves with the subjects (smoothed).
    pan: the camera stays at the first key's position and re-aims each key (a tripod pan)."""
    from tools.icmcp_extra import aim_camera, _camera_named
    fps = RLPy.RGlobal.GetFps()
    f0, f1 = int(args["frame"]), int(args["through_frame"])
    step = max(1, int(round(float(args.get("track_step_s", 1.0)) * fps.ToFloat())))
    keys = list(range(f0, f1, step)) + [f1]
    base = {k: v for k, v in args.items() if k not in ("through_frame", "track", "apply", "frame", "samples")}
    # CLAUDE-NOTE (2026-10-18, CafeTrial): the follow angle came from the subject's facing at the FIRST frame; a walker
    # still idling toward the door wall put the camera outside the room (pushed into his chest by `inside`), then he
    # turned and walked away from it. Take the angle from mid-shot, when the subject is under way.
    mid = (f0 + f1) // 2
    ref = frame_shot(dict(base, frame=mid, apply=False))
    if base.get("world_azimuth_deg") is None and base.get("size") != "ots":
        pm, am = ref["position"], ref["target"]
        base["world_azimuth_deg"] = math.degrees(math.atan2(pm[0] - am[0], -(pm[1] - am[1])))
    first = frame_shot(dict(base, frame=f0, apply=False))
    p0, a0 = first["position"], first["target"]
    # CLAUDE-NOTE (2026-10-16, plaza filmstrip): a follow camera in a crowd had passers-by fill the frame (once the
    # camera sat inside someone). Per key, try the base world angle then +-20/+-40 deg until the sight line to the
    # subjects' heads is clear of every other avatar (hip positions at that frame).
    from tools import scene_qa as Q
    subjects = set(base.get("subjects") or [])
    others_av = [a for a in RLPy.RScene.GetAvatars() if a.GetName() not in subjects]
    hips = Q._sample(others_av, keys) if others_av else {}
    sols, swaps = [], 0
    for ki, f in enumerate(keys):
        others = [(h["CC_Base_Hip"][ki][0], h["CC_Base_Hip"][ki][1]) for h in hips.values() if "CC_Base_Hip" in h]
        az0 = base.get("world_azimuth_deg")
        cands = [az0] if az0 is None else [az0 + d for d in (0, 20, -20, 40, -40)]
        pick = None
        for az in cands:
            sol = first if (f == f0 and az == az0) else frame_shot(dict(base, frame=f, apply=False, world_azimuth_deg=az))
            if not occluded(sol["position"], sol["target"], others) and not sol.get("occluded"):
                pick = sol
                break
            pick = pick or sol
        swaps += int(pick is not None and az != az0)
        sols.append(pick)
    if args.get("track") == "pan":
        poss = [tuple(p0)] * len(sols)
    else:
        poss = smooth([tuple(s["position"]) for s in sols])
    aims = smooth([tuple(s["target"]) for s in sols])
    out = {"ok": True, "track": args.get("track"), "keys": keys, "lens_mm": first["lens_mm"], "angle_changes": swaps,
           "positions": [[round(v, 1) for v in p] for p in poss], "targets": [[round(v, 1) for v in a] for a in aims]}
    if args.get("apply", True):
        name = args.get("camera", "Track_" + args.get("size", "medium"))
        cam = _camera_named(name)
        cam.GetControl("Transform").ClearKeys()
        for f, p, a in zip(keys, poss, aims):
            aim_camera({"name": name, "position": {"x": p[0], "y": p[1], "z": p[2]},
                        "target": {"x": a[0], "y": a[1], "z": a[2]}, "focal_length_mm": first["lens_mm"],
                        "frame": f, "hold": False, "make_current": args.get("make_current", True)})
        out["camera"] = name
    return out


def frame_shot(args):
    """Solve and (by default) apply a camera that frames `subjects` at a shot size."""
    # CLAUDE-NOTE (2026-10-16): track=follow|pan keys a moving camera along the shot (walkers leave a static frame).
    if args.get("track") and args.get("through_frame") is not None:
        return _track_shot(args)
    from tools.scene_qa import _avatars
    from tools.icmcp_extra import aim_camera, _t
    fps = RLPy.RGlobal.GetFps()
    frame = int(args.get("frame", fps.GetFrameIndex(RLPy.RGlobal.GetTime())))
    size = args.get("size", "medium")
    if size not in SIZES and size != "ots":
        raise ValueError(f"size must be one of {sorted(SIZES) + ['ots']}")
    # CLAUDE-NOTE (2026-10-16, renders): 35 mm for a medium two-shot put the camera 1 m from faces (wide-angle look);
    # medium and tighter default to 50 mm, wider sizes to 35 mm.
    lens = float(args.get("lens_mm", 35.0 if size in ("extreme_wide", "wide", "full", "medium_wide") else 50.0))
    aspect = _render_aspect()
    # CLAUDE-NOTE (2026-10-16, filmstrip): a static camera solved on ONE frame lost moving subjects later in the shot.
    # through_frame samples the shot (default 5 samples) and frames the union of the poses / worst OTS case.
    end = int(args.get("through_frame", frame))
    n = max(1, int(args.get("samples", 5))) if end > frame else 1
    sample_frames = sorted({frame + round(i * (end - frame) / max(1, n - 1)) for i in range(n)})
    now = RLPy.RGlobal.GetTime()
    try:
        if size == "ots":
            fg, bg = args["over_shoulder_of"], args["subjects"][0]
            avs = {a.GetName(): a for a in _avatars([fg, bg])}
            samples = []
            for f in sample_frames:
                RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
                samples.append((landmarks(avs[fg]), landmarks(avs[bg])))
            return _apply(args, _ots(samples, lens, aspect, args), frame, lens, aim_camera, _t)
        avs = _avatars(args.get("subjects"))
        L, facing = [], []
        # CLAUDE-NOTE (2026-10-16, filmstrip): body facing put a medium close-up behind a turned head; facing="head"
        # averages where the FACES point over the sampled frames.
        fbone = "CC_Base_Head" if args.get("facing") == "head" else "CC_Base_Hip"
        names = {a.GetName() for a in avs}
        others = [a for a in RLPy.RScene.GetAvatars() if a.GetName() not in names]
        occ = []
        for f in sample_frames:
            RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
            L += [landmarks(a) for a in avs]
            for o in others:                              # possible occluders: other people's heads and chests
                try:
                    lm = landmarks(o)
                    occ += [lm["head"], lm["chest"]]
                except Exception:
                    pass
            if f == sample_frames[0] or fbone == "CC_Base_Head":
                facing += [_facing(a, fbone) for a in avs]
    finally:
        RLPy.RGlobal.SetTime(now)
    bottom, fill, headroom, top = SIZES[size]
    # what must fit sideways: close sizes centre on heads (hands/shoulders pulled a close-up off the face in renders)
    all_keys = {"extreme_closeup": ["head_top", "chin", "head"], "closeup": ["head_top", "chin", "head"],
                "medium_closeup": ["head_top", "chin", "l_sh", "r_sh"], "medium": ["head_top", "l_sh", "r_sh", bottom]
                }.get(size, ["head_top", "l_sh", "r_sh", "l_hand", "r_hand", bottom, "l_toe", "r_toe", "l_knee", "r_knee"])
    pts = [p[k] for p in L for k in all_keys if k in p]
    xs = [p["head"][0] for p in L]; ys = [p["head"][1] for p in L]
    centre = (sum(xs) / len(xs), sum(ys) / len(ys), 0.0)
    if args.get("world_azimuth_deg") is not None:
        az = math.radians(float(args["world_azimuth_deg"]))   # direction the CAMERA sits from the subjects; 0 = -Y
        sit = (math.sin(az), -math.cos(az), 0.0)
    else:
        fx = sum(f[0] for f in facing); fy = sum(f[1] for f in facing)
        if math.hypot(fx, fy) < 0.3:             # subjects face each other: shoot the profile two-shot from -Y side
            a, b = L[0]["head"], L[len(avs) - 1]["head"]
            perp = _norm((-(b[1] - a[1]), b[0] - a[0], 0.0))
            sit = perp if perp[1] < 0 else _mul(perp, -1)
        else:
            sit = _norm((fx, fy, 0.0))
        rel = math.radians(float(args.get("azimuth_deg", 0.0)))   # + = camera swings to the subjects' left
        c, s = math.cos(rel), math.sin(rel)
        sit = (c * sit[0] - s * sit[1], s * sit[0] + c * sit[1], 0.0)
    eye_z = sum(p["head"][2] for p in L) / len(L)
    cam_z = float(args["camera_height_cm"]) if args.get("camera_height_cm") is not None else eye_z + float(args.get("height_offset_cm", 0.0))
    place = {"center": 0.0, "left_third": -1.0 / 3.0, "right_third": 1.0 / 3.0}[args.get("placement", "center")]
    # CLAUDE-NOTE (2026-10-16, renders): close-ups showed a ~0.09 frame offset vs the pinhole model at 80 cm (about
    # 1.5 cm of camera pivot/mesh difference; 0.02 at 2.8 m), enough to cut a bowed chin. Keep the chin >= 0.25 above
    # the bottom edge on close sizes instead of trusting the model to the last centimetre.
    keep = [p["chin"] for p in L] if size in ("closeup", "extreme_closeup", "medium_closeup") else None
    # CLAUDE-NOTE (2026-10-17, ParkReal filmstrip): a close-up of one sitter had the other's head filling half the
    # frame. Try the requested angle, then +-20 / +-40 deg, and keep the first whose sight lines to the subjects' faces
    # are clear of other people's heads/chests (3D, 18 cm) over all sampled frames.
    targets = [p[k] for p in L for k in ("head", "chin") if k in p]
    tries = [0.0] if args.get("avoid_occlusion") is False or not occ else [0.0, 20.0, -20.0, 40.0, -40.0]
    best = None
    for d in tries:
        c, s_ = math.cos(math.radians(d)), math.sin(math.radians(d))
        sit_d = (c * sit[0] - s_ * sit[1], s_ * sit[0] + c * sit[1], 0.0)
        pos, aim, rep = solve_framing([p[top] for p in L], [p[bottom] for p in L], pts, _mul(sit_d, -1.0), cam_z,
                                      centre, lens, aspect, fill, headroom, place, keep_pts=keep)
        hit = blocked(pos, targets, occ)
        if best is None:
            best = (pos, aim, rep, d, hit)
        if not hit:
            best = (pos, aim, rep, d, hit)
            break
    pos, aim, rep, d, hit = best
    rep = dict(rep, occlusion_dodge_deg=d, occluded=hit)
    if args.get("inside"):
        room = RLPy.RScene.FindObject(RLPy.EObjectType_Prop, args["inside"])
        if room is None:
            raise ValueError(f"no prop {args['inside']!r} for 'inside'")
        mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
        room.GetBounds(mx, c, mn)
        pos, lens2 = keep_inside(pos, aim, lens, (mn.x, mx.x, mn.y, mx.y, mn.z, mx.z))
        if lens2 != lens:
            rep = dict(rep, moved_inside_room=True, lens_widened_from=lens)
            lens = lens2
    return _apply(args, (pos, aim, rep), frame, lens, aim_camera, _t)


def keep_inside(pos, aim, lens, box, margin=25.0, min_lens=14.0):
    """Interiors: if the camera is outside the room box (shrunk by margin), slide it along the sight line toward the aim
    until inside and widen the lens by the same ratio so the framing holds (down to min_lens). Returns (pos, lens).
    # CLAUDE-NOTE (2026-10-17): a wide shot solved by distance put the camera behind the walls of a Room surface."""
    x0, x1, y0, y1, z0, z1 = box
    x0, x1, y0, y1, z0, z1 = x0 + margin, x1 - margin, y0 + margin, y1 - margin, z0 + margin, z1 - margin

    def inside(p):
        return x0 <= p[0] <= x1 and y0 <= p[1] <= y1 and z0 <= p[2] <= z1
    if inside(pos):
        return pos, lens
    d = _sub(pos, aim)
    lo, hi = 0.0, 1.0                                  # fraction of the aim->camera vector; 0 = at the aim point
    if not inside(aim):
        return pos, lens                               # subject itself outside the room: leave it
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if inside(_add(aim, _mul(d, mid))):
            lo = mid
        else:
            hi = mid
    k = max(lo, 1e-3)
    return _add(aim, _mul(d, k)), max(min_lens, lens * k)


def blocked(cam, targets, occluders, radius=18.0, personal_cm=60.0):
    """True if any occluder point lies within `radius` of a sight line cam -> target (strictly between them), or the
    camera is within `personal_cm` of an occluder (a bystander's head filling the foreground - EveningStreet tracking)."""
    if any(math.dist(cam, o) < personal_cm for o in occluders):
        return True
    for t in targets:
        d = _sub(t, cam)
        L = _dot(d, d)
        if L < 1e-6:
            continue
        for o in occluders:
            k = _dot(_sub(o, cam), d) / L
            if 0.02 < k < 0.95:
                q = _add(cam, _mul(d, k))
                if math.dist(q, o) < radius:
                    return True
    return False


def ots_error(fg, bg, pos, aim, lens, aspect):
    """Cost of one over-the-shoulder camera for one pose sample (0 = clean). None if a key point is behind the camera."""
    dist_fg = math.dist(pos, fg["head"])
    if dist_fg < 55.0:
        return None
    pt, pb = project(bg["head_top"], pos, aim, lens, aspect), project(bg["chest"], pos, aim, lens, aspect)
    pf, pc = project(fg["head"], pos, aim, lens, aspect), project(bg["chin"], pos, aim, lens, aspect)
    if not (pt and pb and pf and pc):
        return None
    # fg head radius on screen (x units); render: at 65 cm his head covered half her face although the head CENTRES
    # were 0.5 apart
    r_fg = 12.0 * lens / dist_fg / (FILM_W / 2.0)
    err = abs((pt[1] - pb[1]) - 1.6)
    err += 2.0 * max(0.0, 0.45 - abs(pf[0])) + 2.0 * max(0.0, abs(pf[0]) - 1.1)
    err += 3.0 * max(0.0, r_fg + 0.25 - abs(pf[0] - pc[0]))
    return err, pf[0]


def _ots(samples, lens, aspect, args):
    """Over-the-shoulder: behind fg's shoulder looking at bg's face; bg framed head-top..chest (medium close-up).
    samples = [(fg landmarks, bg landmarks)] over the shot; the camera is static, so the WORST sample is scored.
    # CLAUDE-NOTE (2026-10-16, renders): a fixed 22 cm shoulder offset put the camera INSIDE a forward-leaning fg head;
    # a camera solved on one frame was fine there but the fg head swung across the face later in the shot. Search over
    # (distance back, side offset) on the first sample's geometry, score each candidate by its worst sample:
    # >= 55 cm from fg's head, fg's head on the near side (|x| 0.45-1.1), clear of bg's face by its on-screen radius
    # + 0.25, bg's head-top..chest span ~= 1.6. fit_error > ~0.3 = no clean OTS for this staging (e.g. side-by-side
    # sitters): pick another angle or shot size."""
    fg0, bg0 = samples[0]
    u = _norm((bg0["head"][0] - fg0["head"][0], bg0["head"][1] - fg0["head"][1], 0.0))
    side = (-u[1], u[0], 0.0)
    sgn = -1.0 if args.get("shoulder", "right") == "right" else 1.0
    cam_z = fg0["head"][2] + float(args.get("height_offset_cm", 6.0))
    aim = (sum(b["head"][0] for _, b in samples) / len(samples), sum(b["head"][1] for _, b in samples) / len(samples),
           sum(0.5 * (b["head_top"][2] + b["chest"][2]) for _, b in samples) / len(samples))
    best = None
    for back in range(20, 420, 5):
        for off in range(10, 95, 5):
            pos = (fg0["head"][0] - u[0] * back + side[0] * sgn * off,
                   fg0["head"][1] - u[1] * back + side[1] * sgn * off, cam_z)
            scored = [ots_error(f, b, pos, aim, lens, aspect) for f, b in samples]
            if any(s is None for s in scored):
                continue
            err = max(s[0] for s in scored)
            if best is None or err < best[0]:
                best = (err, pos, back, off, scored[0][1])
    if best is None:
        raise ValueError("no over-the-shoulder camera found (subjects too close together?)")
    err, pos, back, off, fx = best
    return pos, aim, {"behind_head_cm": back, "side_offset_cm": off, "shoulder": args.get("shoulder", "right"),
                      "fg_head_x": round(fx, 2), "fit_error": round(err, 3), "samples": len(samples)}


def _apply(args, solved, frame, lens, aim_camera, _t):
    pos, aim, rep = solved
    out = {"ok": True, "frame": frame, "lens_mm": lens, "position": [round(v, 1) for v in pos],
           "target": [round(v, 1) for v in aim], **rep}
    if args.get("apply", True):
        name = args.get("camera", "Shot_" + args.get("size", "medium"))
        aim_camera({"name": name, "position": {"x": pos[0], "y": pos[1], "z": pos[2]},
                    "target": {"x": aim[0], "y": aim[1], "z": aim[2]}, "focal_length_mm": lens,
                    "frame": frame, "hold": bool(args.get("hold", True)), "make_current": args.get("make_current", True)})
        out["camera"] = name
    return out


DOF_LOOKS = {"shallow": (20.0, 60.0, 1.0), "medium": (60.0, 150.0, 1.0), "deep": (200.0, 400.0, 0.6)}  # range, transition, blur


def focus_depth(cam_pos, cam_fwd, point):
    """Depth of a point along the camera's view axis (what RCameraDofData.SetFocus wants, in cm)."""
    return _dot(_sub(point, cam_pos), _norm(cam_fwd))


def focus_on(args):
    """Depth of field on a camera, focused on people's heads (or points), with rack focus between keys.
    # CLAUDE-NOTE (2026-10-18, measured on the cafe Est camera, sharpness = Laplacian variance per person): with range
    # 20 / transition 30, FriendA was sharp only at focus 300, FriendB at 400, the barista at ~500 - focus is DEPTH along
    # the view axis in cm, not straight-line distance and not the avatar root (seated roots sit far from the body).
    # RemoveDofKeys does NOT turn blur off (the last state stays); an enabled=False key does.
    """
    from PySide2 import QtWidgets
    from tools.lighting import quat_forward
    cam = RLPy.RScene.FindObject(RLPy.EObjectType_Camera, args["camera"])
    if cam is None:
        raise ValueError(f"camera {args['camera']!r} not found")
    look = args.get("look", "shallow")
    if look not in DOF_LOOKS and look != "off":
        raise ValueError(f"look must be one of {sorted(DOF_LOOKS) + ['off']}")
    rng, trans, blur = DOF_LOOKS.get(look, (0.0, 0.0, 0.0))
    rng, trans = float(args.get("range", rng)), float(args.get("transition", trans))
    keys = args.get("keys") or [{"frame": args.get("frame", 0), "target": args.get("target")}]
    if args.get("through_frame") is not None and len(keys) == 1:
        # CLAUDE-NOTE (2026-10-18, CafeTrial ManWaits): one key at the shot start focused 311 cm out while the man was
        # still walking in; he stopped 123 cm from the lens and stayed blurred. Follow focus = a key every `step`
        # frames on the same target through the shot.
        f0, f1 = int(keys[0].get("frame", 0)), int(args["through_frame"])
        step = max(1, int(args.get("step", 15)))
        keys = [{"frame": f, "target": keys[0].get("target")} for f in sorted(set(list(range(f0, f1, step)) + [f1]))]
    if args.get("replace", True):
        cam.RemoveDofKeys()
    fps = RLPy.RGlobal.GetFps()
    out = []
    for k in keys:
        frame = int(k.get("frame", 0))
        RLPy.RGlobal.SetTime(fps.IndexedFrameTime(frame))
        QtWidgets.QApplication.processEvents()
        tgt = k.get("target")
        point = None
        if isinstance(tgt, (list, tuple)):
            point = tuple(float(v) for v in tgt)
        elif tgt:
            av = next((a for a in RLPy.RScene.GetAvatars() if a.GetName() == tgt), None)
            if av is not None:
                point = landmarks(av)["head"]
            else:
                obj = next((o for o in RLPy.RScene.GetProps() if o.GetName() == tgt), None)
                if obj is None:
                    raise ValueError(f"focus target {tgt!r} is not an avatar or prop")
                t = obj.WorldTransform().T()
                point = (t.x, t.y, t.z)
        elif look != "off":
            raise ValueError("each key needs a target (avatar/prop name or [x,y,z])")
        wt = cam.WorldTransform()
        r, t = wt.R(), wt.T()
        depth = focus_depth((t.x, t.y, t.z), quat_forward(r.x, r.y, r.z, r.w), point) if point else 0.0
        d = RLPy.RCameraDofData()
        d.SetEnable(look != "off")
        d.SetFocus(max(1.0, depth))
        d.SetRange(rng)
        d.SetNearTransitionRegion(trans)
        d.SetFarTransitionRegion(trans)
        d.SetNearBlurScale(float(args.get("blur", blur)))
        d.SetFarBlurScale(float(args.get("blur", blur)))
        key = RLPy.RKey()
        key.SetTime(fps.IndexedFrameTime(frame))
        key.SetTransitionType(RLPy.ETransitionType_Linear)
        if cam.AddDofKey(key, d) != RLPy.RStatus.Success:
            raise RuntimeError(f"iClone could not add a DOF key at frame {frame}")
        row = {"frame": frame, "target": tgt, "focus_cm": round(depth, 1)}
        if point and depth <= 0:
            row["warning"] = "target is behind the camera"
        out.append(row)
    return {"ok": True, "camera": cam.GetName(), "look": look, "range_cm": rng, "transition_cm": trans,
            "keys": out, "dof_key_count": cam.GetDofKeyCount()}


def register(registry):
    registry["focus_on"] = {
        "handler": focus_on, "main_thread": True,
        "description": "DEPTH OF FIELD on a camera, focused on a person's head (avatar name), a prop, or [x,y,z]: "
                       "look shallow (portrait, background melts) | medium | deep | off. Rack focus: keys=[{frame, "
                       "target}, ...] (linear between keys). Focus depth is measured from the posed head at each "
                       "frame. through_frame (+ step, default 15) = FOLLOW FOCUS: keys on the target every step frames up to it (use it "
                       "for anyone who moves). Optional range / transition cm, blur scale. replace=false keeps old keys.",
        "inputSchema": {"type": "object", "properties": {
            "camera": {"type": "string"}, "target": {}, "frame": {"type": "integer"},
            "look": {"type": "string", "enum": sorted(DOF_LOOKS) + ["off"]},
            "keys": {"type": "array", "items": {"type": "object"}}, "range": {"type": "number"},
            "transition": {"type": "number"}, "blur": {"type": "number"}, "replace": {"type": "boolean"},
            "through_frame": {"type": "integer"}, "step": {"type": "integer"}},
            "required": ["camera"]}}
    registry["frame_shot"] = {
        "handler": frame_shot, "main_thread": True,
        "description": "PREVIZ CAMERA BY SHOT SIZE: frame `subjects` (avatar names) as extreme_wide | wide | full | "
        "medium_wide | medium | medium_closeup | closeup | extreme_closeup, or size=ots with over_shoulder_of=<avatar> "
        "(subjects[0] = the face we see). Measures the posed bodies at `frame` (through `through_frame` for a static shot) and solves distance + aim so head top / "
        "cut line land at the frame edges. Angle: azimuth_deg relative to where the subjects face (0 = front, 90 = their "
        "left) or world_azimuth_deg (camera side, 0 = -Y); height_offset_cm from eye level or camera_height_cm; "
        "placement center|left_third|right_third; lens_mm. apply=false returns position/target for build_shot_list.",
        "inputSchema": {"type": "object", "properties": {
            "subjects": {"type": "array", "items": {"type": "string"}}, "size": {"type": "string"},
            "over_shoulder_of": {"type": "string"}, "shoulder": {"type": "string", "enum": ["right", "left"]},
            "frame": {"type": "integer"}, "through_frame": {"type": "integer", "description": "static shot covering "
            "frame..through_frame: frames the union of the poses (OTS: worst case)"}, "samples": {"type": "integer"},
            "track": {"type": "string", "enum": ["follow", "pan"], "description": "with through_frame: a MOVING camera "
            "keyed every track_step_s (follow = moves with the subjects at a fixed world angle; pan = fixed position, "
            "re-aims)"}, "track_step_s": {"type": "number"},
            "inside": {"type": "string", "description": "room prop name: keep the camera inside it (moves in, widens lens)"},
            "avoid_occlusion": {"type": "boolean", "description": "default true: swing +-20/40 deg if other people "
            "block the faces"},
            "lens_mm": {"type": "number"}, "facing": {"type": "string", "enum": ["body", "head"],
            "description": "what azimuth_deg is relative to (default body; head = where faces point)"}, "azimuth_deg": {"type": "number"},
            "world_azimuth_deg": {"type": "number"}, "height_offset_cm": {"type": "number"},
            "camera_height_cm": {"type": "number"}, "placement": {"type": "string"}, "camera": {"type": "string"},
            "apply": {"type": "boolean"}, "hold": {"type": "boolean"}, "make_current": {"type": "boolean"}},
            "required": ["subjects"]}}
