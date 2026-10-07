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
            # CLAUDE-NOTE (2026-09-26): RIClip.SetLength is in CLIP time; scene length L at speed v -> SetLength(L * v).
            clip.SetLength(_secs_time(float(item["length_s"]) * clip.GetSpeed()))
        loaded.append(os.path.basename(path))
    return {"avatar": av.GetName(), "removed_clips": removed, "loaded": loaded, "clips": _clip_rows(sk)}


def bone_track(args):
    out = {}
    # CLAUDE-NOTE (2026-09-26): right after a reach/clip edit the first SetTime sample returned STALE bone positions
    # (grab read 51 cm off, really 0.0). Nudge the playhead elsewhere first so the solver re-evaluates.
    first = float(args["seconds"][0]) if args["seconds"] else 0.0
    try:
        from PySide2 import QtWidgets
        pump = QtWidgets.QApplication.processEvents
    except Exception:
        pump = lambda: None
    RLPy.RGlobal.SetTime(_secs_time(first + 1.0)); pump()
    RLPy.RGlobal.SetTime(_secs_time(first)); pump()
    for s in args["seconds"]:
        RLPy.RGlobal.SetTime(_secs_time(s)); pump()
        row = {}
        for b in args["bones"]:
            W = _bone(_avatar(b["avatar"]), b["bone"]).WorldTransform(); T = W.T()   # hold W (dangling T(), measured)
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
    # NOTE: index RReachKeyVector (keys[i]); iterating it yields raw SwigPyObject without methods.
    keys = av.GetHikEffectorComponent().GetReachKeys(eff)
    rows = []
    for i in range(len(keys)):
        kk = keys[i]
        # CLAUDE-NOTE (2026-09-26): NEVER call methods on kk.GetTargetObject() — it returns a dangling RIObject and
        # IsValid()/GetName() on it hard-crash iClone 8.74 (proven twice). Report time/type/transition only.
        rows.append({"t": round(kk.GetTime().ToInt() / 6000.0, 3), "type": {0: "target", 1: "lock", 2: "release"}.get(
            int(kk.GetKeyType()), str(kk.GetKeyType())), "transition_s": round(kk.GetTransitionRange().ToInt() / 6000.0, 3)})
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
    # CLAUDE-NOTE (2026-10-07): hold the RTransform — `x.WorldTransform().T()` dangles once another transform is read (measured).
    # Before this, T could be overwritten by the bone read, so obj_to_bone_cm could print 0 for a failed link.
    _wo, _wn = obj.WorldTransform(), node.WorldTransform()
    T, B = _wo.T(), _wn.T()
    return {"status": "ok" if st == RLPy.RStatus.Success else "failed",
            "obj_to_bone_cm": round(((T.x - B.x) ** 2 + (T.y - B.y) ** 2 + (T.z - B.z) ** 2) ** 0.5, 2)}


def _yaw_deg(q):
    import math
    return math.degrees(math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))


def _key_rows(ctrl):
    rows = []
    for i in range(ctrl.GetKeyCount()):
        k = RLPy.RTransformKey()
        ctrl.GetTransformKeyAt(i, k)
        tr = k.GetTransform()
        t = tr.T()
        rows.append({"t": round(k.GetTime().ToInt() / 6000.0, 3), "pos": [round(t.x, 1), round(t.y, 1), round(t.z, 1)],
                     "heading_deg": round(_yaw_deg(tr.R()), 1)})
    return rows


def transform_key(args):
    """Add/overwrite ONE transform key at `seconds`, starting from the currently interpolated value there.
    CLAUDE-NOTE (2026-09-26): upstream set_transform keys at the playhead and zeroes unspecified rotation axes; this keeps
    everything not named, never edits other keys, and enforces Ilyas's frame-0 rule (refuses if the object has no key at 0)."""
    from tools.common import euler_degrees_to_quaternion
    obj = _find_any(args["name"])
    ctrl = obj.GetControl("Transform")
    rows = _key_rows(ctrl)
    if not rows or rows[0]["t"] != 0:
        raise RuntimeError("%s has no transform key at frame 0 — key frame 0 first (place_object/aim_camera)" % obj.GetName())
    t = _secs_time(args["seconds"])
    cur = RLPy.RTransform()
    ctrl.GetValue(t, cur)
    pos, scale, rot = cur.T(), cur.S(), cur.R()
    if "position" in args:
        v = args["position"]
        pos = RLPy.RVector3(v.get("x", pos.x), v.get("y", pos.y), v.get("z", pos.z))
    if "heading_deg" in args or "tilt_deg" in args:
        tilt = args.get("tilt_deg", {})
        rot = euler_degrees_to_quaternion(tilt.get("x", 0), tilt.get("y", 0), args.get("heading_deg", _yaw_deg(rot)))
    st = ctrl.SetValue(t, RLPy.RTransform(scale, rot, pos))
    if "transition" in args:
        tt = {"linear": "ETransitionType_Linear", "step": "ETransitionType_Step", "ease_in": "ETransitionType_Ease_In",
              "ease_out": "ETransitionType_Ease_Out", "ease_in_out": "ETransitionType_Ease_In_Out"}[args["transition"]]
        ctrl.SetKeyTransition(t, getattr(RLPy, tt), float(args.get("strength", 50)))
    return {"status": "ok" if st == RLPy.RStatus.Success else "failed", "keys": _key_rows(ctrl)}


def transform_keys(args):
    return {"name": args["name"], "keys": _key_rows(_find_any(args["name"]).GetControl("Transform"))}


def register(registry):
    def reg(name, fn, desc, props, req, checkpoint=False):
        registry[name] = {"handler": fn, "main_thread": True, "description": desc, "checkpoint": checkpoint,
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
        ["avatar", "seconds"], checkpoint=True)
    reg("transform_key", transform_key,
        "Add/overwrite ONE transform key at seconds from the interpolated value there; set position{x,y,z} (partial ok), "
        "heading_deg (yaw about Z; 0 = facing -Y), tilt_deg{x,y}, transition linear|step|ease_in|ease_out|ease_in_out. "
        "Never edits other keys; refuses objects with no frame-0 key.",
        {"name": {"type": "string"}, "seconds": {"type": "number"}, "position": {"type": "object"}, "heading_deg": {"type": "number"},
         "tilt_deg": {"type": "object"}, "transition": {"type": "string"}, "strength": {"type": "number"}}, ["name", "seconds"])
    reg("transform_keys", transform_keys, "List an object's transform keys (seconds, position, heading_deg).",
        {"name": {"type": "string"}}, ["name"])
    reg("clear_reach_keys", clear_reach_keys, "Remove all Reach keys of one effector on an avatar.",
        {"avatar": {"type": "string"}, "effector": {"type": "string"}}, ["avatar"])
    reg("link_to_bone", link_to_bone,
        "Link a scene object to an avatar BONE (e.g. grab-target prop -> Soldier CC_Base_R_Hand); reports object-to-bone cm at check_s.",
        {"name": {"type": "string"}, "avatar": {"type": "string"}, "bone": {"type": "string"}, "align": {"type": "string"},
         "seconds": {"type": "number"}, "check_s": {"type": "number"}}, ["name", "avatar", "bone"])
