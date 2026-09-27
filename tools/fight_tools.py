"""hoodtronik fork: choreography tools — motion_track, bone_track, reach_key, link_to_bone.

CLAUDE-NOTE (2026-09-26): motion clips, transform keys and reach keys are SEPARATE layers in iClone. Each tool here touches
ONLY the layer it names — motion_track never touches transform keys (Ilyas's hand-fixed placements live there).
Reach API (verified live 09-26, iClone 8.74): RIHikEffectorComponent.AddReachKey(eEffector, RReachKey);
RReachKey.SetTargetObject takes an OBJECT, not a bone -> to grab a bone, link a small prop to the bone
(RIObject.LinkTo(RINode, ELinkObjectAlignType, RTime) accepts a bone node) and reach for the prop.
"""
import os

import RLPy


def _secs_time(s):
    return RLPy.RTime.FromValue(int(round(float(s) * 6000)))


def _win(path):
    return path.replace("/", "\\")


def _avatar(name):
    for a in RLPy.RScene.GetAvatars():
        if a.GetName() == name:
            return a
    raise ValueError("avatar not found: %s" % name)


def _find_any(name):
    for t in ("EObjectType_Prop", "EObjectType_Avatar", "EObjectType_Camera", "EObjectType_Light", "EObjectType_Particle"):
        o = RLPy.RScene.FindObject(getattr(RLPy, t), name)
        if o:
            return o
    raise ValueError("object not found: %s" % name)


def _bone(av, name):
    node = next((n for n in av.GetSkeletonComponent().GetSkinBones() if n.GetName() == name), None)
    if node is None:
        raise ValueError("bone %s not on %s" % (name, av.GetName()))
    return node


def _delete_all_clips(sk):
    removed = 0
    for _ in range(sk.GetClipCount() + 2):
        if sk.GetClipCount() == 0:
            break
        clip = sk.GetClip(sk.GetClipCount() - 1)
        try:
            st = sk.DeleteClip(clip)
        except TypeError:
            st = sk.DeleteClip(sk.GetClipCount() - 1)
        if st != RLPy.RStatus.Success:
            break
        removed += 1
    return removed


def _clip_rows(sk):
    rows = []
    for i in range(sk.GetClipCount()):
        c = sk.GetClip(i)
        st = c.ClipTimeToSceneTime(RLPy.RTime.FromValue(0)).ToInt() / 6000.0
        ln = c.GetClipLength().ToInt() / 6000.0
        rows.append({"index": i, "start_s": round(st, 3), "end_s": round(st + ln, 3), "speed": c.GetSpeed()})
    return rows


def motion_track(args):
    av = _avatar(args["avatar"])
    sk = av.GetSkeletonComponent()
    removed = _delete_all_clips(sk) if args.get("replace", True) else 0
    loaded = []
    for item in sorted(args["clips"], key=lambda c: float(c["start_s"])):
        path = _win(item["path"])
        if not os.path.exists(path):
            raise ValueError("motion file not found: %s" % path)
        before = sk.GetClipCount()
        RLPy.RFileIO.LoadMotion(path, _secs_time(item["start_s"]), av)
        if sk.GetClipCount() <= before:
            raise RuntimeError("LoadMotion added no clip for %s" % os.path.basename(path))
        clip = sk.GetClipByTime(_secs_time(float(item["start_s"]) + 0.02)) or sk.GetClip(sk.GetClipCount() - 1)
        if "speed" in item:
            clip.SetSpeed(float(item["speed"]))
        if "length_s" in item:
            clip.SetLength(_secs_time(item["length_s"]))
        loaded.append(os.path.basename(path))
    return {"avatar": av.GetName(), "removed_clips": removed, "loaded": loaded, "clips": _clip_rows(sk)}


def bone_track(args):
    out = {}
    for s in args["seconds"]:
        RLPy.RGlobal.SetTime(_secs_time(s))
        row = {}
        for b in args["bones"]:
            T = _bone(_avatar(b["avatar"]), b["bone"]).WorldTransform().T()
            row["%s.%s" % (b["avatar"], b["bone"])] = [round(T.x, 1), round(T.y, 1), round(T.z, 1)]
        if len(row) == 2:
            p, q = list(row.values())
            row["distance_cm"] = round(sum((u - v) ** 2 for u, v in zip(p, q)) ** 0.5, 1)
        out[str(s)] = row
    return out


_EFFECTORS = {"right_hand": "EHikEffector_RightHand", "left_hand": "EHikEffector_LeftHand",
              "right_foot": "EHikEffector_RightFoot", "left_foot": "EHikEffector_LeftFoot", "head": "EHikEffector_Head"}
_REACH_TYPES = {"target": "ReachKeyType_Target", "lock": "ReachKeyType_Lock", "release": "ReachKeyType_Release"}


def _reach_rows(av, eff):
    keys = av.GetHikEffectorComponent().GetReachKeys(eff)
    rows = []
    for i in range(len(keys)):
        kk = keys[i]
        o = kk.GetTargetObject()
        rows.append({"t": round(kk.GetTime().ToInt() / 6000.0, 3), "type": str(kk.GetKeyType()),
                     "target": o.GetName() if o else None})
    return rows


def reach_key(args):
    av = _avatar(args["avatar"])
    eff = getattr(RLPy, _EFFECTORS[args.get("effector", "right_hand")])
    ktype = args.get("key_type", "target")
    k = RLPy.RReachKey()
    k.SetTime(_secs_time(args["seconds"]))
    k.SetKeyType(getattr(RLPy, _REACH_TYPES[ktype]))
    if ktype != "release":
        k.SetTargetObject(_find_any(args["target_object"]))
    k.SetTransitionRange(_secs_time(args.get("transition_s", 0.25)))
    k.SetRotationActive(bool(args.get("rotation", False)))
    if "force" in args:
        k.SetForceReach(bool(args["force"]))
    st = av.GetHikEffectorComponent().AddReachKey(eff, k)
    return {"status": "ok" if st == RLPy.RStatus.Success else "failed", "reach_keys": _reach_rows(av, eff)}


def clear_reach_keys(args):
    av = _avatar(args["avatar"])
    eff = getattr(RLPy, _EFFECTORS[args.get("effector", "right_hand")])
    hik = av.GetHikEffectorComponent()
    keys = hik.GetReachKeys(eff)
    n = 0
    for i in range(len(keys) - 1, -1, -1):
        try:
            hik.RemoveReachKey(eff, keys[i])
        except TypeError:
            hik.RemoveReachKey(eff, keys[i].GetTime())
        n += 1
    return {"removed": n, "reach_keys": _reach_rows(av, eff)}


def link_to_bone(args):
    obj = _find_any(args["name"])
    av = _avatar(args["avatar"])
    node = _bone(av, args["bone"])
    align = {"none": "ELinkObjectAlignType_None", "position": "ELinkObjectAlignType_Position",
             "position_and_rotation": "ELinkObjectAlignType_Position_And_Rotation"}[args.get("align", "position")]
    st = obj.LinkTo(node, getattr(RLPy, align), _secs_time(args.get("seconds", 0)))
    RLPy.RGlobal.SetTime(_secs_time(args.get("check_s", 0)))
    T, B = obj.WorldTransform().T(), node.WorldTransform().T()
    return {"status": "ok" if st == RLPy.RStatus.Success else "failed",
            "obj_to_bone_cm": round(((T.x - B.x) ** 2 + (T.y - B.y) ** 2 + (T.z - B.z) ** 2) ** 0.5, 2)}


def register(registry):
    def reg(name, fn, desc, props, req):
        registry[name] = {"handler": fn, "main_thread": True, "description": desc,
                          "inputSchema": {"type": "object", "properties": props, "required": req}}
    reg("motion_track", motion_track,
        "Replace (replace=true, default) or append an avatar's MOTION clips with a timed list clips=[{path,start_s,speed?,length_s?}]. "
        "Never touches transform keys. Returns actual clip start/end seconds.",
        {"avatar": {"type": "string"}, "clips": {"type": "array", "items": {"type": "object"}}, "replace": {"type": "boolean"}},
        ["avatar", "clips"])
    reg("bone_track", bone_track,
        "World positions (cm) of bones=[{avatar,bone}] at seconds=[...]; with exactly 2 bones also distance_cm (contact checks).",
        {"bones": {"type": "array", "items": {"type": "object"}}, "seconds": {"type": "array", "items": {"type": "number"}}},
        ["bones", "seconds"])
    reg("reach_key", reach_key,
        "Add a Reach Target (IK) key: avatar effector (right_hand|left_hand|right_foot|left_foot|head) reaches target_object at "
        "seconds; key_type target|lock|release; transition_s; rotation. To grab a BONE, link_to_bone a small prop to it first.",
        {"avatar": {"type": "string"}, "effector": {"type": "string"}, "target_object": {"type": "string"}, "seconds": {"type": "number"},
         "key_type": {"type": "string"}, "transition_s": {"type": "number"}, "rotation": {"type": "boolean"}, "force": {"type": "boolean"}},
        ["avatar", "seconds"])
    reg("clear_reach_keys", clear_reach_keys, "Remove all Reach keys of one effector on an avatar.",
        {"avatar": {"type": "string"}, "effector": {"type": "string"}}, ["avatar"])
    reg("link_to_bone", link_to_bone,
        "Link a scene object to an avatar BONE (e.g. grab-target prop -> Soldier CC_Base_R_Hand); reports object-to-bone cm at check_s.",
        {"name": {"type": "string"}, "avatar": {"type": "string"}, "bone": {"type": "string"}, "align": {"type": "string"},
         "seconds": {"type": "number"}, "check_s": {"type": "number"}}, ["name", "avatar", "bone"])
