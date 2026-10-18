import math
import RLPy
from tools.objects import find_by_name
from tools.common import rl_string


_TYPES = {
    "object": RLPy.EObjectType_Object,
    "avatar": RLPy.EObjectType_Avatar,
    "prop": RLPy.EObjectType_Prop,
    "camera": RLPy.EObjectType_Camera,
    "light": RLPy.EObjectType_Light,
    "particle": RLPy.EObjectType_Particle,
}
if hasattr(RLPy, "EObjectType_Path"):
    _TYPES["path"] = RLPy.EObjectType_Path


def _object_summary(obj):
    transform = obj.LocalTransform()
    position = transform.T()
    return {"id": obj.GetID(), "name": obj.GetName(), "type": rl_string(obj.GetType()), "position": {"x": position.x, "y": position.y, "z": position.z}}


def list_objects(args):
    object_type = args.get("type", "object").lower()
    if object_type not in _TYPES:
        raise ValueError("Unsupported object type: %s" % object_type)
    return {"objects": [_object_summary(obj) for obj in RLPy.RScene.FindObjects(_TYPES[object_type])]}


def get_selection(_args):
    return {"objects": [_object_summary(obj) for obj in RLPy.RScene.GetSelectedObjects()]}


def select_object(args):
    name = args["name"]
    obj = find_by_name(name)
    RLPy.RScene.SelectObject(obj)
    return {"status": "ok", "name": obj.GetName()}


def set_visibility(args):
    obj = find_by_name(args["name"])
    result = obj.SetVisible(RLPy.RGlobal.GetTime(), args["visible"])
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not change visibility")
    return {"status": "ok", "name": obj.GetName(), "visible": args["visible"]}


def delete_object(args):
    obj = find_by_name(args["name"])
    result = RLPy.RScene.RemoveObject(obj)
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not remove object")
    return {"status": "ok", "name": args["name"]}


def moved_pose(pos, quat, pivot, offset, turn_deg):
    """Pose (pos, quat xyzw) turned turn_deg CCW about a vertical axis through pivot, then moved by offset."""
    a = math.radians(turn_deg)
    c, s = math.cos(a), math.sin(a)
    dx, dy = pos[0] - pivot[0], pos[1] - pivot[1]
    p = (pivot[0] + c * dx - s * dy + offset[0], pivot[1] + s * dx + c * dy + offset[1], pos[2] + offset[2])
    tz, tw = math.sin(a / 2), math.cos(a / 2)       # turn quaternion (0, 0, tz, tw) * quat
    x, y, z, w = quat
    q = (tw * x - tz * y, tw * y + tz * x, tw * z + tz * w, tw * w - tz * z)
    return p, q


def _vec3(v):
    if v is None:
        return (0.0, 0.0, 0.0)
    if isinstance(v, dict):
        return (float(v.get("x", 0)), float(v.get("y", 0)), float(v.get("z", 0)))
    return (float(v[0]), float(v[1]), float(v[2]) if len(v) > 2 else 0.0)


def _move_all_keys(obj, pivot, offset, turn_deg):
    """Shift EVERY transform key so an animated object (walker, moving prop) keeps its motion, just relocated."""
    # CLAUDE-NOTE (2026-10-18): live: one frame-0 transform key on an avatar moves its whole clip (bone x +200 at
    # frames 0-500); a walker has several keys (Man: 3), so each one is read with GetTransformKeyAt and re-set.
    ctrl = obj.GetControl("Transform")
    n = ctrl.GetKeyCount()
    if n == 0:
        cur = obj.LocalTransform()
        RLPy.RGlobal.SetTime(RLPy.RTime.FromValue(0))
        keys = [(RLPy.RTime.FromValue(0), cur)]
    else:
        keys = []
        for i in range(n):
            k = RLPy.RTransformKey()
            ctrl.GetTransformKeyAt(i, k)
            keys.append((k.GetTime(), k.GetTransform()))
    for t, tr in keys:
        T, R = tr.T(), tr.R()
        p, q = moved_pose((T.x, T.y, T.z), (R.x, R.y, R.z, R.w), pivot, offset, turn_deg)
        ctrl.SetValue(t, RLPy.RTransform(tr.S(), RLPy.RQuaternion(RLPy.RVector4(q[0], q[1], q[2], q[3])),
                                         RLPy.RVector3(*p)))
    return len(keys)


def clone_object(args):
    """Clone an object (animation, clips and motion-layer keys come along). Optional offset/turn_deg relocate the
    copy; count makes several copies, each offset/turned once more than the last (a row of chairs, a queue)."""
    source = find_by_name(args["name"])
    count = max(1, int(args.get("count", 1)))
    offset = _vec3(args.get("offset"))
    turn = float(args.get("turn_deg", 0))
    st = source.LocalTransform().T()
    pivot = (st.x, st.y, st.z)
    out = []
    for i in range(1, count + 1):
        clone = source.Clone()
        if clone is None:
            raise RuntimeError("iClone could not clone object")
        name = args.get("new_name")
        if name and count > 1:
            name = "%s%02d" % (name, i)
        if name:
            clone.SetName(name)
        summary = {}
        if any(offset) or turn:
            summary["keys_moved"] = _move_all_keys(clone, pivot, tuple(o * i for o in offset), turn * i)
        summary.update(_object_summary(clone))
        out.append(summary)
    return out[0] if count == 1 else {"clones": out}


def link_object(args):
    obj = find_by_name(args["name"])
    target = find_by_name(args["target_name"])
    alignments = {
        "none": "ELinkObjectAlignType_None",
        "position": "ELinkObjectAlignType_Position",
        "position_and_rotation": "ELinkObjectAlignType_Position_And_Rotation",
    }
    alignment = args.get("alignment", "position_and_rotation")
    if alignment not in alignments:
        raise ValueError("Unsupported alignment: %s" % alignment)
    result = obj.LinkTo(target, getattr(RLPy, alignments[alignment]), RLPy.RGlobal.GetTime())
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not link object")
    return {"status": "ok", "name": obj.GetName(), "target": target.GetName(), "alignment": alignment}


def unlink_object(args):
    obj = find_by_name(args["name"])
    result = obj.UnLink(RLPy.RGlobal.GetTime())
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not unlink object")
    return {"status": "ok", "name": obj.GetName()}


def align_object(args):
    obj = find_by_name(args["name"])
    target = find_by_name(args["target_name"])
    axes = {
        "x": "EAlignAxis_X_AXIS",
        "y": "EAlignAxis_Y_AXIS",
        "z": "EAlignAxis_Z_AXIS",
        "rotation": "EAlignAxis_ROTATE_AXIZ",
    }
    axis = args.get("axis", "rotation")
    if axis not in axes:
        raise ValueError("Unsupported alignment axis: %s" % axis)
    result = obj.AlignTo(target, getattr(RLPy, axes[axis]), args.get("to_pivot", True))
    if result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not align object")
    return {"status": "ok", "name": obj.GetName(), "target": target.GetName(), "axis": axis}


def set_static(args):
    obj = find_by_name(args["name"])
    result = obj.SetStatic(args["static"])
    if result is not None and result != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not change static state")
    return {"status": "ok", "name": obj.GetName(), "static": args["static"]}


def register(registry):
    registry["list_objects"] = {"handler": list_objects, "main_thread": True, "description": "Liste les objets de la scène iClone 8.", "inputSchema": {"type": "object", "properties": {"type": {"type": "string", "enum": list(_TYPES)}}}}
    registry["get_selection"] = {"handler": get_selection, "main_thread": True, "description": "Retourne la sélection active dans iClone.", "inputSchema": {"type": "object", "properties": {}}}
    registry["select_object"] = {"handler": select_object, "main_thread": True, "description": "Sélectionne un objet de la scène par son nom.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}
    registry["set_visibility"] = {"handler": set_visibility, "main_thread": True, "description": "Affiche ou masque un objet à l'instant courant.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "visible": {"type": "boolean"}}, "required": ["name", "visible"]}}
    registry["delete_object"] = {"handler": delete_object, "main_thread": True, "description": "Supprime définitivement un objet de la scène.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}
    registry["clone_object"] = {"handler": clone_object, "main_thread": True, "description": "Clone an object (clips and layer keys included). offset {x,y,z} cm and turn_deg (CCW about the source's position) relocate every transform key; count makes a series (each copy offset once more), names new_name01..", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "new_name": {"type": "string"}, "offset": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}}}, "turn_deg": {"type": "number"}, "count": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["name"]}}
    registry["link_object"] = {"handler": link_object, "main_thread": True, "description": "Lie un objet à une cible à la frame courante.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "target_name": {"type": "string"}, "alignment": {"type": "string", "enum": ["none", "position", "position_and_rotation"]}}, "required": ["name", "target_name"]}}
    registry["unlink_object"] = {"handler": unlink_object, "main_thread": True, "description": "Dissocie un objet de sa cible à la frame courante.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}
    registry["align_object"] = {"handler": align_object, "main_thread": True, "description": "Aligne un objet sur une cible selon un axe ou sa rotation.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "target_name": {"type": "string"}, "axis": {"type": "string", "enum": ["x", "y", "z", "rotation"]}, "to_pivot": {"type": "boolean"}}, "required": ["name", "target_name"]}}
    registry["set_static"] = {"handler": set_static, "main_thread": True, "description": "Active ou désactive le statut statique d’un objet.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "static": {"type": "boolean"}}, "required": ["name", "static"]}}
