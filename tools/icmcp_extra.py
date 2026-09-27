"""hoodtronik fork additions to gorbabor/mc-iclone8-mcp (registered at the end of main._tool_registry).
Tools: viewport_capture ("eyes") · menu_action · list_menu · aim_camera · python_exec · render_snapshot · render_control_pass · rename_object · find_content · load_motion_verified
# CLAUDE-NOTE (2026-09-26): separate module (one registration line in main.py) so upstream merges stay trivial.
# Measured on iClone 8.74 (2026-09-26):
#  - RenderImageSequence*(t, t, ...) with start == end pops a MODAL "Start time and end time are equal" reminder that blocks
#    iClone until a human clicks OK -> every range render here enforces end > start; single frames use RenderImage(path).
#  - Render paths must be Windows backslash paths (a forward-slash path returned Success and wrote nothing).
#  - No RLPy setter for project FPS (GUI-only); projects default to 60 fps -> render at 60, resample to 24 in ffmpeg.
#  - LoadMotion can return success while nothing moves -> load_motion_verified measures bone displacement.
#  - Control-pass signatures + the blank-OpenPose trap: see render_control_pass docstring.
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
    # CLAUDE-NOTE (2026-09-26): a grab right after a camera/transform change returned the PREVIOUS frame (viewport had not
    # redrawn) -> nudge the timeline to the current time and pump events + a short settle before grabbing.
    RLPy.RGlobal.SetTime(RLPy.RGlobal.GetTime())
    for _ in range(int(args.get("settle_ms", 250)) // 25):
        QtWidgets.QApplication.processEvents()
        time.sleep(0.025)
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


def _menu_action_for(path):
    """Resolve 'Create > Camera > Linear Camera'. Menus are rebuilt on the fly (cached QMenu wrappers got deleted
    mid-walk), so every level is looked up fresh and aboutToShow is emitted to populate dynamic submenus."""
    from PySide2 import QtWidgets
    parts = [p.strip() for p in path.split(">")]
    actions = _main_window().menuBar().actions()
    for i, part in enumerate(parts):
        hit = next((a for a in actions if a.text().replace("&", "") == part), None)
        if hit is None:
            raise ValueError(f"menu item {part!r} not found in {' > '.join(parts[:i]) or 'menu bar'}; have "
                             f"{[a.text().replace('&', '') for a in actions if a.text()]}")
        if i == len(parts) - 1:
            return hit
        m = hit.menu()
        if m is None:
            raise ValueError(f"{part!r} is not a submenu")
        m.aboutToShow.emit()
        actions = m.actions()


def menu_action(args):
    """Trigger any iClone menu item by path (e.g. 'Create > Camera > Linear Camera'). Reports scene objects added."""
    def names():
        return {"cameras": [c.GetName() for c in RLPy.RScene.GetCameras()], "avatars": [a.GetName() for a in RLPy.RScene.GetAvatars()],
                "props": [p.GetName() for p in RLPy.RScene.GetProps()]}
    before = names()
    act = _menu_action_for(args["path"])
    if not act.isEnabled():
        raise RuntimeError(f"menu item {args['path']!r} is disabled right now")
    act.trigger()
    after = names()
    return {"ok": True, "path": args["path"], "added": {k: [n for n in after[k] if n not in before[k]] for k in after}}


def list_menu(args):
    out = []

    def walk(actions, path):
        for a in actions:
            t = a.text().replace("&", "")
            if not t:
                continue
            if a.menu():
                a.menu().aboutToShow.emit()
                walk(a.menu().actions(), path + [t])
            else:
                out.append(" > ".join(path + [t]))
    walk(_main_window().menuBar().actions(), [])
    pre = args.get("prefix", "")
    return {"items": [p for p in out if p.startswith(pre)]}


def _look_quaternion(pos, target, roll_deg=0.0):
    """Camera rest pose looks down local -Z with +Y up (measured 09-26: rotation 0 = straight-down top view, image-up = +Y)."""
    import math
    f = [t - p for t, p in zip(target, pos)]
    n = math.sqrt(sum(v * v for v in f)) or 1.0
    f = [v / n for v in f]
    up = [0.0, 0.0, 1.0] if abs(f[2]) < 0.999 else [0.0, 1.0, 0.0]
    r = [f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]]
    rn = math.sqrt(sum(v * v for v in r)); r = [v / rn for v in r]
    u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
    if roll_deg:
        c, s_ = math.cos(math.radians(roll_deg)), math.sin(math.radians(roll_deg))
        r, u = [c * a + s_ * b for a, b in zip(r, u)], [-s_ * a + c * b for a, b in zip(r, u)]
    z = [-v for v in f]
    m00, m01, m02 = r[0], u[0], z[0]
    m10, m11, m12 = r[1], u[1], z[1]
    m20, m21, m22 = r[2], u[2], z[2]
    tr = m00 + m11 + m22
    if tr > 0:
        S = math.sqrt(tr + 1.0) * 2; w = 0.25 * S; x = (m21 - m12) / S; y = (m02 - m20) / S; zq = (m10 - m01) / S
    elif m00 > m11 and m00 > m22:
        S = math.sqrt(1.0 + m00 - m11 - m22) * 2; w = (m21 - m12) / S; x = 0.25 * S; y = (m01 + m10) / S; zq = (m02 + m20) / S
    elif m11 > m22:
        S = math.sqrt(1.0 + m11 - m00 - m22) * 2; w = (m02 - m20) / S; x = (m01 + m10) / S; y = 0.25 * S; zq = (m12 + m21) / S
    else:
        S = math.sqrt(1.0 + m22 - m00 - m11) * 2; w = (m10 - m01) / S; x = (m02 + m20) / S; y = (m12 + m21) / S; zq = 0.25 * S
    return RLPy.RQuaternion(RLPy.RVector4(x, y, zq, w))


def aim_camera(args):
    """Place a scene camera at position looking at target (cm, Z up), optional roll/focal, keyed at frame (default current).
    Creates a Linear Camera via the menu if the scene has none and name is omitted."""
    cams = list(RLPy.RScene.GetCameras())
    name = args.get("name")
    if not cams and not name:
        menu_action({"path": "Create > Camera > Linear Camera"})
        cams = list(RLPy.RScene.GetCameras())
    cam = next((c for c in cams if c.GetName() == name), None) if name else cams[0]
    if cam is None:
        raise ValueError(f"camera {name!r} not found; have {[c.GetName() for c in cams]}")
    t = _t(args["frame"]) if args.get("frame") is not None else RLPy.RGlobal.GetTime()
    pos, tgt = args["position"], args["target"]
    P = [pos["x"], pos["y"], pos["z"]]; T = [tgt["x"], tgt["y"], tgt["z"]]
    q = _look_quaternion(P, T, float(args.get("roll_degrees", 0.0)))
    ctrl = cam.GetControl("Transform")
    if args.get("hold", False):   # a new camera already carries a creation key at frame 0 -> clear keys for a static shot
        ctrl.ClearKeys() if hasattr(ctrl, "ClearKeys") else None
        t = _t(0)
    ctrl.SetValue(t, RLPy.RTransform(RLPy.RVector3(1, 1, 1), q, RLPy.RVector3(*P)))
    if args.get("focal_length_mm"):
        cam.SetFocalLength(t, float(args["focal_length_mm"]))
    if args.get("make_current", True):
        RLPy.RScene.SetCurrentCamera(cam)
    return {"ok": True, "camera": cam.GetName(), "position": P, "target": T}


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


def _nonblank(path, step=20):
    """Count sampled pixels that are visible and non-black (a 'successful' render can be fully transparent)."""
    from PySide2 import QtGui
    im = QtGui.QImage(path)
    n = 0
    for y in range(0, im.height(), step):
        for x in range(0, im.width(), step):
            c = QtGui.QColor.fromRgba(im.pixel(x, y))
            if c.alpha() > 0 and (c.red() + c.green() + c.blue()) > 0:
                n += 1
    return n


def render_control_pass(args):
    """# CLAUDE-NOTE (2026-09-26): measured signatures on iClone 8.74 —
    OpenPose (t0, t1, ROpenPoseKeyPointParam, path): the default param renders FULLY TRANSPARENT frames; strPoseFormat must be
      "COCO" ("", "BODY_25", "OpenPose" all blank) and gizmo scales/opacity must be set (1 = ~1 px lines, 100 = blobs).
    Depth (t0, t1, RDepthParam, path) · Normal (t0, t1, path) · Canny (t0, t1, REdgeDetectionCannyParam, path).
    Output rate follows the Render panel's frame rate (30 by default), not the 60 fps project."""
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
            p.strPoseFormat = args.get("pose_format", "COCO")
            sc = float(args.get("gizmo_scale", 6.0))
            p.fOpacity = 1.0
            for k in ("fBoneGizmoScale", "fBoneNubGizmoScale", "fHandGizmoScale", "fHandNubGizmoScale", "fFaceGizmoScale"):
                setattr(p, k, sc)
            p.fVisibleFacialGizmoPercentage = 1.0
            for k in ("bFace", "bHand", "bWholeHand", "bWholeFace", "bEnableEars", "bCheckBodyBlocking"):
                if k in args:
                    setattr(p, k, bool(args[k]))
            status = fn(_t(s), _t(e), p, path)
        elif kind == "depth":
            p = RLPy.RDepthParam()
            p.b16BitPng = bool(args.get("depth_16bit", False))
            p.bEnhanced = bool(args.get("depth_enhanced", False))
            status = fn(_t(s), _t(e), p, path)
        elif kind == "canny":
            # CLAUDE-NOTE (2026-09-26): Canny with a default REdgeDetectionCannyParam() CRASHED iClone 8.74 (process died after
            # ~3 frames; scene lost). Blocked unless explicitly allowed; save the project first. Make Canny from beauty in ffmpeg/OpenCV instead.
            if not args.get("allow_crash_risk"):
                raise RuntimeError("canny pass crashed iClone 8.74 with default params — derive Canny from the beauty pass "
                                   "outside iClone, or pass allow_crash_risk=true after saving the project")
            status = fn(_t(s), _t(e), RLPy.REdgeDetectionCannyParam(), path)
        else:
            status = fn(_t(s), _t(e), path)
    except TypeError as err:
        return {"ok": False, "error": "signature mismatch — prototype from iClone: " + str(err)}
    new = sorted(set(os.listdir(folder)) - before)
    visible = _nonblank(os.path.join(folder, new[len(new) // 2])) if new else 0
    return {"ok": bool(new) and visible > 0, "status_success": status == RLPy.RStatus.Success, "files_written": len(new),
            "mid_frame_visible_samples": visible, "first": new[:3], "folder": folder, "seconds": round(time.time() - t0, 1),
            "note": "" if visible else "frames are EMPTY (transparent/black) — check camera, pose_format, gizmo_scale"}


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
    reg("menu_action", menu_action, "Trigger any iClone menu item by path, e.g. 'Create > Camera > Linear Camera' or 'Create > Primitive Shape > Box'. Reports objects added. Items that open dialogs will block until closed.",
        {"path": {"type": "string"}}, ["path"])
    reg("list_menu", list_menu, "List iClone menu item paths (optionally filtered by prefix, e.g. 'Create').", {"prefix": {"type": "string"}}, [])
    reg("aim_camera", aim_camera, "Place a SCENE camera at position looking at target (cm, Z up), optional roll_degrees / focal_length_mm, keyed at frame. Creates a Linear Camera if none exists. The Preview Camera cannot be animated.",
        {"name": {"type": "string"}, "position": {"type": "object"}, "target": {"type": "object"}, "roll_degrees": {"type": "number"},
         "focal_length_mm": {"type": "number"}, "frame": {"type": "integer"}, "make_current": {"type": "boolean"},
         "hold": {"type": "boolean", "description": "clear existing transform keys and hold this pose for the whole shot"}}, ["position", "target"])
    reg("python_exec", python_exec, "Run Python inside iClone 8 (RLPy imported; persistent namespace). Set _result to return a value.",
        {"code": {"type": "string"}}, ["code"])
    reg("render_snapshot", render_snapshot, "Render ONE still through the current camera (RenderImage) at an optional frame; verifies the file exists. Never pops the equal-time modal.",
        {"output_path": {"type": "string"}, "frame": {"type": "integer"}}, ["output_path"])
    reg("render_control_pass", render_control_pass, "Render an OpenPose / Depth / Normal / Canny / beauty image sequence for a frame range (end > start enforced; render size = project settings; project fps = iClone's, default 60). Verifies files were written.",
        {"pass": {"type": "string", "enum": list(_PASSES)}, "start_frame": {"type": "integer"}, "end_frame": {"type": "integer"},
         "output_path": {"type": "string", "description": "folder or file path prefix"}, "bFace": {"type": "boolean"},
         "bHand": {"type": "boolean"}, "bWholeHand": {"type": "boolean"}, "bWholeFace": {"type": "boolean"},
         "pose_format": {"type": "string", "description": "default COCO (other values rendered blank)"}, "gizmo_scale": {"type": "number"},
         "depth_16bit": {"type": "boolean"}, "depth_enhanced": {"type": "boolean"}, "allow_crash_risk": {"type": "boolean"}},
        ["pass", "start_frame", "end_frame", "output_path"])
    reg("rename_object", rename_object, "Rename a scene avatar/prop/object.",
        {"name": {"type": "string"}, "new_name": {"type": "string"}}, ["name", "new_name"])
    reg("find_content", find_content, "Search the local Reallusion content library (default F:\\iCLONE) by path words; kind = motion|avatar|prop|scene|project|accessory|template. First call builds a cached index.",
        {"query": {"type": "string"}, "kind": {"type": "string"}, "limit": {"type": "integer"}, "rebuild": {"type": "boolean"}}, [])
    reg("load_motion_verified", load_motion_verified, "Load a motion file onto an avatar at a frame and verify it applied (bone displacement over probe_frames).",
        {"avatar": {"type": "string"}, "path": {"type": "string"}, "frame": {"type": "integer"}, "probe_frames": {"type": "integer"}},
        ["avatar", "path"])
