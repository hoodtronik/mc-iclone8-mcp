"""Seating: fit a seated character to a seat from its real (posed) body surface, not from bone heights.
Tool: fit_sitter.
# CLAUDE-NOTE (2026-10-16): bone heights alone mis-fit sitters by ~5 cm (measured on the park bench: male Sit Talk
# sank 4 cm into the seat with his feet 8 cm in the air, female sat 0.5 cm proud — same bones, different clips and
# bodies). RLPy has no deformed-vertex API (RIMesh.GetVertices returns the BIND pose, object space), so we rigidly skin
# the lower-body vertices ourselves: each bind vertex is attached to its nearest leg/pelvis bone segment. Bind bone
# frames = BasisTransform (parent-relative rest pose) composed down from RL_BoneRoot; posed frames = skin-bone
# WorldTransform (convention verified live: child.T == parent.T + parent.R * child.Basis.T to 0.1 cm).
# Do NOT use RISkeletonComponent.GetBoneTPosePosition: it returned the CURRENT posed world positions for one avatar.
# The math is pure python (no numpy, no RLPy) so it is unit-tested offline.
"""
import math

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

HIP = "CC_Base_Hip"
# (frame bone, segment from, segment to, role). Vertices bind to the nearest segment and move with the frame bone.
# role "seat" = surfaces that rest on a seat, "sole" = surfaces that stand on the floor.
SEGMENTS = [
    ("CC_Base_Pelvis", "CC_Base_Hip", "CC_Base_Waist", "seat"),
    ("CC_Base_L_Thigh", "CC_Base_L_Thigh", "CC_Base_L_Calf", "seat"),
    ("CC_Base_R_Thigh", "CC_Base_R_Thigh", "CC_Base_R_Calf", "seat"),
    ("CC_Base_L_Calf", "CC_Base_L_Calf", "CC_Base_L_Foot", "leg"),
    ("CC_Base_R_Calf", "CC_Base_R_Calf", "CC_Base_R_Foot", "leg"),
    ("CC_Base_L_Foot", "CC_Base_L_Foot", "CC_Base_L_ToeBase", "sole"),
    ("CC_Base_R_Foot", "CC_Base_R_Foot", "CC_Base_R_ToeBase", "sole"),
    ("CC_Base_L_ToeBase", "CC_Base_L_ToeBase", "CC_Base_L_ToeBase", "sole"),
    ("CC_Base_R_ToeBase", "CC_Base_R_ToeBase", "CC_Base_R_ToeBase", "sole"),
]
BONES = sorted({b for s in SEGMENTS for b in s[:3]})
# CLAUDE-NOTE (2026-10-16): calibrated live on two bodies/clips (Business M + Sit Talk, Rahera F + Sit Talk): after a
# fit the eye-level render showed both hovering 2.0-2.4 cm above the seat, i.e. rigid+blend skinning reads the seated
# underside ~2.2 cm too low (real LBS keeps more volume under the hips). Soles needed no correction (female read 0.0).
SEAT_BIAS_CM = 2.2


# ----------------------------------------------------------------------------------------------- pure vector helpers
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


def _median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def qrot(q, v):
    """Rotate v by unit quaternion q = (x, y, z, w) (RLPy RQuaternion order)."""
    u, w = q[:3], q[3]
    uv = _cross(u, v)
    return _add(v, _add(_mul(uv, 2 * w), _mul(_cross(u, uv), 2)))


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def qconj(q):
    return (-q[0], -q[1], -q[2], q[3])


def compose(parent, local):
    """World (T, Q) of a child from its parent's world (T, Q) and its parent-relative (T, Q); unit scale."""
    pT, pQ = parent
    lT, lQ = local
    return _add(pT, qrot(pQ, lT)), qmul(pQ, lQ)


def seg_dist(p, a, b):
    """Distance from point p to segment a-b."""
    ab = _sub(b, a)
    L = _dot(ab, ab)
    t = 0.0 if L < 1e-9 else max(0.0, min(1.0, _dot(_sub(p, a), ab) / L))
    d = _sub(p, _add(a, _mul(ab, t)))
    return math.sqrt(_dot(d, d))


def _seg_t(p, a, b):
    ab = _sub(b, a)
    L = _dot(ab, ab)
    return 0.0 if L < 1e-9 else _dot(_sub(p, a), ab) / L


def bind_lower_body(verts, bind, max_dist=24.0, max_abs_x=26.0, above_hip=12.0, blend=(-0.05, 0.4)):
    """Attach bind-pose vertices to their nearest SEGMENTS. bind = {bone: (T, Q)} in mesh object space.
    Returns [(role, [(bone, weight, coords in that bone's frame)])]. Thigh vertices near the hip joint blend between
    the pelvis and the thigh by position along the thigh (t in `blend` -> weight 0..1), like the real skin weights:
    rigid thigh skinning swung the back-of-hip vertices ~10 cm below the true seated buttocks (measured 10-16).
    Excludes upper body (z > hip + above_hip), hands/arms (|x| > max_abs_x: A-pose hands hang beside the thighs) and
    anything farther than max_dist from every segment."""
    segs = [s for s in SEGMENTS if all(b in bind for b in s[:3])]
    top = bind[HIP][0][2] + above_hip
    pelvis = SEGMENTS[0][0]

    def local(bone, v):
        T, Q = bind[bone]
        return qrot(qconj(Q), _sub(v, T))

    out = []
    for v in verts:
        if v[2] > top or abs(v[0]) > max_abs_x:
            continue
        best = min(segs, key=lambda s: seg_dist(v, bind[s[1]][0], bind[s[2]][0]))
        if seg_dist(v, bind[best[1]][0], bind[best[2]][0]) > max_dist:
            continue
        w = 1.0
        if best[0] in ("CC_Base_L_Thigh", "CC_Base_R_Thigh") and pelvis in bind:
            t = _seg_t(v, bind[best[1]][0], bind[best[2]][0])
            w = max(0.0, min(1.0, (t - blend[0]) / (blend[1] - blend[0])))
        infl = [(best[0], w, local(best[0], v))]
        if w < 1.0:
            infl.append((pelvis, 1.0 - w, local(pelvis, v)))
        out.append((best[3], infl))
    return out


def posed_surface(bound, posed):
    """World positions of bound vertices for one posed skeleton {bone: (T, Q)} -> {role: [points]}."""
    out = {"seat": [], "leg": [], "sole": []}
    for role, infl in bound:
        p = (0.0, 0.0, 0.0)
        for bone, w, q in infl:
            T, Q = posed[bone]
            p = _add(p, _mul(_add(T, qrot(Q, q)), w))
        out[role].append(p)
    return out


def seat_contact(points, seat_rect=None):
    """Lowest seat-surface point, optionally only over the seat footprint (xmin, xmax, ymin, ymax)."""
    if seat_rect:
        x0, x1, y0, y1 = seat_rect
        inside = [p for p in points if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]
        points = inside or points
    return min(points, key=lambda p: p[2]) if points else None


def plan_fit(contacts, soles, seat_top=None, floor=0.0, mode="seat", tol=2.5):
    """Decide the vertical shift for a sitter. contacts/soles: per-frame lowest seat-surface / sole z (cm).
    mode 'seat' (default; a sitter hovering over or sinking into a seat reads worse than a small foot gap) rests the
    body on the seat; 'feet' puts the soles on the floor. Both report the other error and, beyond tol, advice to set
    the seat to the height the clip was authored for."""
    c, s = _median(contacts), _median(soles)
    authored = c - s                                 # seat height this clip expects when the feet are on the floor
    if seat_top is None or mode == "feet":
        dz, used = floor - s, "feet"
    else:
        dz, used = seat_top - c, "seat"
    res = {"dz_cm": round(dz, 1), "mode_used": used, "authored_seat_height_cm": round(authored - floor, 1),
           "contact_z_range": [round(min(contacts) + dz, 1), round(max(contacts) + dz, 1)],
           "sole_z_after": round(s + dz - floor, 1)}
    if seat_top is not None:
        res["seat_gap_after_cm"] = round(c + dz - seat_top, 1)      # + = hovering, - = sinking
        mismatch = (seat_top - floor) - authored
        res["seat_mismatch_cm"] = round(mismatch, 1)
        if abs(mismatch) > tol:
            res["advice"] = (f"clip expects a {authored - floor:.0f} cm seat but the seat is {seat_top - floor:.0f} cm: "
                             f"feet will be {'off' if mismatch > 0 else 'in'} the floor by {abs(mismatch):.0f} cm. "
                             f"Set the seat top to {authored:.0f} cm (best) or pick a clip authored for this height.")
    return res


# ------------------------------------------------------------------------------------------------------ RLPy side
def _vec(v):
    return (v.x, v.y, v.z)


def _find_avatar(name):
    for a in RLPy.RScene.GetAvatars():
        if a.GetName() == name:
            return a
    raise ValueError(f"no avatar {name!r}")


def _tq(t):
    T, Q = t.T(), t.R()          # t must be held by the caller (dangling SWIG ref otherwise)
    return (T.x, T.y, T.z), (Q.x, Q.y, Q.z, Q.w)


def _bind_world(node, memo):
    """Rest-pose (T, Q) of a bone in mesh object space: BasisTransforms composed down from the skeleton root."""
    name = node.GetName()
    if name not in memo:
        b = node.BasisTransform()
        local = _tq(b)
        parent = node.GetParent()
        memo[name] = compose(_bind_world(parent, memo), local) if parent else local
    return memo[name]


def _bind_data(av):
    sk = av.GetSkeletonComponent()
    bones = {b.GetName(): b for b in sk.GetSkinBones() if b.GetName() in BONES}
    missing = set(BONES) - set(bones)
    if missing:
        raise ValueError(f"{av.GetName()} lacks CC bones {sorted(missing)} (fit_sitter needs a CC3/CC4 skeleton)")
    memo = {}
    bind = {n: _bind_world(b, memo) for n, b in bones.items()}
    verts = [_vec(v) for m in av.GetMeshes() for v in m.GetVertices()]
    return bones, bind, verts


def seat_from_vertices(verts, front=0.6, band=6.0, min_share=0.12):
    """Seat surface of an upright seat prop from its LOCAL vertices (front = -Y, like characters): the highest z band
    (band cm thick) holding >= min_share of the vertices in the front `front` part of the depth. Returns
    (top_z, (x0, x1, y0, y1)) local, or None. Armrests/backrests are too sparse or behind the front part.
    # CLAUDE-NOTE (2026-10-17): a real bench's bounds top is its BACKREST (Classic Park Bench_01: 87.5 cm), not the
    # seat (~43 cm); measured band layout: legs z 0-4, seat slats z 32-44 across y -35..22, backrest above 44 at rear."""
    if not verts:
        return None
    ys = [v[1] for v in verts]
    y0, y1 = min(ys), max(ys)
    fr = [v for v in verts if v[1] <= y0 + front * (y1 - y0)]
    if not fr:
        return None
    zs = sorted(v[2] for v in fr)
    need = max(3, int(min_share * len(fr)))
    for top in reversed(zs):
        if sum(1 for z in zs if top - band <= z <= top) >= need:
            seat = [v for v in fr if top - band <= v[2] <= top]
            return top, (min(v[0] for v in seat), max(v[0] for v in seat), y0, y0 + front * (y1 - y0))
    return None


def _seat_info(args):
    if args.get("seat"):
        obj = RLPy.RScene.FindObject(RLPy.EObjectType_Prop, args["seat"])
        if not obj:
            raise ValueError(f"no prop {args['seat']!r}")
        mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
        obj.GetBounds(mx, c, mn)
        verts = [_vec(v) for m in (obj.GetMeshes() if hasattr(obj, "GetMeshes") else []) for v in m.GetVertices()]
        found = seat_from_vertices(verts) if args.get("seat_surface", "auto") == "auto" else None
        if found and found[0] < (mx.z - mn.z) * 0.9:
            # local -> world for an upright prop: scale, then yaw/rotation, then translation
            wt = obj.WorldTransform()
            T, Q, S = wt.T(), wt.R(), wt.S()
            q = (Q.x, Q.y, Q.z, Q.w)
            top, (x0, x1, y0, y1) = found
            corners = [_add((T.x, T.y, T.z), qrot(q, (x * S.x, y * S.y, top * S.z))) for x in (x0, x1) for y in (y0, y1)]
            return (sum(c[2] for c in corners) / 4.0,
                    (min(c[0] for c in corners), max(c[0] for c in corners), min(c[1] for c in corners), max(c[1] for c in corners)))
        return mx.z, (mn.x, mx.x, mn.y, mx.y)
    if args.get("seat_height_cm") is not None:
        return float(args["seat_height_cm"]), None
    return None, None


def measure_sitter(av, frames):
    bones, bind, verts = _bind_data(av)
    bound = bind_lower_body(verts, bind)
    fps = RLPy.RGlobal.GetFps()
    now = RLPy.RGlobal.GetTime()
    per = []
    try:
        for f in frames:
            RLPy.RGlobal.SetTime(fps.IndexedFrameTime(int(f)))
            posed = {}
            for n, b in bones.items():
                wt = b.WorldTransform()
                posed[n] = _tq(wt)
            per.append(posed_surface(bound, posed))
    finally:
        RLPy.RGlobal.SetTime(now)
    return per, len(bound)


def fit_sitter(args):
    """Measure a seated avatar's body surface over a frame range and (optionally) shift it so it rests on the seat."""
    av = _find_avatar(args["avatar"])
    fps = RLPy.RGlobal.GetFps()
    s = int(args.get("start_frame", 0))
    e = int(args.get("end_frame", min(fps.GetFrameIndex(RLPy.RGlobal.GetProjectLength()), s + 300)))
    n = max(2, int(args.get("samples", 12)))
    frames = sorted({s + round(i * (e - s) / (n - 1)) for i in range(n)})
    seat_top, rect = _seat_info(args)
    floor = float(args.get("floor_z", 0.0))
    per, nverts = measure_sitter(av, frames)
    contacts, soles, where = [], [], []
    for p in per:
        pt = seat_contact(p["seat"], rect)
        contacts.append(pt[2] + SEAT_BIAS_CM); where.append(pt)
        soles.append(min(q[2] for q in p["sole"]))
    plan = plan_fit(contacts, soles, seat_top, floor, args.get("mode", "seat"), float(args.get("tolerance_cm", 2.5)))
    mid = where[len(where) // 2]
    out = {"ok": True, "avatar": av.GetName(), "frames": frames, "vertices_used": nverts,
           "seat_top_cm": None if seat_top is None else round(seat_top, 1),
           "contact_z_now": [round(min(contacts), 1), round(max(contacts), 1)],
           "sole_z_now": [round(min(soles), 1), round(max(soles), 1)],
           "contact_point_xy": [round(mid[0], 1), round(mid[1], 1)], **plan}
    if rect:
        x0, x1, y0, y1 = rect
        out["contact_inside_seat"] = x0 <= mid[0] <= x1 and y0 <= mid[1] <= y1
        out["contact_to_seat_back_cm"] = round(y1 - mid[1], 1)     # characters face -Y: the seat back edge is +Y
    if args.get("apply", True) and abs(plan["dz_cm"]) >= 0.2:
        from tools.icmcp_extra import place_object
        T = av.LocalTransform().T()
        r = place_object({"name": av.GetName(), "frame": 0, "clear_keys": False,
                          "position": {"x": T.x, "y": T.y, "z": T.z + plan["dz_cm"]}})
        out["applied"] = {"position_now": [round(v, 1) for v in r["position_now"]], "transform_keys": r["transform_keys"]}
    return out


def register(registry):
    registry["fit_sitter"] = {
        "handler": fit_sitter, "main_thread": True,
        "description": "Seat a sitting character properly. Measures its real posed body surface (buttocks/thighs and soles, "
        "not bone heights) over a frame range and shifts it vertically so it rests on the seat (prop name `seat` or "
        "`seat_height_cm`). Reports the seat height the clip was authored for, the gap/sink after the fit, where the "
        "feet end up, and advice when the seat height does not suit the clip. apply=false only measures.",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "seat": {"type": "string", "description": "prop whose bounds top is the seat"},
            "seat_height_cm": {"type": "number"}, "floor_z": {"type": "number"},
            "seat_surface": {"type": "string", "enum": ["auto", "bounds"], "description": "auto (default): find the seat "
            "in the prop's mesh (a real bench's bounds top is its backrest); bounds: use the bounds top"},
            "mode": {"type": "string", "enum": ["seat", "feet"]}, "apply": {"type": "boolean"},
            "start_frame": {"type": "integer"}, "end_frame": {"type": "integer"}, "samples": {"type": "integer"},
            "tolerance_cm": {"type": "number"}}, "required": ["avatar"]}}
