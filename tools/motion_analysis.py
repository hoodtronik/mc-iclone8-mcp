"""Bone-space contact QA and explicit gaze planning; no implicit native Look-at."""

import math

from tools import performance as p


def quat(q):
    values = [p.number(getattr(q, a), "quaternion") for a in ("x", "y", "z", "w")]
    norm = math.sqrt(sum(v * v for v in values))
    if not math.isfinite(norm) or norm < 1e-12:
        raise ValueError("Invalid zero quaternion")
    return [v / norm for v in values]


def multiply(a, b):
    x, y, z, w = a
    u, v, t, s = b
    return [
        w * u + x * s + y * t - z * v,
        w * v - x * t + y * s + z * u,
        w * t + x * v - y * u + z * s,
        w * s - x * u - y * v - z * t,
    ]


def conjugate(q):
    return [-q[0], -q[1], -q[2], q[3]]


def rotate(q, v):
    return multiply(multiply(q, list(v) + [0]), conjugate(q))[:3]


def length(v):
    return math.sqrt(sum(x * x for x in v))


def angular_error(a, b):
    # q and -q encode the same rotation.
    return math.degrees(2 * math.acos(min(1, abs(sum(u * v for u, v in zip(a, b))))))


def spec(value):
    p.fields(value, ("avatar", "bone"), ("avatar", "bone"))
    avatar = p._avatar(value["avatar"])
    return p.bones(avatar.GetSkeletonComponent(), [value["bone"]])[value["bone"]]


def transform(node):
    tr = node.WorldTransform()
    pos = tr.T()
    return [p.number(getattr(pos, a), "position") for a in "xyz"], quat(tr.R())


def check_contact_pose(args):
    source = spec(args["source"])
    target = spec(args["target"]) if "target" in args else None
    if args.get("target") == args["source"]:
        raise ValueError("Source and target must differ")
    times = [
        p.number(t, "seconds", 0, p.seconds(p.RLPy.RGlobal.GetEndTime()))
        for t in p.sequence(args["seconds"], "seconds", 240, 2)
    ]
    ticks = [p.time(t).ToInt() for t in times]
    if any(b <= a for a, b in zip(ticks, ticks[1:])):
        raise ValueError("Samples must increase after 6000 Hz time quantization")
    cm = p.number(args.get("tolerance_cm", 2), "tolerance_cm", 0)
    deg = p.number(args.get("tolerance_deg", 10), "tolerance_deg", 0, 180)
    if target is None and "expected_distance_cm" in args:
        raise ValueError("expected_distance_cm requires a target bone")
    expected = (
        p.number(args["expected_distance_cm"], "expected_distance_cm", 0)
        if "expected_distance_cm" in args
        else None
    )
    rows = []
    with p.playhead():
        for s in times:
            p.refresh(s)
            pos, rotation = transform(source)
            if target:
                tgt, qr = transform(target)
                pos = rotate(conjugate(qr), [u - v for u, v in zip(pos, tgt)])
                rotation = multiply(conjugate(qr), rotation)
            if not rows:
                anchor_pos, anchor_rot = pos, rotation
            drift = length([u - v for u, v in zip(pos, anchor_pos)])
            angle = angular_error(rotation, anchor_rot)
            distance = length(pos) if target else None
            passed = (
                drift <= cm
                and angle <= deg
                and (expected is None or abs(distance - expected) <= cm)
            )
            rows.append(
                {
                    "seconds": p.seconds(p.time(s)),
                    "position_cm": pos,
                    "drift_cm": drift,
                    "rotation_drift_deg": angle,
                    "distance_cm": distance,
                    "passed": passed,
                }
            )
    return {
        "space": "target-local" if target else "world",
        "passed": all(r["passed"] for r in rows),
        "max_drift_cm": max(r["drift_cm"] for r in rows),
        "max_rotation_drift_deg": max(r["rotation_drift_deg"] for r in rows),
        "samples": rows,
        "limits": "Bone origins/orientations, not mesh surfaces. First sample is the reference; expected_distance_cm "
        "adds an initial-gap check. No proof between samples or of IK reachability.",
    }


def plan_actor_gaze(args):
    source = spec(args["source"])
    target = spec(args["target"])
    s = p.number(args["seconds"], "seconds", 0, p.seconds(p.RLPy.RGlobal.GetEndTime()))
    with p.playhead():
        p.refresh(s)
        pos, q = transform(source)
        tgt, _ = transform(target)
    direction = [u - v for u, v in zip(tgt, pos)]
    distance = length(direction)
    if distance < 1e-6:
        raise ValueError("Gaze target coincides with the source bone")
    direction = [v / distance for v in direction]
    local = rotate(conjugate(q), direction)
    return {
        "seconds": s,
        "target_distance_cm": distance,
        "world_direction": direction,
        "source_local_direction": local,
        "world_yaw_deg": math.degrees(math.atan2(direction[1], direction[0])),
        "world_elevation_deg": math.degrees(
            math.atan2(direction[2], math.hypot(direction[0], direction[1]))
        ),
        "executed": False,
        "native_look_at": False,
        "instruction": "Directions are diagnostic, NOT FK Euler key values. Use calibrated head/eye layer channels "
        "through set_pose_keys; native actor Look-at/head-body weighting is not implemented.",
    }


def register(registry):
    bone = {
        "type": "object",
        "properties": {"avatar": {"type": "string"}, "bone": {"type": "string"}},
        "required": ["avatar", "bone"],
        "additionalProperties": False,
    }
    registry["check_contact_pose"] = {
        "handler": check_contact_pose,
        "main_thread": True,
        "description": "Sample full-precision target-local position AND quaternion drift, accounting for target rotation. "
        "Optional expected_distance_cm tests bone-origin separation. Restores paused playhead. No mesh collision check.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": bone,
                "target": bone,
                "seconds": {"type": "array", "items": {"type": "number"}},
                "tolerance_cm": {"type": "number"},
                "tolerance_deg": {"type": "number"},
                "expected_distance_cm": {"type": "number"},
            },
            "required": ["source", "seconds"],
        },
    }
    registry["plan_actor_gaze"] = {
        "handler": plan_actor_gaze,
        "main_thread": True,
        "description": "Read source/target bone directions at scene seconds for eyeline planning. No native Look-at or automatic gaze keys. "
        "Do not use returned direction/yaw as FK Euler values without rig calibration.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": bone,
                "target": bone,
                "seconds": {"type": "number"},
            },
            "required": ["source", "target", "seconds"],
        },
    }
