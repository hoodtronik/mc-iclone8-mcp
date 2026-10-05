"""Experimental character-performance tools, isolated from measured legacy code.

All edit tools preflight, default to dry run, and require a new project backup
on execution. FK values are clip-layer channels, not absolute world poses.
"""

import contextlib
import json
import math
import os

import RLPy

from tools import fight_tools
from tools.previz import _avatar


def number(v, label, minimum=None, maximum=None):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError("%s must be finite numeric data" % label)
    if minimum is not None and v < minimum or maximum is not None and v > maximum:
        raise ValueError("%s is outside the allowed range" % label)
    return float(v)


def integer(v, label, minimum=0, maximum=1000000):
    number(v, label, minimum, maximum)
    if int(v) != v:
        raise ValueError("%s must be an integer" % label)
    return int(v)


def boolean(v, label):
    if not isinstance(v, bool):
        raise ValueError("%s must be boolean" % label)
    return v


def fields(v, allowed, required=()):
    if not isinstance(v, dict) or set(v) - set(allowed) or set(required) - set(v):
        raise ValueError(
            "Expected fields %s; required %s" % (sorted(allowed), sorted(required))
        )
    return v


def sequence(v, label, maximum=240, minimum=1):
    if not isinstance(v, list) or not minimum <= len(v) <= maximum:
        raise ValueError("%s must contain %d..%d entries" % (label, minimum, maximum))
    return v


def text(v, label):
    if not isinstance(v, str) or not v.strip():
        raise ValueError("%s must be nonempty text" % label)
    return v


def time(s):
    s = number(s, "seconds", 0, 86400)
    return RLPy.RTime.FromValue(int(round(s * 6000)))


def seconds(t):
    return t.ToInt() / 6000.0


def ok(status, label):
    if status != RLPy.RStatus.Success:
        raise RuntimeError("%s failed: %s" % (label, status))


def method(obj, name):
    fn = getattr(obj, name, None)
    if not callable(fn):
        raise RuntimeError("%s is unavailable on this iClone build" % name)
    return fn


@contextlib.contextmanager
def playhead():
    if RLPy.RGlobal.IsPlaying():
        raise ValueError("Pause the timeline first")
    original = RLPy.RGlobal.GetTime()
    try:
        yield
    finally:
        ok(RLPy.RGlobal.SetTime(original), "Restore playhead")


def refresh(s):
    # Reuse the measured solver refresh without accessing unsafe reach targets.
    end = seconds(RLPy.RGlobal.GetEndTime())
    other = min(end, s + 1) if s < end else max(0, s - 1)
    from PySide2 import QtWidgets

    for point in (other, s):
        ok(RLPy.RGlobal.SetTime(time(point)), "Set sampling time")
        QtWidgets.QApplication.processEvents()


def backup(path):
    path = os.path.abspath(text(path, "backup_path"))
    if not path.lower().endswith(".iproject"):
        raise ValueError("backup_path must end with .iProject")
    if os.path.exists(path) or not os.path.isdir(os.path.dirname(path)):
        raise ValueError("backup_path must be a NEW file in an existing directory")
    ok(method(RLPy.RFileIO, "SaveProject")(path), "Save project backup")
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError("Backup save reported success but produced no nonempty file")
    return path


def execute(args, plan, steps):
    if not boolean(args.get("execute", False), "execute"):
        return dict(plan, executed=False)
    if RLPy.RGlobal.IsPlaying():
        raise ValueError("Pause the timeline before editing")
    saved = backup(args.get("backup_path"))
    applied = []
    try:
        for label, fn in steps:
            fn()
            applied.append(label)
    except Exception as error:
        raise RuntimeError(
            "Partial edit; backup=%s; applied=%s; failed=%s: %s. "
            "Inspect state or restore the backup before retrying."
            % (saved, applied, label, error)
        ) from error
    return dict(plan, executed=True, backup_path=saved, applied=applied)


def skeleton(args):
    avatar = _avatar(args["avatar"])
    sk = avatar.GetSkeletonComponent()
    if sk is None:
        raise ValueError("Avatar has no skeleton")
    return avatar, sk


def clip_at(sk, s):
    t = time(s)
    s = seconds(t)
    found = []
    for i in range(sk.GetClipCount()):
        clip = sk.GetClip(i)
        start = seconds(clip.ClipTimeToSceneTime(time(0)))
        end = start + seconds(clip.GetClipLength())
        if start <= s < end:
            found.append((i, clip))
    if len(found) != 1:
        raise ValueError(
            "Time %.6f must be inside exactly one motion clip (found %d)"
            % (s, len(found))
        )
    index, clip = found[0]
    return index, clip, method(clip, "SceneTimeToClipTime")(t)


def clip_index(sk, index):
    index = integer(index, "clip_index", 0, max(0, sk.GetClipCount() - 1))
    if index >= sk.GetClipCount():
        raise ValueError("No clip at this index")
    return sk.GetClip(index)


def bones(sk, names):
    names = sequence(names, "bones", 200)
    if len(set(text(n, "bone") for n in names)) != len(names):
        raise ValueError("Duplicate bone names")
    result = {}
    for name in names:
        matches = [b for b in sk.GetSkinBones() if b.GetName() == name]
        if len(matches) != 1:
            raise ValueError("Bone %r must match exactly one skin bone" % name)
        result[name] = matches[0]
    return result


def channel(clip, bone, group, axis):
    control = method(clip, "GetControl")("Layer", bone)
    if control is None:
        raise ValueError("No Layer control for %s" % bone.GetName())
    block = control.GetDataBlock()
    ctl = block.GetControl("%s/%s%s" % (group, group, axis.upper()))
    if ctl is None:
        raise ValueError("Missing layer channel %s.%s" % (group, axis))
    method(ctl, "GetValue")
    method(ctl, "SetValue")
    return ctl


def value(ctl, t):
    result = ctl.GetValue(t, 0.0)
    if not isinstance(result, (tuple, list)) or len(result) != 2:
        raise RuntimeError(
            "Unexpected RFloatControl.GetValue signature; native verification required"
        )
    ok(result[0], "Read layer channel")
    return number(result[1], "layer channel")


def capture_pose(args):
    _, sk = skeleton(args)
    s = number(args["seconds"], "seconds", 0, 86400)
    index, clip, t = clip_at(sk, s)
    selected = bones(sk, args["bones"])
    pose = {}
    for name, bone in selected.items():
        pose[name] = {
            "rotation_degrees": {
                a: math.degrees(value(channel(clip, bone, "Rotation", a), t))
                for a in "xyz"
            },
            "position_cm": {
                a: value(channel(clip, bone, "Position", a), t) for a in "xyz"
            },
        }
    return {
        "avatar": args["avatar"],
        "seconds": s,
        "clip_index": index,
        "bones": pose,
        "space": "FK clip-layer channel values; not an absolute world-space pose",
    }


def set_pose_keys(args):
    avatar, sk = skeleton(args)
    keys = sequence(args["keys"], "keys", 240)
    mode = args.get("mode", "absolute")
    if mode not in ("absolute", "delta"):
        raise ValueError("mode must be absolute or delta")
    seen, actions, rows = set(), [], []
    for key in keys:
        fields(key, ("seconds", "bones"), ("seconds", "bones"))
        s = number(key["seconds"], "seconds", 0, 86400)
        index, clip, t = clip_at(sk, s)
        updates = key["bones"]
        if not isinstance(updates, dict) or not 1 <= len(updates) <= 200:
            raise ValueError("Each key requires 1..200 bone updates")
        selected = bones(sk, list(updates))
        for name, update in updates.items():
            fields(update, ("rotation_degrees", "position_cm"))
            if not update:
                raise ValueError("Bone update must include channels")
            for prop, group in (
                ("rotation_degrees", "Rotation"),
                ("position_cm", "Position"),
            ):
                if prop not in update:
                    continue
                values = fields(update[prop], "xyz")
                if not values:
                    raise ValueError("Channel update must not be empty")
                for axis, raw in values.items():
                    raw = number(
                        raw,
                        prop,
                        -360000 if group == "Rotation" else -1e9,
                        360000 if group == "Rotation" else 1e9,
                    )
                    val = math.radians(raw) if group == "Rotation" else raw
                    ctl = channel(clip, selected[name], group, axis)
                    before = value(ctl, t)
                    if mode == "delta":
                        val += before
                    number(val, "resulting channel")
                    identity = (index, name, group, axis, t.ToInt())
                    if identity in seen:
                        raise ValueError(
                            "Duplicate channel key after 6000 Hz time quantization"
                        )
                    seen.add(identity)
                    if len(seen) > 5000:
                        raise ValueError("At most 5000 channel keys per call")
                    label = "%s:%s.%s.%s@%s" % (index, name, group, axis, s)

                    def write(ctl=ctl, t=t, val=val, bone=selected[name]):
                        ok(ctl.SetValue(t, val), "Set layer key")
                        actual = value(ctl, t)
                        if not math.isclose(actual, val, rel_tol=1e-6, abs_tol=1e-6):
                            raise RuntimeError(
                                "Layer key readback differs from requested value"
                            )
                        bone.Update()

                    actions.append((label, write))
                    rows.append(
                        {
                            "bone": name,
                            "channel": group + axis.upper(),
                            "seconds": s,
                            "clip_index": index,
                            "clip_tick": t.ToInt(),
                            "before": before,
                            "after": val,
                        }
                    )
    actions.append(("avatar update", avatar.Update))
    return execute(
        args,
        {
            "avatar": args["avatar"],
            "mode": mode,
            "keys": rows,
            "space": "FK clip-layer; radians internally, cm for position",
        },
        actions,
    )


def apply_pose(args):
    fields(
        args["pose"], ("bones", "avatar", "seconds", "clip_index", "space"), ("bones",)
    )
    selected = sequence(args["bones"], "bones", 200)
    if len(set(selected)) != len(selected):
        raise ValueError("Duplicate bone mask names")
    if any(n not in args["pose"]["bones"] for n in selected):
        raise ValueError("Every masked bone must exist in the supplied pose")
    return set_pose_keys(
        dict(
            args,
            keys=[
                {
                    "seconds": args["seconds"],
                    "bones": {n: args["pose"]["bones"][n] for n in selected},
                }
            ],
        )
    )


def apply_hand_pose(args):
    # Rig-specific hand masks are explicit; no guessed finger names/axes.
    selected = sequence(args["finger_bones"], "finger_bones", 40)
    updates = args["pose"].get("bones") if isinstance(args["pose"], dict) else None
    if not isinstance(updates, dict) or set(updates) != set(selected):
        raise ValueError(
            "Hand pose must contain exactly the explicit finger_bones mask"
        )
    if any(
        set(fields(v, ("rotation_degrees",), ("rotation_degrees",)))
        != {"rotation_degrees"}
        for v in updates.values()
    ):
        raise ValueError("Hand presets must contain rotation channels only")
    return apply_pose(dict(args, bones=selected))


def _preset_pose(pose):
    fields(pose, ("bones", "avatar", "seconds", "clip_index", "space"), ("bones",))
    for label in ("avatar", "space"):
        if label in pose:
            text(pose[label], label)
    if "seconds" in pose:
        number(pose["seconds"], "seconds", 0, 86400)
    if "clip_index" in pose:
        integer(pose["clip_index"], "clip_index")
    if not isinstance(pose["bones"], dict) or not 1 <= len(pose["bones"]) <= 200:
        raise ValueError("Preset needs 1..200 bone entries")
    for name, update in pose["bones"].items():
        text(name, "bone")
        fields(update, ("rotation_degrees", "position_cm"))
        if not update:
            raise ValueError("Empty preset bone update")
        for prop, channels in update.items():
            fields(channels, "xyz")
            if not channels:
                raise ValueError("Empty preset channel update")
            limit = 360000 if prop == "rotation_degrees" else 1e9
            for val in channels.values():
                number(val, prop, -limit, limit)
    return pose


def save_pose_preset(args):
    pose = _preset_pose(args["pose"])
    name = text(args["name"], "preset name")
    path = os.path.abspath(text(args["path"], "path"))
    if not path.lower().endswith(".json") or not os.path.isdir(os.path.dirname(path)):
        raise ValueError("Preset path must be .json under an existing directory")
    payload = {"schema_version": 1, "name": name, "pose": pose}
    serialized = json.dumps(payload, indent=2, allow_nan=False)
    with open(path, "x", encoding="utf-8") as stream:
        stream.write(serialized)
    return {"path": path, "name": name, "bones": list(pose["bones"])}


def load_pose_preset(args):
    path = os.path.abspath(text(args["path"], "path"))
    if os.path.getsize(path) > 1024 * 1024:
        raise ValueError("Preset exceeds 1 MiB")
    with open(path, encoding="utf-8") as stream:
        data = json.load(stream)
    fields(data, ("schema_version", "name", "pose"), ("schema_version", "name", "pose"))
    if data["schema_version"] != 1 or isinstance(data["schema_version"], bool):
        raise ValueError("Unsupported preset schema version")
    text(data["name"], "preset name")
    _preset_pose(data["pose"])
    return data


def inspect_clip_transition(args):
    _, sk = skeleton(args)
    clip = clip_index(sk, args["clip_index"])
    return {
        "avatar": args["avatar"],
        "clip_index": args["clip_index"],
        "range_sdk_s": seconds(method(clip, "GetTransitionRange")()),
        "fade_in_type": str(method(clip, "GetTransitionType")(True)),
        "fade_in_strength": method(clip, "GetTransitionStrength")(True),
    }


def set_clip_transition(args):
    _, sk = skeleton(args)
    clip = clip_index(sk, args["clip_index"])
    duration = number(
        args["duration_sdk_s"], "duration_sdk_s", 0, seconds(clip.GetLength())
    )
    strength = number(args.get("strength", 50), "strength", 0, 100)
    curve = args.get("curve", "linear")
    names = {
        "linear": "Linear",
        "step": "Step",
        "ease_in": "Ease_In",
        "ease_out": "Ease_Out",
        "ease_in_out": "Ease_In_Out",
    }
    if curve not in names or not hasattr(RLPy, "ETransitionType_" + names[curve]):
        raise ValueError("Unsupported transition curve")
    enum = getattr(RLPy, "ETransitionType_" + names[curve])
    range_fn = method(clip, "SetTransitionRange")
    type_fn = method(clip, "SetTransitionType")
    before = inspect_clip_transition(args)

    def change():
        ok(range_fn(time(duration)), "Set clip transition range")
        ok(type_fn(True, enum, strength), "Set clip transition curve")
        if abs(seconds(clip.GetTransitionRange()) - duration) > 1 / 6000.0:
            raise RuntimeError("Transition duration was rejected or clamped")
        if clip.GetTransitionType(True) != enum or not math.isclose(
            clip.GetTransitionStrength(True), strength, abs_tol=1e-5
        ):
            raise RuntimeError("Transition curve/strength readback mismatch")

    return execute(
        args,
        {
            "before": before,
            "duration_sdk_s": duration,
            "curve": curve,
            "strength": strength,
        },
        [("transition", change)],
    )


def split_motion_clip(args):
    _, sk = skeleton(args)
    s = number(args["seconds"], "seconds", 0, 86400)
    _, clip, _ = clip_at(sk, s)
    start = seconds(clip.ClipTimeToSceneTime(time(0)))
    frame = seconds(RLPy.RGlobal.GetFps().IndexedFrameTime(1))
    end = start + seconds(clip.GetClipLength())
    if min(s - start, end - s) < frame:
        raise ValueError("Split must leave at least one project frame on both sides")
    fn = method(sk, "BreakClip")
    before = sk.GetClipCount()

    def split():
        ok(fn(time(s)), "Break clip")
        if sk.GetClipCount() != before + 1:
            raise RuntimeError("Split did not produce exactly one additional clip")

    return execute(
        args,
        {"avatar": args["avatar"], "seconds": s, "before_clip_count": before},
        [("split", split)],
    )


def trim_motion_clip(args):
    _, sk = skeleton(args)
    clip = clip_index(sk, args["clip_index"])
    frame = seconds(RLPy.RGlobal.GetFps().IndexedFrameTime(1))
    duration = number(
        args["length_scene_s"], "length_scene_s", frame, seconds(clip.GetClipLength())
    )
    speed = number(clip.GetSpeed(), "clip speed", 1e-12)
    source_length = number(duration * speed, "source length", frame, 86400)
    fn = method(clip, "SetLength")

    def trim():
        ok(fn(time(source_length)), "Trim motion clip")
        if abs(seconds(clip.GetClipLength()) - duration) > 1 / 6000:
            raise RuntimeError("Trimmed scene duration differs from requested duration")

    return execute(
        args,
        {
            "avatar": args["avatar"],
            "clip_index": args["clip_index"],
            "length_scene_s": duration,
            "warning": "Shortens the tail and can discard encased layer keys; never extends the clip.",
        },
        [("trim", trim)],
    )


def merge_motion_clips(args):
    _, sk = skeleton(args)
    first = integer(args["first_index"], "first_index")
    second = integer(args["second_index"], "second_index")
    if second != first + 1:
        raise ValueError("Merge requires adjacent clip indices in chronological order")
    a, b = clip_index(sk, first), clip_index(sk, second)
    end_a = seconds(a.ClipTimeToSceneTime(time(0))) + seconds(a.GetClipLength())
    start_b = seconds(b.ClipTimeToSceneTime(time(0)))
    if abs(start_b - end_a) > 1 / 6000:
        raise ValueError(
            "Merge requires touching clips; resolve gaps/overlaps explicitly"
        )
    fn = method(sk, "MergeClips")
    count = sk.GetClipCount()

    def merge():
        ok(fn(a, b), "Merge motion clips")
        if sk.GetClipCount() != count - 1:
            raise RuntimeError("Merged clip count differs from expected count")

    return execute(
        args,
        {
            "avatar": args["avatar"],
            "first_index": first,
            "second_index": second,
            "warning": "Experimental native merge; inspect transition/layer behavior after execution.",
        },
        [("merge", merge)],
    )


def hold_motion_pose(args):
    # Measured workaround: stretch one source frame. This is NOT an exact freeze.
    _, sk = skeleton(args)
    s = number(args["seconds"], "seconds", 0, 86400)
    duration = number(args["duration_s"], "duration_s", 0.001, 86400)
    _, clip, _ = clip_at(sk, s)
    start = seconds(clip.ClipTimeToSceneTime(time(0)))
    frame = seconds(RLPy.RGlobal.GetFps().IndexedFrameTime(1))
    end = start + seconds(clip.GetClipLength())
    if s - start < frame or s + duration > end or duration < frame:
        raise ValueError(
            "Near-hold must start inside a clip, leaving a prefix, and end within that clip"
        )
    fn = method(sk, "BreakClip")
    for name in ("SetSpeed", "SetLength", "SetLoopCount"):
        method(clip, name)
    speed = frame / duration

    def hold():
        before = sk.GetClipCount()
        ok(fn(time(s)), "Split for near-hold")
        if sk.GetClipCount() != before + 1:
            raise RuntimeError("Near-hold split count mismatch")
        tails = [
            sk.GetClip(i)
            for i in range(sk.GetClipCount())
            if abs(seconds(sk.GetClip(i).ClipTimeToSceneTime(time(0))) - s) <= 1 / 6000
        ]
        if len(tails) != 1:
            raise RuntimeError("Cannot resolve newly split tail")
        tail = tails[0]
        ok(tail.SetLoopCount(0), "Disable looping")
        ok(tail.SetSpeed(speed), "Set near-hold speed")
        ok(tail.SetLength(time(frame)), "Set one-frame source length")
        if (
            not math.isclose(tail.GetSpeed(), speed, rel_tol=1e-5)
            or abs(seconds(tail.GetClipLength()) - duration) > frame
        ):
            raise RuntimeError("Near-hold speed/duration readback mismatch")

    return execute(
        args,
        {
            "avatar": args["avatar"],
            "seconds": s,
            "duration_s": duration,
            "speed": speed,
            "warning": "Near-still retimed source frame, not exact freeze. Replaces/discards the remaining tail of this clip.",
        },
        [("near-hold", hold)],
    )


def plan_contact(args):
    avatar = _avatar(args["avatar"])
    effector = args.get("effector", "right_hand")
    if effector not in fight_tools._EFFECTORS:
        raise ValueError("Unknown effector")
    target = fight_tools._find_any(text(args["target_object"], "target_object"))
    start = number(args["start_s"], "start_s", 0, 86400)
    end = number(args["end_s"], "end_s", start, seconds(RLPy.RGlobal.GetEndTime()))
    transition = number(
        args.get("transition_s", 0.25), "transition_s", 0, min(start, (end - start) / 2)
    )
    if time(end).ToInt() <= time(start).ToInt():
        raise ValueError("Contact end must be later than start")
    rotation = boolean(args.get("rotation", False), "rotation")
    method(avatar.GetHikEffectorComponent(), "AddReachKey")
    enum = getattr(RLPy, fight_tools._EFFECTORS[effector])
    existing = avatar.GetHikEffectorComponent().GetReachKeys(enum)
    for i in range(len(existing)):
        stamp = seconds(existing[i].GetTime())
        if start - transition <= stamp <= end + transition:
            raise ValueError(
                "Existing reach key intersects this interval; resolve it explicitly before applying"
            )
    return {
        "avatar": args["avatar"],
        "effector": effector,
        "target_object": target.GetName(),
        "keys": [
            {
                "avatar": args["avatar"],
                "effector": effector,
                "target_object": target.GetName(),
                "seconds": start,
                "transition_s": transition,
                "rotation": rotation,
                "key_type": "target",
            },
            {
                "avatar": args["avatar"],
                "effector": effector,
                "seconds": end,
                "transition_s": transition,
                "key_type": "release",
            },
        ],
        "warning": "Use a pre-positioned offset target prop to preserve the grip. Native keep-current-pose is not invoked. "
        "Reach ramps can begin before the key; verify approach/release timing and reachability visually.",
    }


def apply_contact_interval(args):
    plan = plan_contact(args)
    steps = []
    for i, key in enumerate(plan["keys"]):

        def write(key=key):
            result = fight_tools.reach_key(key)
            if result.get("status") != "ok":
                raise RuntimeError("Reach key rejected")

        steps.append(("reach key %d" % i, write))
    return execute(args, plan, steps)


def inspect_performance_capabilities(args):
    avatar, sk = skeleton(args)
    face = avatar.GetFaceComponent()
    return {
        "avatar": args["avatar"],
        "experimental": True,
        "skeleton_methods": {
            n: callable(getattr(sk, n, None))
            for n in (
                "BreakClip",
                "MergeClips",
                "SampleMotionClip",
                "FlattenMotionClip",
            )
        },
        "face_methods": {
            n: callable(getattr(face, n, None))
            for n in ("AddExpressionKeys", "AddHeadKey", "AddEyeKey")
        },
        "native_actor_look_at": {
            "supported_by_this_plugin": False,
            "reason": "No verified native actor Look-at API route",
        },
        "motion_director": {
            "supported_by_this_plugin": False,
            "reason": "No verified native recording/control route; path transforms do not generate gait",
        },
        "note": "Symbol presence does not prove native compatibility. Pose-layer controls are checked per bone and clip.",
    }


def register(registry):
    edit = {
        "execute": {"type": "boolean", "default": False},
        "backup_path": {"type": "string"},
    }
    avatar = {"avatar": {"type": "string"}}

    def reg(name, fn, desc, props, req, mutation=False):
        registry[name] = {
            "handler": fn,
            "main_thread": True,
            "description": desc,
            "inputSchema": {
                "type": "object",
                "properties": dict(props, **(edit if mutation else {})),
                "required": req,
            },
        }

    reg(
        "capture_pose",
        capture_pose,
        "Read masked FK layer channels at explicit scene seconds. Values are layer channels, not absolute world pose.",
        dict(
            avatar,
            seconds={"type": "number"},
            bones={"type": "array", "items": {"type": "string"}},
        ),
        ["avatar", "seconds", "bones"],
    )
    reg(
        "set_pose_keys",
        set_pose_keys,
        "Preflight masked FK layer keys at scene seconds; convert through each clip. Only specified axes change. Dry run default; execution requires NEW backup_path. Experimental.",
        dict(
            avatar,
            keys={"type": "array", "items": {"type": "object"}},
            mode={"type": "string", "enum": ["absolute", "delta"]},
        ),
        ["avatar", "keys"],
        True,
    )
    reg(
        "apply_pose",
        apply_pose,
        "Apply explicit bone mask from pose={bones:{...}} at seconds; preserves other layer channels. Dry run default; new backup required.",
        dict(
            avatar,
            seconds={"type": "number"},
            pose={"type": "object"},
            bones={"type": "array", "items": {"type": "string"}},
        ),
        ["avatar", "seconds", "pose", "bones"],
        True,
    )
    reg(
        "apply_hand_pose",
        apply_hand_pose,
        "Apply a rig-calibrated finger rotation preset with exact finger_bones mask. No guessed bone names, axes, or automatic left/right mapping. Dry run default.",
        dict(
            avatar,
            seconds={"type": "number"},
            pose={"type": "object"},
            finger_bones={"type": "array", "items": {"type": "string"}},
        ),
        ["avatar", "seconds", "pose", "finger_bones"],
        True,
    )
    reg(
        "save_pose_preset",
        save_pose_preset,
        "Save a validated rig-specific FK layer preset to a NEW local JSON file. Never overwrites a preset.",
        {
            "name": {"type": "string"},
            "path": {"type": "string"},
            "pose": {"type": "object"},
        },
        ["name", "path", "pose"],
    )
    reg(
        "load_pose_preset",
        load_pose_preset,
        "Load a validated FK layer JSON preset. Applying it still requires an explicit mask and rig-compatible channels.",
        {"path": {"type": "string"}},
        ["path"],
    )
    reg(
        "inspect_clip_transition",
        inspect_clip_transition,
        "Read fade-in transition range/type/strength; range reported as native RTime seconds; no retiming conversion assumed.",
        dict(avatar, clip_index={"type": "integer"}),
        ["avatar", "clip_index"],
    )
    reg(
        "set_clip_transition",
        set_clip_transition,
        "Set fade-in native RTime duration in seconds (no retiming conversion), curve and strength (0..100), with readback. Dry run default; new backup required.",
        dict(
            avatar,
            clip_index={"type": "integer"},
            duration_sdk_s={"type": "number"},
            curve={"type": "string"},
            strength={"type": "number"},
        ),
        ["avatar", "clip_index", "duration_sdk_s"],
        True,
    )
    reg(
        "split_motion_clip",
        split_motion_clip,
        "Split motion at scene seconds with one-frame margins and clip-count readback. Experimental, dry run default; new backup required.",
        dict(avatar, seconds={"type": "number"}),
        ["avatar", "seconds"],
        True,
    )
    reg(
        "trim_motion_clip",
        trim_motion_clip,
        "Shorten motion tail by SCENE duration; speed conversion/readback checked. Can discard layer keys. Dry run default; new backup required.",
        dict(avatar, clip_index={"type": "integer"}, length_scene_s={"type": "number"}),
        ["avatar", "clip_index", "length_scene_s"],
        True,
    )
    reg(
        "merge_motion_clips",
        merge_motion_clips,
        "Merge touching adjacent motion clips with clip-count readback. Experimental, dry run default; new backup required.",
        dict(avatar, first_index={"type": "integer"}, second_index={"type": "integer"}),
        ["avatar", "first_index", "second_index"],
        True,
    )
    reg(
        "hold_motion_pose",
        hold_motion_pose,
        "Near-still retimed one-source-frame slice, NOT exact freeze. Discards remaining clip tail; interval must fit existing clip. Dry run default; new backup required.",
        dict(avatar, seconds={"type": "number"}, duration_s={"type": "number"}),
        ["avatar", "seconds", "duration_s"],
        True,
    )
    contact = dict(
        avatar,
        effector={"type": "string"},
        target_object={"type": "string"},
        start_s={"type": "number"},
        end_s={"type": "number"},
        transition_s={"type": "number"},
        rotation={"type": "boolean"},
    )
    reg(
        "plan_contact",
        plan_contact,
        "Validate target/release interval without editing. Requires pre-positioned offset prop; rejects intersecting reach keys. Does not use native keep-current-pose.",
        contact,
        ["avatar", "target_object", "start_s", "end_s"],
    )
    reg(
        "apply_contact_interval",
        apply_contact_interval,
        "Apply preflighted reach+release keys using existing measured reach API. Dry run default; new backup required. No automatic offset or motion repair.",
        contact,
        ["avatar", "target_object", "start_s", "end_s"],
        True,
    )
    reg(
        "inspect_performance_capabilities",
        inspect_performance_capabilities,
        "Report actual SDK symbol availability and unsupported native Look-at/Motion Director routes without guessing.",
        avatar,
        ["avatar"],
    )
