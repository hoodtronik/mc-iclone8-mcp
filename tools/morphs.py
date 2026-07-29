import RLPy

from tools.objects import find_by_name
from tools.common import current_time, frame_time, require_success, require_unit_interval


def _target(args):
    if args.get("name"):
        obj = find_by_name(args["name"])
    else:
        selected = RLPy.RScene.GetSelectedObjects()
        if not selected:
            raise ValueError("name is required when no object is selected")
        obj = selected[0]
    if obj.GetType() not in (RLPy.EObjectType_Prop, RLPy.EObjectType_Avatar):
        raise ValueError("Morphs are only supported on props and avatars")
    component = obj.GetMorphComponent()
    if component is None:
        raise RuntimeError("Object has no morph component")
    return obj, component


def list_morphs(args):
    obj, component = _target(args)
    morphs = []
    for mesh in obj.GetMeshNames():
        for name in component.GetMorphNames(mesh):
            morphs.append({"mesh": mesh, "name": name})
    return {"object": obj.GetName(), "morph_count": len(morphs), "morphs": morphs}


def get_morph_weight(args):
    obj, component = _target(args)
    time = frame_time(args.get("frame")) if "frame" in args else current_time()
    value = component.GetWeight(args["mesh"], args["morph"], time, 0.0)
    weight = value[1] if isinstance(value, tuple) else value
    return {"object": obj.GetName(), "mesh": args["mesh"], "morph": args["morph"], "weight": weight}


def set_morph_weight(args):
    obj, component = _target(args)
    weight = require_unit_interval(args["weight"], "weight")
    time = frame_time(args.get("frame")) if "frame" in args else current_time()
    result = component.AddKey(args["mesh"], args["morph"], time, weight, False, False)
    require_success(result, "iClone could not add morph key")
    return {"status": "ok", "object": obj.GetName(), "mesh": args["mesh"], "morph": args["morph"], "weight": weight, "frame": args.get("frame")}


def clear_morph_keys(args):
    if args.get("confirm") != "DELETE_MORPH_KEYS":
        raise ValueError("confirm must be DELETE_MORPH_KEYS")
    obj, component = _target(args)
    result = component.RemoveAllKeys(args["mesh"], args["morph"])
    require_success(result, "iClone could not remove morph keys")
    return {"status": "ok", "object": obj.GetName(), "mesh": args["mesh"], "morph": args["morph"]}


def register(registry):
    target = {"name": {"type": "string", "description": "Objet prop ou avatar (par défaut : premier objet sélectionné)."}}
    registry["list_morphs"] = {"handler": list_morphs, "main_thread": True, "description": "Liste les morphs disponibles, classés par mesh.", "inputSchema": {"type": "object", "properties": target}}
    weight = dict(target)
    weight.update({"mesh": {"type": "string"}, "morph": {"type": "string"}, "frame": {"type": "integer", "minimum": 0}})
    registry["get_morph_weight"] = {"handler": get_morph_weight, "main_thread": True, "description": "Lit le poids du morph à l’instant courant.", "inputSchema": {"type": "object", "properties": weight, "required": ["mesh", "morph"]}}
    set_weight = dict(weight)
    set_weight["weight"] = {"type": "number", "minimum": 0, "maximum": 1}
    registry["set_morph_weight"] = {"handler": set_morph_weight, "main_thread": True, "description": "Pose une clé de poids de morph à l’instant courant.", "inputSchema": {"type": "object", "properties": set_weight, "required": ["mesh", "morph", "weight"]}}
    clear_weight = dict(weight)
    clear_weight["confirm"] = {"type": "string", "enum": ["DELETE_MORPH_KEYS"]}
    registry["clear_morph_keys"] = {"handler": clear_morph_keys, "main_thread": True, "description": "Supprime toutes les clés d’un morph. Action destructive.", "inputSchema": {"type": "object", "properties": clear_weight, "required": ["mesh", "morph", "confirm"]}}
