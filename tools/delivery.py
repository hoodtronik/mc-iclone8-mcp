"""Preflighted shots, facial beats, render bundles and experimental interchange."""

import hashlib
import json
import math
import os
import re
import struct

from tools import performance as p


def vector(value, label):
    p.fields(value, "xyz", "xyz")
    return {a: p.number(value[a], label, -1e9, 1e9) for a in "xyz"}


def validate_shot_list(args):
    shots = p.sequence(args["shots"], "shots", 100)
    fps = p.RLPy.RGlobal.GetFps().ToFloat()
    end = p.seconds(p.RLPy.RGlobal.GetEndTime())
    ids, previous, normalized = set(), 0, []
    allowed = (
        "id",
        "start_s",
        "end_s",
        "position",
        "target",
        "focal_length_mm",
        "end_position",
        "end_target",
        "end_focal_length_mm",
        "roll_degrees",
        "near_cm",
        "far_cm",
    )
    for shot in shots:
        p.fields(shot, allowed, ("id", "start_s", "end_s", "position", "target"))
        name = p.text(shot["id"], "shot id")
        if name in ids:
            raise ValueError("Each shot id/camera name must be unique")
        ids.add(name)
        s = p.number(shot["start_s"], "start_s", previous, end)
        e = p.number(shot["end_s"], "end_s", s + 1 / fps, end)
        row = dict(shot, start_s=s, end_s=e)
        for field in ("position", "target", "end_position", "end_target"):
            if field in shot:
                row[field] = vector(shot[field], field)
        for prefix in ("", "end_"):
            pos = row.get(prefix + "position", row["position"])
            tgt = row.get(prefix + "target", row["target"])
            if sum((pos[a] - tgt[a]) ** 2 for a in "xyz") < 1e-12:
                raise ValueError("Camera position and target must differ")
        for field in ("focal_length_mm", "end_focal_length_mm"):
            if field in shot:
                row[field] = p.number(shot[field], field, 0.1, 10000)
        if "roll_degrees" in shot:
            row["roll_degrees"] = p.number(shot["roll_degrees"], "roll_degrees")
        row["near_cm"] = p.integer(shot.get("near_cm", 1), "near_cm", 1)
        row["far_cm"] = p.integer(
            shot.get("far_cm", 3000), "far_cm", row["near_cm"] + 1
        )
        # The existing builder places keys at end_s - 1/project_fps.
        for stamp in (s, e):
            if abs(stamp * fps - round(stamp * fps)) > 1e-6:
                raise ValueError("Shot boundaries must align to project frames")
        previous = e
        normalized.append(row)
    return {
        "shots": normalized,
        "project_fps": fps,
        "validated": True,
        "warning": "Existing builder clears each named camera transform track. Camera creation uses native UI; "
        "inspect after execution. Filmback/physical f-stop automation is not added.",
    }


def build_shot_list_verified(args):
    from tools import icmcp_extra

    plan = validate_shot_list(args)
    clear = p.boolean(args.get("clear_switch_keys", False), "clear_switch_keys")

    def build():
        result = icmcp_extra.build_shot_list(
            {"shots": plan["shots"], "clear_switch_keys": clear}
        )
        if not result.get("ok") or len(result.get("shots", [])) != len(plan["shots"]):
            raise RuntimeError("Shot builder did not report all shots")

    return p.execute(
        args, dict(plan, clear_switch_keys=clear), [("shot builder", build)]
    )


def schedule_face_performance(args):
    avatar = p._avatar(args["avatar"])
    face = avatar.GetFaceComponent()
    if face is None:
        raise ValueError("Avatar has no face component")
    available = set()
    for group in face.GetExpressionGroups():
        for name in face.GetExpressionNames(group):
            available.add(name.ToString() if hasattr(name, "ToString") else str(name))
    p.method(face, "BeginKeyEditing")
    p.method(face, "EndKeyEditing")
    p.method(face, "AddExpressionKeys")
    beats = p.sequence(args["beats"], "beats", 240)
    steps, normalized, seen = [], [], set()
    for beat in beats:
        p.fields(beat, ("seconds", "expressions"), ("seconds", "expressions"))
        s = p.number(
            beat["seconds"], "seconds", 0, p.seconds(p.RLPy.RGlobal.GetEndTime())
        )
        tick = p.time(s).ToInt()
        if tick in seen:
            raise ValueError("Duplicate facial beat after time quantization")
        seen.add(tick)
        expressions = beat["expressions"]
        if not isinstance(expressions, dict) or not expressions:
            raise ValueError("Each beat needs an expression-to-strength map")
        if set(expressions) - available:
            raise ValueError(
                "Unknown expressions: %s" % sorted(set(expressions) - available)
            )
        names = sorted(expressions)
        strengths = [p.number(expressions[n], "strength", 0, 100) for n in names]
        if face.GetClipByTime(p.time(s)) is None:
            raise ValueError(
                "Create an expression clip covering every beat before scheduling"
            )

        def write(s=s, names=names, strengths=strengths):
            face.BeginKeyEditing()
            try:
                p.ok(
                    face.AddExpressionKeys(p.time(s), names, strengths, p.time(0)),
                    "Write expressions",
                )
            finally:
                face.EndKeyEditing()

        steps.append(("face@%s" % s, write))
        normalized.append({"seconds": s, "expressions": dict(zip(names, strengths))})
    return p.execute(
        args,
        {
            "avatar": args["avatar"],
            "beats": normalized,
            "note": "Explicit-time expression keys; does not replace clips, generate blinks/gaze or change vocal timing.",
        },
        steps,
    )


def _files(folder):
    paths = [
        os.path.join(folder, n)
        for n in os.listdir(folder)
        if n.lower().endswith(".png")
    ]
    indexed = []
    for path in paths:
        match = re.search(r"(\d+)\.png$", path, re.IGNORECASE)
        if not match:
            raise RuntimeError(
                "Cannot establish render frame order from filename: %s" % path
            )
        indexed.append((int(match.group(1)), path))
    indexed.sort()
    if any(b[0] != a[0] + 1 for a, b in zip(indexed, indexed[1:])):
        raise RuntimeError("Render indices are duplicated or noncontiguous")
    return indexed


def export_previz_bundle(args):
    from PIL import Image

    from tools import icmcp_extra

    s = p.integer(args["start_frame"], "start_frame")
    e = p.integer(args["end_frame"], "end_frame", s + 1)
    fps = p.RLPy.RGlobal.GetFps()
    output_fps = p.integer(args["fps"], "fps", 1, 120)
    if not math.isclose(fps.ToFloat(), output_fps, abs_tol=1e-6):
        raise ValueError(
            "This bundle requires output fps == project fps for an unambiguous frame map"
        )
    if e > fps.GetFrameIndex(p.RLPy.RGlobal.GetEndTime()):
        raise ValueError("Render range exceeds timeline end")
    width = p.integer(args["width"], "width", 16, 8192)
    height = p.integer(args["height"], "height", 16, 8192)
    passes = p.sequence(args.get("passes", ["beauty", "openpose"]), "passes", 5)
    if len(set(passes)) != len(passes) or set(passes) - {
        "beauty",
        "openpose",
        "depth",
        "normal",
        "canny",
    }:
        raise ValueError("Passes must be unique supported pass names")
    root = os.path.abspath(p.text(args["output_dir"], "output_dir"))
    if os.path.exists(root) or not os.path.isdir(os.path.dirname(root)):
        raise ValueError("output_dir must be a NEW directory under an existing parent")
    camera_name = p.text(args["camera"], "camera")
    cams = [c for c in p.RLPy.RScene.GetCameras() if c.GetName() == camera_name]
    if len(cams) != 1:
        raise ValueError("Camera must match exactly one real scene camera")
    for kind in passes:
        p.method(
            p.RLPy.RGlobal, icmcp_extra._PASSES["beauty" if kind == "canny" else kind]
        )
    plan = {
        "camera": camera_name,
        "start_frame": s,
        "end_frame": e,
        "fps": output_fps,
        "width": width,
        "height": height,
        "passes": passes,
        "expected_frames": e - s + 1,
        "output_dir": root,
    }

    def render():
        original_camera = p.RLPy.RScene.GetCurrentCamera()
        original = p.RLPy.RGlobal.GetRenderExportImageSequenceParameter()
        original = original[0] if isinstance(original, (list, tuple)) else original
        restore_config = {
            "fps": int(original.kCommon.kFps),
            "width": original.kCommon.nOutputSizeWidth,
            "height": original.kCommon.nOutputSizeHeight,
        }
        with p.playhead():
            try:
                p.ok(p.RLPy.RScene.SetCurrentCamera(cams[0]), "Activate render camera")
                actual = icmcp_extra.set_render_output(
                    {"fps": output_fps, "width": width, "height": height}
                )
                if (
                    int(actual["fps"]) != output_fps
                    or actual["width"] != width
                    or actual["height"] != height
                ):
                    raise RuntimeError("Render configuration readback mismatch")
                os.mkdir(root)
                manifest = dict(plan, passes={})
                indices = None
                for kind in passes:
                    folder = os.path.join(root, kind)
                    os.mkdir(folder)
                    result = icmcp_extra.render_control_pass(
                        {
                            "pass": kind,
                            "camera": camera_name,
                            "start_frame": s,
                            "end_frame": e,
                            "output_path": os.path.join(folder, kind + ".png"),
                            "normalize": False,
                            "depth_raw_png": True,
                        }
                    )
                    if not result.get("ok"):
                        raise RuntimeError("Render failed: %s" % result)
                    files = _files(folder)
                    current_indices = [n for n, path in files]
                    if (
                        len(files) != e - s + 1
                        or indices is not None
                        and current_indices != indices
                    ):
                        raise RuntimeError("Pass frame count/index alignment mismatch")
                    indices = current_indices
                    rows = []
                    for ordinal, (n, path) in enumerate(files):
                        with Image.open(path) as image:
                            if image.size != (width, height):
                                raise RuntimeError("Unexpected render dimensions")
                            image.verify()
                        with open(path, "rb") as stream:
                            digest = hashlib.sha256(stream.read()).hexdigest()
                        rows.append(
                            {
                                "file": os.path.relpath(path, root),
                                "render_index": n,
                                "project_frame": s + ordinal,
                                "seconds": (s + ordinal) / output_fps,
                                "sha256": digest,
                            }
                        )
                    manifest["passes"][kind] = rows
                manifest["limits"] = (
                    "Strict inclusive source-frame map requires native smoke test. Raw 8-bit depth is unnormalized; "
                    "no per-frame contrast stretch. Native constraints are not baked by this renderer."
                )
                with open(
                    os.path.join(root, "manifest.json"), "x", encoding="utf-8"
                ) as stream:
                    json.dump(manifest, stream, indent=2)
            finally:
                try:
                    restored = icmcp_extra.set_render_output(restore_config)
                    if any(int(restored[k]) != v for k, v in restore_config.items()):
                        raise RuntimeError("Could not restore render settings")
                finally:
                    if original_camera is not None:
                        p.ok(
                            p.RLPy.RScene.SetCurrentCamera(original_camera),
                            "Restore camera",
                        )

    return p.execute(args, plan, [("render bundle", render)])


def inspect_glb(args):
    path = os.path.abspath(p.text(args["path"], "path"))
    size = os.path.getsize(path)
    if size > 256 * 1024 * 1024:
        raise ValueError("Structural inspection is limited to 256 MiB")
    with open(path, "rb") as stream:
        header = stream.read(12)
        if len(header) != 12:
            raise ValueError("Truncated GLB header")
        magic, version, declared = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2 or declared != size:
            raise ValueError("Invalid GLB magic/version/length")
        chunks = []
        while stream.tell() < size:
            raw = stream.read(8)
            if len(raw) != 8:
                raise ValueError("Truncated chunk header")
            length, kind = struct.unpack("<I4s", raw)
            if length % 4 or length > size - stream.tell():
                raise ValueError("Invalid GLB chunk length/alignment")
            chunks.append((kind, stream.read(length)))
    if not chunks or chunks[0][0] != b"JSON":
        raise ValueError("First GLB chunk must be JSON")
    doc = json.loads(chunks[0][1].decode("utf-8"))
    if not isinstance(doc, dict) or doc.get("asset", {}).get("version") != "2.0":
        raise ValueError("GLB JSON must describe glTF 2.0")
    if len(chunks) > 2 or len(chunks) == 2 and chunks[1][0] != b"BIN\x00":
        raise ValueError("Unexpected GLB chunk layout")
    for key in ("nodes", "meshes", "skins", "animations", "images", "buffers"):
        if not isinstance(doc.get(key, []), list):
            raise ValueError("%s must be a glTF array" % key)
    external = [
        item["uri"]
        for key in ("images", "buffers")
        for item in doc.get(key, [])
        if isinstance(item, dict)
        and "uri" in item
        and not item["uri"].startswith("data:")
    ]
    return {
        "path": path,
        "bytes": size,
        "structural_header_valid": True,
        "counts": {
            key: len(doc.get(key, []))
            for key in ("nodes", "meshes", "skins", "animations", "images")
        },
        "animation_names": [a.get("name", "") for a in doc.get("animations", [])],
        "external_resources": external,
        "limits": "Header/chunk/JSON checks only, not complete glTF validation or proof of animation, scale, materials or AR playback.",
    }


def export_animation_package(args):
    avatar = p._avatar(args["avatar"])
    path = os.path.abspath(p.text(args["path"], "path"))
    fmt = args.get("format", "glb")
    if fmt not in ("glb", "fbx") or not path.lower().endswith("." + fmt):
        raise ValueError("format/path extension mismatch")
    if (
        os.path.exists(path)
        or os.path.exists(path + ".manifest.json")
        or not os.path.isdir(os.path.dirname(path))
    ):
        raise ValueError(
            "Export and manifest paths must be NEW under an existing parent"
        )
    if not p.boolean(args.get("constraints_prebaked", False), "constraints_prebaked"):
        raise ValueError(
            "Bake constraints in a saved project copy first; then attest constraints_prebaked=true. "
            "This tool does not claim native all-constraint baking."
        )
    if fmt == "glb":
        p.method(p.RLPy.RFileIO, "ExportGlbFile")
        if not hasattr(p.RLPy, "RExportGlbSetting"):
            raise RuntimeError("RExportGlbSetting unavailable")
    else:
        p.method(p.RLPy.RFileIO, "ExportFbxFile")
    plan = {
        "avatar": avatar.GetName(),
        "path": path,
        "format": fmt,
        "constraints_prebaked": "caller attestation, not verified",
    }

    def export():
        from tools import project

        fn = project.export_glb if fmt == "glb" else project.export_fbx
        result = fn({"name": avatar.GetName(), "path": path})
        if (
            result.get("status") != "ok"
            or not os.path.isfile(path)
            or os.path.getsize(path) == 0
        ):
            raise RuntimeError("Export did not produce a nonempty file")
        metadata = dict(
            plan,
            bytes=os.path.getsize(path),
            project_fps=p.RLPy.RGlobal.GetFps().ToFloat(),
        )
        if fmt == "glb":
            metadata["glb_inspection"] = inspect_glb({"path": path})
        with open(path, "rb") as stream:
            metadata["sha256"] = hashlib.sha256(stream.read()).hexdigest()
        with open(path + ".manifest.json", "x", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2)

    return p.execute(args, plan, [("export + structural inspection", export)])


def register(registry):
    edit = {
        "execute": {"type": "boolean", "default": False},
        "backup_path": {"type": "string"},
    }

    def reg(name, fn, desc, props, req, mutating=False):
        registry[name] = {
            "handler": fn,
            "main_thread": True,
            "description": desc,
            "inputSchema": {
                "type": "object",
                "properties": dict(props, **(edit if mutating else {})),
                "required": req,
            },
        }

    shots = {"shots": {"type": "array", "items": {"type": "object"}}}
    reg(
        "validate_shot_list",
        validate_shot_list,
        "Validate all shot values and frame-aligned boundaries before editing cameras or switches.",
        shots,
        ["shots"],
    )
    reg(
        "build_shot_list_verified",
        build_shot_list_verified,
        "Preflight entire shot list before existing builder; dry run default, preserves switch keys unless clear_switch_keys=true. Builder still clears named camera transforms. New backup required.",
        dict(shots, clear_switch_keys={"type": "boolean"}),
        ["shots"],
        True,
    )
    reg(
        "schedule_face_performance",
        schedule_face_performance,
        "Schedule explicit-time expression keys on existing facial clips; validate every expression/strength/beat first. Dry run default; new backup required.",
        {
            "avatar": {"type": "string"},
            "beats": {"type": "array", "items": {"type": "object"}},
        },
        ["avatar", "beats"],
        True,
    )
    reg(
        "export_previz_bundle",
        export_previz_bundle,
        "Render aligned verified PNG passes and checksum/frame-map manifest to NEW directory. Output fps must equal project fps; strict inclusive frame counts. Restores camera/playhead/render settings. Dry run default; new backup required.",
        {
            "camera": {"type": "string"},
            "output_dir": {"type": "string"},
            "start_frame": {"type": "integer"},
            "end_frame": {"type": "integer"},
            "fps": {"type": "integer"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "passes": {"type": "array", "items": {"type": "string"}},
        },
        ["camera", "output_dir", "start_frame", "end_frame", "fps", "width", "height"],
        True,
    )
    reg(
        "inspect_glb",
        inspect_glb,
        "Inspect local GLB 2.0 header/chunks/JSON counts and external resources. NOT full glTF validation, motion validation or AR playback verification.",
        {"path": {"type": "string"}},
        ["path"],
    )
    reg(
        "export_animation_package",
        export_animation_package,
        "Export named avatar with checksum/metadata after caller attests constraints were prebaked. Does NOT bake constraints, choose clip ranges or optimize AR assets. GLB route experimental. Dry run default; new backup required.",
        {
            "avatar": {"type": "string"},
            "path": {"type": "string"},
            "format": {"type": "string", "enum": ["glb", "fbx"]},
            "constraints_prebaked": {"type": "boolean"},
        },
        ["avatar", "path", "constraints_prebaked"],
        True,
    )
