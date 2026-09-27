"""hoodtronik fork additions to gorbabor/mc-iclone8-mcp (registered at the end of main._tool_registry).
Tools: viewport_capture ("eyes") · python_exec · render_snapshot · render_control_pass · rename_object · find_content · load_motion_verified
# CLAUDE-NOTE (2026-09-26): separate module (one registration line in main.py) so upstream merges stay trivial.
# Measured on iClone 8.74 (2026-09-26):
#  - RenderImageSequence*(t, t, ...) with start == end pops a MODAL "Start time and end time are equal" reminder that blocks
#    iClone until a human clicks OK -> every range render here enforces end > start; single frames use RenderImage(path).
#  - Render paths must be Windows backslash paths (a forward-slash path returned Success and wrote nothing).
#  - No RLPy setter for project FPS (GUI-only); projects default to 60 fps -> render at 60, resample to 24 in ffmpeg.
#  - LoadMotion can return success while nothing moves -> load_motion_verified measures bone displacement.
#  - OpenPose = (RTime start, RTime end, ROpenPoseKeyPointParam, str path) (TypeError-proven 2026-08-29);
#    Depth/Normal/Canny assumed (start, end, path); a TypeError returns iClone's prototype text instead of guessing.
"""
import contextlib, io, json, os, time, traceback

import RLPy

_NS = {"RLPy": RLPy, "__name__": "icmcp_exec"}
CONTENT_ROOT = os.environ.get("ICMCP_CONTENT_ROOT", r"F:\iCLONE")
INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "content_index.json")
_EXT = {".imotion": "motion", ".rlmotion": "motion", ".imotionplus": "motion", ".iavatar": "avatar", ".iprop": "prop",
        ".iscene": "scene", ".iproject": "project", ".iaccessory": "accessory", ".itemplate": "template"}


def _win(path):
    return os.path.normpath(path).replace("/", "\\")


def _fps():
    return RLPy.RGlobal.GetFps()


def _t(frame):
    return _fps().IndexedFrameTime(int(frame))


def _avatar(name):
    for a in RLPy.RScene.GetAvatars():
        if a.GetName() == name:
            return a
    raise ValueError(f"no avatar named {name!r}; have {[a.GetName() for a in RLPy.RScene.GetAvatars()]}")


def _main_window():
    from PySide2 import QtWidgets
    from shiboken2 import wrapInstance
    return wrapInstance(int(RLPy.RUi.GetMainWindow()), QtWidgets.QMainWindow)


def viewport_capture(args):
    """EYES: grab the live iClone viewport (or the whole iClone window, dialogs included) — no render, ~instant.
    # CLAUDE-NOTE (2026-09-26): the 3D view is the native child window class CCoreWnd; QScreen.grabWindow(winId) returns the
    # real GL pixels (verified non-black 1575x1159). 'window' mode grabs the main window's screen rect so modal dialogs show.
    Returns an MCP image block (via the handler's _image_png_b64 hook) plus the saved path."""
    import base64
    from PySide2 import QtCore, QtWidgets, QtGui
    mw = _main_window()
    target = args.get("target", "viewport")
    scr = mw.windowHandle().screen()
    if target == "window":
        g, sg = mw.frameGeometry(), scr.geometry()
        pm = scr.grabWindow(0, g.x() - sg.x(), g.y() - sg.y(), g.width(), g.height())
    else:
        vps = [w for w in mw.findChildren(QtWidgets.QWidget) if w.metaObject().className() == "CCoreWnd" and w.isVisible()]
        if not vps:
            raise RuntimeError("viewport (CCoreWnd) not found — is the 3D view docked/visible?")
        vp = max(vps, key=lambda w: w.width() * w.height())
        pm = scr.grabWindow(int(vp.winId()))
    mwid = int(args.get("max_width", 1280))
    if pm.width() > mwid:
        pm = pm.scaledToWidth(mwid, QtCore.Qt.SmoothTransformation)
    path = _win(args.get("output_path") or os.path.join(os.environ.get("TEMP", r"C:\Temp"), "icmcp_eyes.png"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pm.save(path, "PNG")
    ba = QtCore.QByteArray()
    buf = QtCore.QBuffer(ba)
    buf.open(QtCore.QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    out = {"ok": True, "path": path, "size": [pm.width(), pm.height()], "target": target,
           "frame": _fps().GetFrameIndex(RLPy.RGlobal.GetTime()) if hasattr(_fps(), "GetFrameIndex") else None}
    if args.get("return_image", True):
        out["_image_png_b64"] = base64.b64encode(bytes(ba)).decode("ascii")
    return out


def python_exec(args):
    """Run Python inside iClone (main thread). Set _result to return a value; stdout is captured."""
    out = io.StringIO()
    _NS.pop("_result", None)
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(args.get("code", ""), "<icmcp>", "exec"), _NS)
    except Exception:
        return {"ok": False, "stdout": out.getvalue(), "error": traceback.format_exc()}
    res = _NS.get("_result")
    try:
        json.dumps(res)
    except Exception:
        res = repr(res)
    return {"ok": True, "stdout": out.getvalue(), "result": res}


def render_snapshot(args):
    """Render ONE still of the current camera (RenderImage) at an optional frame; verifies the file."""
    path = _win(args["output_path"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if args.get("frame") is not None:
        RLPy.RGlobal.SetTime(_t(args["frame"]))
    if os.path.exists(path):
        os.remove(path)
    status = RLPy.RGlobal.RenderImage(path)
    ok = os.path.exists(path) and os.path.getsize(path) > 0
    if not ok:  # some builds append an index or use the render-settings extension; look for a sibling
        stem = os.path.splitext(path)[0]
        sib = [f for f in os.listdir(os.path.dirname(path)) if f.startswith(os.path.basename(stem))]
        return {"ok": bool(sib), "status_success": status == RLPy.RStatus.Success, "written": sib}
    return {"ok": True, "path": path, "bytes": os.path.getsize(path)}


_PASSES = {"openpose": "RenderImageSequenceOpenPoseKeyPoint", "depth": "RenderImageSequenceDepth",
           "normal": "RenderImageSequenceNormal", "canny": "RenderImageSequenceCanny", "beauty": "RenderImageSequence"}


def render_control_pass(args):
    kind = args["pass"].lower()
    s, e = int(args["start_frame"]), int(args["end_frame"])
    if e <= s:
        raise ValueError("end_frame must be > start_frame (equal frames pop a blocking modal in iClone; use render_snapshot)")
    fn = getattr(RLPy.RGlobal, _PASSES[kind])
    path = _win(args["output_path"])
    folder = os.path.dirname(path) if os.path.splitext(path)[1] else path
    os.makedirs(folder, exist_ok=True)
    before = set(os.listdir(folder))
    t0 = time.time()
    try:
        if kind == "openpose":
            p = RLPy.ROpenPoseKeyPointParam()
            for k in ("bFace", "bHand", "bWholeHand", "bWholeFace"):
                if k in args:
                    setattr(p, k, bool(args[k]))
            status = fn(_t(s), _t(e), p, path)
        else:
            status = fn(_t(s), _t(e), path)
    except TypeError as err:
        return {"ok": False, "error": "signature mismatch — prototype from iClone: " + str(err)}
    new = sorted(set(os.listdir(folder)) - before)
    return {"ok": bool(new), "status_success": status == RLPy.RStatus.Success, "files_written": len(new),
            "first": new[:3], "folder": folder, "seconds": round(time.time() - t0, 1),
            "project_fps": _fps().ToFloat() if hasattr(_fps(), "ToFloat") else None}


def rename_object(args):
    objs = RLPy.RScene.FindObjects(RLPy.EObjectType_Object) if hasattr(RLPy, "EObjectType_Object") else []
    pool = list(RLPy.RScene.GetAvatars()) + list(RLPy.RScene.GetProps()) + list(objs)
    for o in pool:
        if o.GetName() == args["name"]:
            o.SetName(args["new_name"])
            return {"ok": o.GetName() == args["new_name"], "name": o.GetName()}
    raise ValueError(f"object {args['name']!r} not found")


def _build_index():
    items = []
    for root, _, files in os.walk(CONTENT_ROOT):
        for f in files:
            k = _EXT.get(os.path.splitext(f)[1].lower())
            if k:
                items.append([k, os.path.join(root, f)])
    with open(INDEX, "w", encoding="utf-8") as fh:
        json.dump({"root": CONTENT_ROOT, "built": time.time(), "items": items}, fh)
    return items


def find_content(args):
    """Search the local Reallusion content library by words in the path (all words must match)."""
    if args.get("rebuild") or not os.path.exists(INDEX):
        items = _build_index()
    else:
        with open(INDEX, encoding="utf-8") as fh:
            items = json.load(fh)["items"]
    words = [w.lower() for w in args.get("query", "").split()]
    kind = args.get("kind")
    hits = [p for k, p in items if (not kind or k == kind) and all(w in p.lower() for w in words)]
    lim = int(args.get("limit", 40))
    return {"total_indexed": len(items), "matches": len(hits), "results": hits[:lim], "root": CONTENT_ROOT}


def _bone_sample(av, frame):
    RLPy.RGlobal.SetTime(_t(frame))
    bones = av.GetSkeletonComponent().GetSkinBones()
    idx = [i for i in (0, len(bones) // 4, len(bones) // 2, (3 * len(bones)) // 4, len(bones) - 1) if 0 <= i < len(bones)]
    pts = []
    for i in idx:
        T = bones[i].WorldTransform().T()
        pts.append((T.x, T.y, T.z))
    return pts


def load_motion_verified(args):
    """Load a motion onto an avatar at a frame, then PROVE it applied by comparing bone positions across the clip."""
    av = _avatar(args["avatar"])
    frame = int(args.get("frame", 0))
    path = _win(args["path"])
    if not os.path.exists(path):
        raise ValueError(f"motion file not found: {path}")
    status = RLPy.RFileIO.LoadMotion(path, _t(frame), av)
    probe = int(args.get("probe_frames", 30))
    a, b = _bone_sample(av, frame), _bone_sample(av, frame + probe)
    moved = max(sum((p - q) ** 2 for p, q in zip(u, v)) ** 0.5 for u, v in zip(a, b)) if a and b else 0.0
    return {"ok": moved > 0.5, "max_bone_move_cm": round(moved, 2), "status_error": status.IsError() if hasattr(status, "IsError") else None,
            "clips": av.GetSkeletonComponent().GetClipCount()}


def register(registry):
    def reg(name, fn, desc, props, req):
        registry[name] = {"handler": fn, "main_thread": True, "description": desc,
                          "inputSchema": {"type": "object", "properties": props, "required": req}}
    reg("viewport_capture", viewport_capture, "EYES: instant screenshot of the live iClone 3D viewport (target=viewport) or the whole iClone window incl. dialogs (target=window). Returns the image. No render.",
        {"target": {"type": "string", "enum": ["viewport", "window"]}, "max_width": {"type": "integer"},
         "output_path": {"type": "string"}, "return_image": {"type": "boolean"}}, [])
    reg("python_exec", python_exec, "Run Python inside iClone 8 (RLPy imported; persistent namespace). Set _result to return a value.",
        {"code": {"type": "string"}}, ["code"])
    reg("render_snapshot", render_snapshot, "Render ONE still through the current camera (RenderImage) at an optional frame; verifies the file exists. Never pops the equal-time modal.",
        {"output_path": {"type": "string"}, "frame": {"type": "integer"}}, ["output_path"])
    reg("render_control_pass", render_control_pass, "Render an OpenPose / Depth / Normal / Canny / beauty image sequence for a frame range (end > start enforced; render size = project settings; project fps = iClone's, default 60). Verifies files were written.",
        {"pass": {"type": "string", "enum": list(_PASSES)}, "start_frame": {"type": "integer"}, "end_frame": {"type": "integer"},
         "output_path": {"type": "string", "description": "folder or file path prefix"}, "bFace": {"type": "boolean"},
         "bHand": {"type": "boolean"}, "bWholeHand": {"type": "boolean"}, "bWholeFace": {"type": "boolean"}},
        ["pass", "start_frame", "end_frame", "output_path"])
    reg("rename_object", rename_object, "Rename a scene avatar/prop/object.",
        {"name": {"type": "string"}, "new_name": {"type": "string"}}, ["name", "new_name"])
    reg("find_content", find_content, "Search the local Reallusion content library (default F:\\iCLONE) by path words; kind = motion|avatar|prop|scene|project|accessory|template. First call builds a cached index.",
        {"query": {"type": "string"}, "kind": {"type": "string"}, "limit": {"type": "integer"}, "rebuild": {"type": "boolean"}}, [])
    reg("load_motion_verified", load_motion_verified, "Load a motion file onto an avatar at a frame and verify it applied (bone displacement over probe_frames).",
        {"avatar": {"type": "string"}, "path": {"type": "string"}, "frame": {"type": "integer"}, "probe_frames": {"type": "integer"}},
        ["avatar", "path"])
