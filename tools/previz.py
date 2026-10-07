"""Validated motion planning and sampled contact diagnostics for previz.

The original choreography functions stay intact. No reach keys or transforms
are edited by these diagnostics; motion replacement remains explicitly opt-in.
"""
import math
import os

import RLPy
from tools import fight_tools


def _number(value, label, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("%s must be a finite number" % label)
    if value < 0 or (positive and value == 0):
        raise ValueError("%s must be %s" % (label, "positive" if positive else "nonnegative"))
    return float(value)


def _avatar(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("avatar must be an exact, nonempty scene name")
    matches = [a for a in RLPy.RScene.GetAvatars() if a.GetName() == name]
    if len(matches) != 1:
        raise ValueError("avatar %r must match exactly one scene avatar (found %d)" % (name, len(matches)))
    return matches[0]


def _motion_plan(args):
    av = _avatar(args["avatar"])
    replace = args.get("replace", False)
    if not isinstance(replace, bool):
        raise ValueError("replace must be boolean")
    items = args["clips"]
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise ValueError("clips must contain 1 to 100 entries; use the existing clearing tool to remove all motion")
    frame_seconds = RLPy.RGlobal.GetFps().IndexedFrameTime(1).ToInt() / 6000.0
    normalized = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or set(item) - {"path", "start_s", "speed", "length_s"}:
            raise ValueError("clips[%d] must contain only path, start_s, speed, length_s" % i)
        if "path" not in item or "start_s" not in item:
            raise ValueError("clips[%d] requires path and start_s" % i)
        path = item["path"]
        if not isinstance(path, str) or not path.strip():
            raise ValueError("clips[%d].path must be nonempty" % i)
        path = fight_tools._win(path)
        if not os.path.isfile(path):
            raise ValueError("motion file not found or not a file: %s" % path)
        row = {"path": path, "start_s": _number(item["start_s"], "start_s")}
        speed = _number(item.get("speed", 1), "speed", positive=True)
        row["speed"] = speed
        if "length_s" in item:
            row["length_s"] = _number(item["length_s"], "length_s", positive=True)
            clip_length = _number(row["length_s"] * speed, "length_s * speed", positive=True)
            if clip_length < frame_seconds:
                raise ValueError("length_s * speed must be at least one project frame; iClone rejects shorter clip lengths")
        normalized.append(row)
    normalized.sort(key=lambda c: c["start_s"])
    return av, {"avatar": args["avatar"], "clips": normalized, "replace": replace}


def safe_motion_track(args):
    """Check every input before delegating to the measured motion loader."""
    execute = args.get("execute", False)
    if not isinstance(execute, bool):
        raise ValueError("execute must be boolean")
    av, plan = _motion_plan(args)
    if not execute:
        return {"validated": True, "executed": False, "plan": plan,
                "existing_clip_count": av.GetSkeletonComponent().GetClipCount(),
                "warning": "Preflight checks files and values, not motion compatibility. Execution is not atomic; "
                           "save a separate project backup before replacing clips."}
    result = fight_tools.motion_track(plan)
    result["executed"] = True
    return result


def _bone_spec(value, label):
    if not isinstance(value, dict) or set(value) != {"avatar", "bone"}:
        raise ValueError("%s requires exactly avatar and bone" % label)
    av = _avatar(value["avatar"])
    if not isinstance(value["bone"], str) or not value["bone"].strip():
        raise ValueError("%s.bone must be nonempty" % label)
    fight_tools._bone(av, value["bone"])
    return value


def check_contact(args):
    source = _bone_spec(args["source"], "source")
    target = _bone_spec(args["target"], "target") if "target" in args else None
    if target is not None and "%s.%s" % (target["avatar"], target["bone"]) == "%s.%s" % (source["avatar"], source["bone"]):
        raise ValueError("source and target must be different bones")
    seconds = args["seconds"]
    if not isinstance(seconds, list) or not 2 <= len(seconds) <= 240:
        raise ValueError("seconds must contain 2 to 240 strictly increasing sample times")
    times = [_number(s, "sample time") for s in seconds]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("sample times must be strictly increasing")
    tolerance = _number(args.get("tolerance_cm", 2), "tolerance_cm")
    if RLPy.RGlobal.IsPlaying():
        raise ValueError("Pause playback before sampling contacts")
    end = RLPy.RGlobal.GetEndTime().ToInt() / 6000.0
    if times[-1] > end:
        raise ValueError("sample times must be within the timeline end (%.3fs)" % end)
    original = RLPy.RGlobal.GetTime()
    try:
        samples = fight_tools.bone_track({"bones": [source] + ([target] if target else []), "seconds": times})
    finally:
        status = RLPy.RGlobal.SetTime(original)
        if status != RLPy.RStatus.Success:
            raise RuntimeError("Contact sampling could not restore the playhead; inspect the timeline")
    source_key = "%s.%s" % (source["avatar"], source["bone"])
    target_key = "%s.%s" % (target["avatar"], target["bone"]) if target else None
    rows = []
    anchor = None
    for s in times:
        row = samples[str(s)]
        p = row[source_key]
        q = row[target_key] if target else [0, 0, 0]
        relative = [u - v for u, v in zip(p, q)]
        if len(relative) != 3 or not all(math.isfinite(v) for v in relative):
            raise RuntimeError("Bone sampling returned invalid coordinates")
        if anchor is None:
            anchor = relative
        drift = math.sqrt(sum((u - v) ** 2 for u, v in zip(relative, anchor)))
        entry = {"seconds": s, "drift_cm": round(drift, 3), "within_tolerance": drift <= tolerance}
        if target:
            entry["distance_cm"] = round(math.sqrt(sum(v * v for v in relative)), 3)
        rows.append(entry)
    worst = max(rows, key=lambda r: r["drift_cm"])
    return {"mode": "relative_translation" if target else "world_position",
            "tolerance_cm": tolerance, "max_drift_cm": worst["drift_cm"], "worst_seconds": worst["seconds"],
            "passed": all(r["within_tolerance"] for r in rows), "samples": rows,
            "limits": "Sampled positions rounded to 0.1 cm by bone_track. Drift is relative to the first sample; "
                      "it does not prove initial contact, orientation, surface clearance, or behavior between samples. "
                      "Relative translation does not compensate for target rotation."}


def register(registry):
    def reg(name, handler, description, properties, required):
        registry[name] = {"handler": handler, "main_thread": True, "description": description,
                          "inputSchema": {"type": "object", "properties": properties, "required": required}}
    reg("safe_motion_track", safe_motion_track,
        "Preferred motion planning tool: validates ALL files/times/speeds before edits. Defaults to dry run "
        "(execute=false) and append (replace=false). execute=true delegates to motion_track; replacement is not atomic. "
        "Preserves transform and reach layers. Save a separate backup before replace=true.",
        {"avatar": {"type": "string"}, "clips": {"type": "array", "items": {"type": "object"}},
         "replace": {"type": "boolean", "default": False}, "execute": {"type": "boolean", "default": False}},
        ["avatar", "clips"])
    bone = {"type": "object", "properties": {"avatar": {"type": "string"}, "bone": {"type": "string"}},
            "required": ["avatar", "bone"], "additionalProperties": False}
    reg("check_contact", check_contact,
        "Measure sampled positional drift in cm for planted feet or held contact. source={avatar,bone}, "
        "optional target={avatar,bone} measures translation relative to a moving bone. Explicit increasing seconds "
        "(2..240), tolerance_cm defaults to 2. Paused timeline required. Restores playhead even on sampling error. "
        "Does not create IK or repair animation; compare distance_cm to detect an initial gap.",
        {"source": bone, "target": bone, "seconds": {"type": "array", "items": {"type": "number"}},
         "tolerance_cm": {"type": "number", "minimum": 0, "default": 2}}, ["source", "seconds"])
