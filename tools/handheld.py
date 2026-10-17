"""Hand-held props: put a prop (a phone, cup, bag...) in a character's hand and keep it there.
Tool: hold_prop.
# CLAUDE-NOTE (2026-10-17): link_to_bone snaps the prop to the WRIST pivot. hold_prop computes the prop's world pose from
# the hand bone at `frame` (offset/rotation expressed in the hand bone's frame: CC limb bones point along local +Y, as
# measured for Thigh->Calf basis (0, 36.6, 0)), places it there, then links with alignment None so the offset is kept.
"""
import math

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

PRESETS = {   # size cm (x, y, z) of a primitive stand-in, offset cm in the hand frame (+Y toward fingers)
    "phone": {"size": (7.5, 15.5, 0.9), "offset": (0.0, 9.0, -2.5), "color": (0.05, 0.05, 0.06)},
    "cup": {"size": (8.0, 8.0, 11.0), "offset": (0.0, 8.0, -4.0), "color": (0.9, 0.9, 0.88)},
    "book": {"size": (15.0, 22.0, 2.5), "offset": (0.0, 10.0, -3.0), "color": (0.35, 0.12, 0.1)},
}


def euler_q(deg):
    """XYZ euler degrees -> quaternion (x, y, z, w), applied X then Y then Z (q = qz * qy * qx)."""
    rx, ry, rz = (math.radians(d) / 2 for d in deg)
    qx = (math.sin(rx), 0.0, 0.0, math.cos(rx))
    qy = (0.0, math.sin(ry), 0.0, math.cos(ry))
    qz = (0.0, 0.0, math.sin(rz), math.cos(rz))
    from tools.seating import qmul
    return qmul(qz, qmul(qy, qx))


def hold_pose(hand_T, hand_Q, offset, rot_deg=(0.0, 0.0, 0.0)):
    """World (T, Q) of a prop held at `offset` (hand frame) with extra rotation rot_deg relative to the hand."""
    from tools.seating import qrot, qmul, _add
    return _add(hand_T, qrot(hand_Q, offset)), qmul(hand_Q, euler_q(rot_deg))


def hold_prop(args):
    from tools.icmcp_extra import _avatar, _t
    from tools.objects import find_by_name
    av = _avatar(args["avatar"])
    hand = "CC_Base_R_Hand" if args.get("hand", "right") == "right" else "CC_Base_L_Hand"
    bone = next((b for b in av.GetSkeletonComponent().GetSkinBones() if b.GetName() == hand), None)
    if bone is None:
        raise ValueError(f"{av.GetName()} has no {hand}")
    preset = PRESETS.get(args.get("preset", "phone"), PRESETS["phone"])
    name = args.get("prop") or f"{av.GetName()}_{args.get('preset', 'phone')}"
    obj = None
    try:
        obj = find_by_name(name)
    except Exception:
        obj = None
    made_scale = None
    if obj is None:                                   # make a primitive stand-in with the preset's size
        from tools.project import create_primitive
        sx, sy, sz = preset["size"]
        create_primitive({"type": "box", "name": name, "scale": {"x": sx / 100.0, "y": sy / 100.0, "z": sz / 100.0}})
        made_scale = (sx / 100.0, sy / 100.0, sz / 100.0)
        obj = find_by_name(name)
        if args.get("color", True):
            from tools.materials import set_material_color
            c = preset["color"]
            RLPy.RGlobal.SetTime(RLPy.RTime.FromValue(0))       # material colour is KEYED at the current frame
            set_material_color({"name": name, "color": {"r": c[0], "g": c[1], "b": c[2]}})
    frame = int(args.get("frame", 0))
    offset = tuple(args.get("offset_cm") or preset["offset"])
    rot = tuple(args.get("rotation_deg") or (0.0, 0.0, 0.0))
    now = RLPy.RGlobal.GetTime()
    try:
        # CLAUDE-NOTE (2026-10-17, measured): LinkTo with ELinkObjectAlignType__None (double underscore in RLPy) keeps
        # the object's CURRENT WORLD offset to the bone. The keyed world pose must be EVALUATED before linking (stale
        # read otherwise: the link captured the old origin pose, 344 cm away) -> nudge the playhead first. Keys set
        # after an aligned link are ignored. Result: 9.3 cm constant from the link frame on.
        RLPy.RGlobal.SetTime(_t(frame + 1)); RLPy.RGlobal.SetTime(_t(frame))
        wt = bone.WorldTransform()
        T, Q = wt.T(), wt.R()
        (px, py, pz), q = hold_pose((T.x, T.y, T.z), (Q.x, Q.y, Q.z, Q.w), offset, rot)
        ctrl = obj.GetControl("Transform")
        ctrl.ClearKeys()
        # CLAUDE-NOTE (2026-10-17, render): the scale read right after create_primitive was stale (1, 1, 1) and keying it
        # back made the phone a 1 m box. Use the scale we created with; otherwise read it after the nudge above.
        S = RLPy.RVector3(*made_scale) if made_scale else obj.LocalTransform().S()
        ctrl.SetValue(_t(0), RLPy.RTransform(S, RLPy.RQuaternion(RLPy.RVector4(*q)), RLPy.RVector3(px, py, pz)))
        RLPy.RGlobal.SetTime(_t(frame + 1)); RLPy.RGlobal.SetTime(_t(frame))
        st = obj.LinkTo(bone, RLPy.ELinkObjectAlignType__None, _t(frame))
        checks = []
        for f in (frame, frame + 30, frame + 90):
            RLPy.RGlobal.SetTime(_t(f + 1)); RLPy.RGlobal.SetTime(_t(f))
            a, b = obj.WorldTransform(), bone.WorldTransform()
            ta, tb = a.T(), b.T()
            checks.append(round(math.dist((ta.x, ta.y, ta.z), (tb.x, tb.y, tb.z)), 1))
    finally:
        RLPy.RGlobal.SetTime(now)
    steady = max(checks) - min(checks) < 2.0
    return {"ok": st == RLPy.RStatus.Success and steady, "prop": name, "hand": hand,
            "prop_to_hand_cm": checks, "note": "distance should stay constant (the prop rides with the hand)"}


def register(registry):
    registry["hold_prop"] = {
        "handler": hold_prop, "main_thread": True,
        "description": "HAND-HELD PROP: put a prop in an avatar's hand and link it there (rides with the hand). prop = an "
                       "existing object name, or omit to create a primitive stand-in from preset phone|cup|book. hand "
                       "right|left, frame (when the pose is matched), offset_cm [x, y, z] in the hand frame (+Y toward the "
                       "fingers; preset default), rotation_deg [x, y, z] relative to the hand. Verify with a close-up.",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "prop": {"type": "string"}, "preset": {"type": "string"},
            "hand": {"type": "string", "enum": ["right", "left"]}, "frame": {"type": "integer"},
            "offset_cm": {"type": "array"}, "rotation_deg": {"type": "array"}, "color": {"type": "boolean"}},
            "required": ["avatar"]}}
