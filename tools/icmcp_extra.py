"""hoodtronik fork additions to gorbabor/mc-iclone8-mcp (registered at the end of main._tool_registry).
Tools: viewport_capture ("eyes") · menu_action · list_menu · aim_camera · python_exec · render_snapshot · render_control_pass · rename_object · find_content · load_motion_verified · set_look_at
# CLAUDE-NOTE (2026-09-26): separate module (one registration line in main.py) so upstream merges stay trivial.
# Measured on iClone 8.74 (2026-09-26):
#  - RenderImageSequence*(t, t, ...) with start == end pops a MODAL "Start time and end time are equal" reminder that blocks
#    iClone until a human clicks OK -> every range render here enforces end > start; single frames use RenderImage(path).
#  - Render paths must be Windows backslash paths (a forward-slash path returned Success and wrote nothing).
#  - No RLPy setter for project FPS; since 2026-10-07 set_project_fps drives the Project panel combo instead (Qt tier).
#  - LoadMotion can return success while nothing moves -> load_motion_verified measures bone displacement.
#  - Control-pass signatures + the blank-OpenPose trap: see render_control_pass docstring.
"""
import contextlib, io, json, os, time, traceback

import RLPy

_NS = {"RLPy": RLPy, "__name__": "icmcp_exec"}
CONTENT_ROOT = os.environ.get("ICMCP_CONTENT_ROOT", r"F:\iCLONE")
INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "content_index.json")
_EXT = {".imotion": "motion", ".rlmotion": "motion", ".imotionplus": "motion", ".iavatar": "avatar", ".iprop": "prop",
        ".iscene": "scene", ".iproject": "project", ".iaccessory": "accessory", ".itemplate": "template",
        ".ipath": "path"}   # CLAUDE-NOTE (2026-10-07): loading a template .iPath is the proven way to create a path


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
    now = RLPy.RGlobal.GetTime()
    fps_ = _fps()
    fi = fps_.GetFrameIndex(now) if hasattr(fps_, "GetFrameIndex") else 0
    # CLAUDE-NOTE (2026-10-07, measured): on an unattended launch the GL view stops repainting while the window is not
    # active — grabs returned the same pixels after moving objects; RGlobal.ForceViewportUpdate() did NOT help, but
    # activateWindow()+raise_() did (hash changed). So activate first, then the time nudge below.
    mw.activateWindow(); mw.raise_(); QtWidgets.QApplication.processEvents()
    RLPy.RGlobal.SetTime(_t(fi + 1))      # re-setting the SAME time does not redraw (stale grab 09-26); step off and back
    QtWidgets.QApplication.processEvents()
    RLPy.RGlobal.SetTime(now)
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


def _key_transform(ctrl, frame_time, transform):
    """Write a transform key; if the control has NO keys yet and this isn't frame 0, key frame 0 first.
    # CLAUDE-NOTE (2026-09-26, Ilyas): "always do your first keyframe at frame 0 for the transform at least" — iClone
    # auto-keys, and an object whose first key is later than 0 drifts/pops before it."""
    keys = ctrl.GetKeyCount() if hasattr(ctrl, "GetKeyCount") else 1
    if keys == 0 and frame_time != _t(0):
        ctrl.SetValue(_t(0), transform)
    ctrl.SetValue(frame_time, transform)


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
    _key_transform(ctrl, t, RLPy.RTransform(RLPy.RVector3(1, 1, 1), q, RLPy.RVector3(*P)))
    if args.get("focal_length_mm"):
        cam.SetFocalLength(t, float(args["focal_length_mm"]))
    if args.get("make_current", True):
        RLPy.RScene.SetCurrentCamera(cam)
    return {"ok": True, "camera": cam.GetName(), "position": P, "target": T}


def _fps_value():
    f = _fps()
    for attr in ("ToFloat", "GetFpsValue", "ToDouble"):
        if hasattr(f, attr):
            try:
                return float(getattr(f, attr)())
            except Exception:
                pass
    return 60.0


def _sec(s):
    return _t(int(round(float(s) * _fps_value())))


def _camera_named(name):
    cam = next((c for c in RLPy.RScene.GetCameras() if c.GetName() == name), None)
    if cam is None:
        added = menu_action({"path": "Create > Camera > Linear Camera"})["added"]["cameras"]
        cam = next(c for c in RLPy.RScene.GetCameras() if c.GetName() == added[0])
        cam.SetName(name)
    return cam


def build_shot_list(args):
    """Multi-shot previz: one named camera per shot, keyed start (and optional end) framing, lens, and a camera-switch key
    at each shot start so the timeline cuts like an edit. Times in SECONDS (fps-agnostic).
    shots: [{id, start_s, end_s, position, target, focal_length_mm, end_position?, end_target?, end_focal_length_mm?, roll_degrees?}]"""
    shots = args["shots"]
    if args.get("clear_switch_keys", True):
        RLPy.RScene.ClearSwitchCameraKeys()
    done = []
    for sh in shots:
        cam = _camera_named(sh["id"])
        cam.SetNearClippingPlane(int(sh.get("near_cm", 1)))    # inherited 10/600 from the active camera; close work needs ~1 cm
        cam.SetFarClippingPlane(int(sh.get("far_cm", 3000)))   # int-typed in RLPy
        ctrl = cam.GetControl("Transform")
        ctrl.ClearKeys()
        for which, tkey in (("", "start_s"), ("end_", "end_s")):
            pos, tgt = sh.get(which + "position"), sh.get(which + "target")
            if which and not (pos or tgt):
                continue
            pos = pos or sh["position"]; tgt = tgt or sh["target"]
            P = [pos["x"], pos["y"], pos["z"]]; T = [tgt["x"], tgt["y"], tgt["z"]]
            t = _sec(sh[tkey] if which == "" else sh["end_s"] - 1.0 / _fps_value())
            tr = RLPy.RTransform(RLPy.RVector3(1, 1, 1), _look_quaternion(P, T, float(sh.get("roll_degrees", 0.0))), RLPy.RVector3(*P))
            if which == "":
                ctrl.SetValue(_t(0), tr)          # first key always at frame 0 (Ilyas rule) — holds the opening pose until the cut
            ctrl.SetValue(t, tr)
            f = sh.get(which + "focal_length_mm") or sh.get("focal_length_mm")
            if f:
                if which == "":
                    cam.SetFocalLength(_t(0), float(f))   # lens also gets its first key at frame 0 (else it reads 24 mm before the cut)
                cam.SetFocalLength(t, float(f))
        RLPy.RScene.AddSwitchCameraKey(_sec(sh["start_s"]), cam)
        done.append({"id": sh["id"], "camera": cam.GetName(), "start_s": sh["start_s"], "end_s": sh["end_s"]})
    mode = _set_camera_mode("Switch")   # CLAUDE-NOTE (2026-10-07): without Switch mode, renders ignore the cuts (measured)
    return {"ok": True, "shots": done, "camera_mode": mode, "switch_cuts": _switch_cuts()}


def set_render_output(args):
    """Render panel output: fps (e.g. 24), width/height, frame range (project frames). Reads back what iClone kept."""
    p = RLPy.RGlobal.GetRenderExportImageSequenceParameter()
    p = p[0] if isinstance(p, (list, tuple)) else p
    c = p.kCommon
    if "fps" in args:
        c.kFps = str(int(args["fps"]))          # kFps is a wstring ('24'), NOT an RFps (measured 09-26)
    if "width" in args:
        c.nOutputSizeWidth = int(args["width"])
    if "height" in args:
        c.nOutputSizeHeight = int(args["height"])
    p.kCommon = c
    RLPy.RGlobal.SetRenderExportParameter(p)   # returns Failure even when applied -> trust the read-back
    q = RLPy.RGlobal.GetRenderExportImageSequenceParameter()
    q = q[0] if isinstance(q, (list, tuple)) else q
    return {"fps": q.kCommon.kFps, "width": q.kCommon.nOutputSizeWidth, "height": q.kCommon.nOutputSizeHeight,
            "range": [q.kOutputRange.nOutputRangeStart, q.kOutputRange.nOutputRangeEnd]}


def place_object(args):
    """Place an avatar/prop so it HOLDS: transform written at frame 0 (default) with other transform keys cleared.
    # CLAUDE-NOTE (2026-09-26, Ilyas): iClone auto-keys — any transform change at the current frame becomes a KEY, so an
    # object set at frame 40 animates in from its frame-0 pose. Upstream set_transform writes at the CURRENT time; for
    # blocking use this (clear_keys=false keeps existing keys and just adds/overwrites the frame-0 key)."""
    from tools.objects import find_by_name
    from tools.common import euler_degrees_to_quaternion
    obj = find_by_name(args["name"])
    ctrl = obj.GetControl("Transform")
    if args.get("clear_keys", True):
        ctrl.ClearKeys()
    t = _t(int(args.get("frame", 0)))
    cur = obj.LocalTransform()
    pos = args.get("position"); rot = args.get("rotation_degrees")
    P = RLPy.RVector3(pos["x"], pos["y"], pos["z"]) if pos else cur.T()
    Q = euler_degrees_to_quaternion(rot.get("x", 0), rot.get("y", 0), rot.get("z", 0)) if rot else cur.R()
    ctrl.SetValue(t, RLPy.RTransform(cur.S(), Q, P))
    W = obj.WorldTransform(); T = W.T()
    return {"ok": True, "name": obj.GetName(), "frame": int(args.get("frame", 0)), "position_now": [T.x, T.y, T.z],
            "transform_keys": ctrl.GetKeyCount() if hasattr(ctrl, "GetKeyCount") else None}


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
    """Count sampled pixels that are visible and non-black (a 'successful' render can be fully transparent).
    numpy/PIL ship with iClone's Python (verified 09-26); handles 8/16-bit, L/RGB/RGBA."""
    import numpy as np
    from PIL import Image
    a = np.array(Image.open(path))[::step, ::step]
    if a.ndim == 3 and a.shape[2] == 4:
        a = np.where(a[..., 3:4] > 0, a[..., :3], 0)
    return int((a.reshape(a.shape[0], a.shape[1], -1).max(axis=2) > 0).sum())


def _normalize_depth(folder, files, lo_pct=1.0, hi_pct=99.0):
    """# CLAUDE-NOTE (2026-09-26): iClone depth is squashed near white (subjects 252-254 of 255, even with far clip 600 cm or
    'enhanced'), so stretch the FOREGROUND range per frame to 0..255 (near = bright, background stays 0) — ControlNet style."""
    import numpy as np
    from PIL import Image
    for f in files:
        p = os.path.join(folder, f)
        a = np.array(Image.open(p).convert("L")).astype(np.float32)
        fg = a > 0
        if fg.sum() < 50:
            continue
        lo, hi = np.percentile(a[fg], lo_pct), np.percentile(a[fg], hi_pct)
        out = np.zeros_like(a)
        out[fg] = np.clip((a[fg] - lo) / max(hi - lo, 1e-3), 0, 1) * 235 + 20
        Image.fromarray(out.astype(np.uint8)).save(p)


def _exr_depth_to_png(xdir, exrs, folder):
    import numpy as np
    from PIL import Image
    from tools import exr_zip
    for f in exrs:
        d = exr_zip.read(os.path.join(xdir, f))
        R = d.get("R", next(iter(d.values())))
        A = d.get("A")
        fg = (A > 0.5) if A is not None else (R > 0)
        out = np.zeros(R.shape, np.uint8)
        if fg.sum() > 10:
            v = R[fg]
            rank = np.argsort(np.argsort(v, kind="stable"), kind="stable") / max(len(v) - 1, 1)
            out[fg] = (20 + rank * 235).astype(np.uint8)       # larger value = nearer (measured: foreground actor brighter)
        Image.fromarray(out).save(os.path.join(folder, os.path.splitext(f)[0] + ".png"))


def _canny_from(folder_src, files, folder_dst, low=80, high=180):
    import cv2
    os.makedirs(folder_dst, exist_ok=True)
    for f in files:
        img = cv2.imread(os.path.join(folder_src, f), cv2.IMREAD_GRAYSCALE)
        cv2.imwrite(os.path.join(folder_dst, f.replace("beauty", "canny")), cv2.Canny(cv2.GaussianBlur(img, (3, 3), 0), low, high))


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
    if args.get("camera"):   # render through an explicit camera — the current camera can change under us (project load, UI)
        cam = next((c for c in RLPy.RScene.GetCameras() if c.GetName() == args["camera"]), None)
        if cam is None:
            raise ValueError(f"camera {args['camera']!r} not found; have {[c.GetName() for c in RLPy.RScene.GetCameras()]}")
        RLPy.RScene.SetCurrentCamera(cam)
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
            # CLAUDE-NOTE (2026-09-26): 8-bit depth has ~3 grey levels on subjects (useless). b16BitPng=True really writes
            # half-float EXR (677 levels) -> decoded with tools/exr_zip.py and histogram-equalized over the foreground to an
            # 8-bit PNG (near = bright, background 0). Set depth_raw_png=true for iClone's own 8-bit PNG instead.
            p = RLPy.RDepthParam()
            p.bEnhanced = bool(args.get("depth_enhanced", False))
            if args.get("depth_raw_png"):
                status = fn(_t(s), _t(e), p, path)
            else:
                p.b16BitPng = True
                xdir = os.path.join(folder, "_exr")
                os.makedirs(xdir, exist_ok=True)
                x_before = set(os.listdir(xdir))
                stem = os.path.splitext(os.path.basename(path))[0] if os.path.splitext(path)[1] else "depth"
                status = fn(_t(s), _t(e), p, os.path.join(xdir, stem + ".png"))
                _exr_depth_to_png(xdir, sorted(f for f in set(os.listdir(xdir)) - x_before if f.lower().endswith(".exr")), folder)
        elif kind == "canny":
            # CLAUDE-NOTE (2026-09-26): iClone's RenderImageSequenceCanny with a default REdgeDetectionCannyParam CRASHED iClone
            # 8.74 (scene lost). Canny is derived from a beauty render with OpenCV instead (cv2 ships in iClone's Python).
            if args.get("allow_crash_risk"):
                status = fn(_t(s), _t(e), RLPy.REdgeDetectionCannyParam(), path)
            else:
                bdir = os.path.join(folder, "_beauty_src")
                os.makedirs(bdir, exist_ok=True)
                b_before = set(os.listdir(bdir))
                status = RLPy.RGlobal.RenderImageSequence(_t(s), _t(e), os.path.join(bdir, "beauty.png"))
                _canny_from(bdir, sorted(set(os.listdir(bdir)) - b_before), folder,
                            int(args.get("canny_low", 80)), int(args.get("canny_high", 180)))
        else:
            status = fn(_t(s), _t(e), path)
    except TypeError as err:
        return {"ok": False, "error": "signature mismatch — prototype from iClone: " + str(err)}
    new = sorted(f for f in set(os.listdir(folder)) - before if f.lower().endswith(".png"))
    if kind == "depth" and args.get("depth_raw_png") and args.get("normalize", True) and new:
        _normalize_depth(folder, new)
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
        W = bones[i].WorldTransform(); T = W.T()
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


def _head_q(sc, frame):
    """World rotation (x, y, z, w) of the avatar's head bone at `frame`, after the stale-read nudge (see viewport_capture)."""
    from PySide2 import QtWidgets
    RLPy.RGlobal.SetTime(_t(frame + 1)); QtWidgets.QApplication.processEvents()
    RLPy.RGlobal.SetTime(_t(frame)); QtWidgets.QApplication.processEvents()
    bones = sc.GetSkinBones()
    head = [b for b in bones if b.GetName() == "CC_Base_Head"] or [b for b in bones if "head" in b.GetName().lower()] or [sc.GetRootBone()]
    W = head[0].WorldTransform(); q = W.R()
    return (q.x, q.y, q.z, q.w)


def _q_angle_deg(a, b):
    import math
    return math.degrees(2 * math.acos(min(1.0, abs(sum(p * q for p, q in zip(a, b))))))


def set_look_at(args):
    """Key an avatar's LOOK AT track: look at a prop/camera (object mode), at another avatar's bone (bone mode, default
    CC_Base_Head, with transition + head/body weights), or release. PROVEN-RUNTIME on iClone 8.75.5630.1 (2026-10-07).
    # CLAUDE-NOTE (2026-10-07): RISkeletonComponent.GetLookAtComponent() -> RILookAtComponent.AddLookAtKey has two SWIG
    # overloads, recovered by mis-calling it: (RTime, RIObjectPtr) and (RTime, RTime transition, RINodePtr, head_w, body_w).
    # Props/cameras are RIObjects -> 2-arg only (SWIG rejects a RIProp as RINode, so no transition/weights for them). Bones
    # are RINodes -> 5-arg. An avatar passed as RIObject is looked at by its PIVOT (feet), hence bone mode for avatars.
    # target None = release key; the head eases back over the following ~1 s. The transition ramps IN BEFORE the key time
    # (measured 0 deg at key-30f, full at the key). The head/body weight datablock controls stayed 0.7/0.3 after a 1.0/0.0
    # call, so weights are NOT read back; proof = world-rotation delta of CC_Base_Head at the key and after the ramp."""
    from tools.objects import find_by_name
    av = _avatar(args["avatar"])
    sc = av.GetSkeletonComponent()
    if not hasattr(sc, "GetLookAtComponent"):
        raise RuntimeError("this iClone build has no RISkeletonComponent.GetLookAtComponent (tool measured on 8.75.5630.1)")
    la = sc.GetLookAtComponent()
    frame, ramp = int(args.get("frame", 0)), int(args.get("transition_frames", 30))
    now = RLPy.RGlobal.GetTime()
    probe = (frame, frame + max(ramp, 1), frame + 60)
    before = {f: _head_q(sc, f) for f in probe}
    target_name, bone_name = args.get("target"), args.get("bone")
    if args.get("release") or not target_name:
        mode, target_name, bone_name = "release", None, None
        status = la.AddLookAtKey(_t(frame), None)
    else:
        target = find_by_name(target_name)
        is_avatar = isinstance(target, RLPy.RIAvatar)   # RIProp also has GetSkeletonComponent -> hasattr misfires (measured)
        if bone_name is None and is_avatar:
            bone_name = "CC_Base_Head"
        if bone_name:
            if not is_avatar:
                raise ValueError(f"bone targets need an avatar; {target_name!r} is not one")
            bones = target.GetSkeletonComponent().GetSkinBones()
            node = next((b for b in bones if b.GetName() == bone_name), None)
            if node is None:
                raise ValueError(f"bone {bone_name!r} not on {target_name!r}; head/eye bones: "
                                 f"{[b.GetName() for b in bones if 'head' in b.GetName().lower() or 'eye' in b.GetName().lower()]}")
            mode = "bone"
            status = la.AddLookAtKey(_t(frame), _t(ramp), node, float(args.get("head_weight", 0.7)), float(args.get("body_weight", 0.3)))
        else:
            mode = "object"
            status = la.AddLookAtKey(_t(frame), target)
    after = {f: _head_q(sc, f) for f in probe}
    RLPy.RGlobal.SetTime(now)
    deltas = {str(f): round(_q_angle_deg(before[f], after[f]), 1) for f in probe}
    err = status.IsError() if hasattr(status, "IsError") else None
    moved = max(deltas.values()) > 1.0
    return {"ok": not err, "avatar": av.GetName(), "mode": mode, "target": target_name, "bone": bone_name, "frame": frame,
            "status_error": err, "head_moved": moved, "head_turn_deg": deltas,
            "note": None if moved else "head rotation unchanged: nothing to release, or the target is already in view"}


def _scene_summary():
    return {"avatars": [a.GetName() for a in RLPy.RScene.GetAvatars()],
            "props": [p.GetName() for p in RLPy.RScene.GetProps() if p.GetName() != "Shadow Catcher"],
            "cameras": [c.GetName() for c in RLPy.RScene.GetCameras()]}


def _save_current_first(args):
    """Both session tools silently DISCARD unsaved work (measured 2026-10-07: no save prompt on a dirty scene), so the tracked
    project is saved first unless save_current=false. An untitled scene has nothing to save to and is reported as such."""
    from tools.common import current_project_path, scene_is_empty
    from tools.project import save_project
    if not args.get("save_current", True):
        return {"saved_previous": False, "reason": "save_current=false"}
    prev = current_project_path()
    if not prev:
        return {"saved_previous": False, "reason": "untitled scene (no tracked project path)"}
    if scene_is_empty():
        return {"saved_previous": False, "reason": f"scene is empty; not overwriting {prev} (tracked path may be stale)"}
    if save_project({"path": prev}).get("status") != "ok":
        raise RuntimeError(f"refusing to continue: checkpoint save to {prev} failed")
    return {"saved_previous": True, "saved_to": prev}


def load_project(args):
    """Open an .iProject IN-SESSION (no relaunch). PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): RFileIO.LoadProject(path) returned
    in 2.2 s, raised NO save prompt on a dirty scene, invalidated every old object handle and restored the saved transforms.
    # CLAUDE-NOTE (2026-10-07): because it discards silently, the tracked current project is saved first (_save_current_first)
    # and the loaded path becomes the tracked project, so later checkpoint saves go to the file that is actually open."""
    from tools.common import set_current_project
    path = _win(args["path"])
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    pre = _save_current_first(args)
    t0 = time.time()
    status = RLPy.RFileIO.LoadProject(path)
    err = status.IsError() if hasattr(status, "IsError") else None
    if not err:
        set_current_project(path)
    return {"ok": not err, "path": path, "status_error": err, "load_seconds": round(time.time() - t0, 1), **pre, **_scene_summary()}


def new_project(args):
    """Start an EMPTY project in-session through the File > New Project menu action (RLPy has no symbol for it).
    PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): 0.7 s, no save prompt even with unsaved changes.
    # CLAUDE-NOTE (2026-10-07): the tracked project is saved first, then the tracked path is CLEARED (clear_current_project)
    # so a later checkpoint save cannot overwrite the old project with this empty scene."""
    from tools.common import clear_current_project
    pre = _save_current_first(args)
    r = menu_action({"path": "File > New Project"})
    scene = _scene_summary()
    empty = not (scene["avatars"] or scene["props"] or scene["cameras"])
    if empty:
        clear_current_project()
    return {"ok": bool(r.get("ok")) and empty, **pre, **scene,
            "note": None if empty else "scene not empty after New Project: a prompt may be open, check list_dialogs"}


_RANGE_FIELDS = (("project_length", "GetProjectLength", "SetProjectLength"), ("start", "GetStartTime", "SetStartTime"),
                 ("end", "GetEndTime", "SetEndTime"), ("preview_start", "GetPreviewStartTime", "SetPreviewStartTime"),
                 ("preview_end", "GetPreviewEndTime", "SetPreviewEndTime"))


def set_timeline_range(args):
    """Set project length, play range (start/end) and preview range, in frames (default) or seconds, with read-back.
    PROVEN-RUNTIME 8.75.5630.1 (2026-10-07) on RGlobal.SetProjectLength / SetStartTime / SetEndTime / SetPreviewStart|EndTime.
    # CLAUDE-NOTE (2026-10-07, measured): setting project_length clamps end and preview_end to it and pulls the playhead
    # inside; end may exceed project_length (accepted, not clamped); shrinking the length does NOT delete keys beyond it
    # (they return when it grows again). Fields are applied in _RANGE_FIELDS order so a length change is clamped first and
    # explicit start/end/preview values win. ok = every requested value reads back exactly."""
    fps = _fps()
    unit = args.get("unit", "frames")
    if unit not in ("frames", "seconds"):
        raise ValueError("unit must be 'frames' or 'seconds'")
    to_frame = (lambda v: int(round(float(v) * fps.ToFloat()))) if unit == "seconds" else (lambda v: int(v))
    requested, errors = {}, {}
    for key, _getter, setter in _RANGE_FIELDS:
        if args.get(key) is not None:
            requested[key] = to_frame(args[key])
            status = getattr(RLPy.RGlobal, setter)(_t(requested[key]))
            errors[key] = status.IsError() if hasattr(status, "IsError") else None
    if not requested:
        raise ValueError(f"nothing to set; pass any of {[k for k, _, _ in _RANGE_FIELDS]}")
    from PySide2 import QtWidgets
    QtWidgets.QApplication.processEvents()
    now = {key: fps.GetFrameIndex(getattr(RLPy.RGlobal, getter)()) for key, getter, _ in _RANGE_FIELDS}
    now["current"] = fps.GetFrameIndex(RLPy.RGlobal.GetTime())
    mismatch = {k: {"requested": v, "now": now[k]} for k, v in requested.items() if now[k] != v}
    return {"ok": not any(errors.values()) and not mismatch, "fps": fps.ToFloat(), "requested_frames": requested,
            "status_error": errors, "frames_now": now, "mismatch": mismatch or None}


def _clip_rows(sk):
    fps = _fps(); out = []
    for i in range(sk.GetClipCount()):
        c = sk.GetClip(i)
        start = fps.GetFrameIndex(c.ClipTimeToSceneTime(RLPy.RTime.FromValue(0)))
        out.append({"index": i, "start_frame": start, "end_frame": start + fps.GetFrameIndex(c.GetClipLength()), "speed": round(c.GetSpeed(), 3)})
    return out


def _hip_hands(sk, frame):
    from PySide2 import QtWidgets
    RLPy.RGlobal.SetTime(_t(frame + 1)); QtWidgets.QApplication.processEvents()
    RLPy.RGlobal.SetTime(_t(frame)); QtWidgets.QApplication.processEvents()
    d = {}
    for b in sk.GetSkinBones():
        if b.GetName() in ("CC_Base_Hip", "CC_Base_L_Hand", "CC_Base_R_Hand"):
            W = b.WorldTransform(); v = W.T(); d[b.GetName()[8:]] = [round(v.x, 1), round(v.y, 1), round(v.z, 1)]
    return d


def edit_clip(args):
    """Clip surgery on an avatar's motion track: op = break (split at frame) | merge (clip index + the next one) |
    mirror (clip index) | delete (clip index). PROVEN-RUNTIME 8.75.5630.1 (2026-10-07) on RISkeletonComponent.BreakClip /
    MergeClips / MirrorClip / DeleteClip (all Experimental APIs). Proof = clip rows before/after; mirror also returns
    hip/hand world positions at `probe_frame`.
    # CLAUDE-NOTE (2026-10-07, measured): MirrorClip mirrors in WORLD X — the whole motion incl. root (hip x −149 → +149),
    # so an actor standing off-centre jumps to the other side; re-place it afterwards. Break at frame f gives [start,f] and
    # [f,end]; Merge needs two adjacent clips; after Break both halves report speed 1.0 (speed is baked into length)."""
    av = _avatar(args["avatar"]); sk = av.GetSkeletonComponent(); op = args.get("op")
    before = _clip_rows(sk)
    probe = int(args.get("probe_frame", 30))
    extra = {}
    if op == "break":
        status = sk.BreakClip(_t(int(args["frame"])))
    elif op in ("merge", "mirror", "delete"):
        i = int(args.get("clip", 0))
        if i >= len(before) or (op == "merge" and i + 1 >= len(before)):
            raise ValueError(f"{op}: need clip index {i}{' and ' + str(i + 1) if op == 'merge' else ''}; have {before}")
        if op == "merge":
            status = sk.MergeClips(sk.GetClip(i), sk.GetClip(i + 1))
        elif op == "mirror":
            extra["pose_before"] = _hip_hands(sk, probe)
            status = sk.MirrorClip(sk.GetClip(i))
        else:
            status = sk.DeleteClip(sk.GetClip(i))
    else:
        raise ValueError("op must be break | merge | mirror | delete")
    from PySide2 import QtWidgets
    QtWidgets.QApplication.processEvents()
    after = _clip_rows(sk)
    err = status.IsError() if hasattr(status, "IsError") else None
    if op == "mirror":
        extra["pose_after"] = _hip_hands(sk, probe)
        changed = extra["pose_before"] != extra["pose_after"]
    else:
        changed = before != after
    return {"ok": (not err) and changed, "avatar": av.GetName(), "op": op, "status_error": err, "clips_before": before,
            "clips_after": after, "changed": changed, **extra}


def _wav_stats(path):
    """(seconds, peak, nonzero_samples) of a PCM wav, or None if unreadable."""
    import struct, wave
    try:
        w = wave.open(path); n, fr, sw = w.getnframes(), w.getframerate(), w.getsampwidth(); data = w.readframes(n); w.close()
        vals = struct.unpack("<%d%s" % (len(data) // sw, {1: "b", 2: "h", 4: "i"}[sw]), data)
        return {"seconds": round(n / fr, 3), "peak": max((abs(v) for v in vals), default=0), "nonzero_samples": sum(1 for v in vals if v)}
    except Exception as e:
        return {"error": str(e)}


def render_audio(args):
    """Render the mixed scene audio for a frame range to a wav (RGlobal.RenderAudio) and analyse it. PROVEN-RUNTIME
    8.75.5630.1 (2026-10-07): 120 frames -> 2.0 s stereo 48 kHz wav in ~0.2 s, no dialog. end > start enforced (same
    equal-time modal family as the image renders)."""
    start, end = int(args["start_frame"]), int(args["end_frame"])
    if end <= start:
        raise ValueError("end_frame must be > start_frame")
    out = _win(args["output_path"])
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if os.path.exists(out):
        os.remove(out)
    status = RLPy.RGlobal.RenderAudio(_t(start), _t(end), out)
    err = status.IsError() if hasattr(status, "IsError") else None
    exists = os.path.exists(out)
    return {"ok": (not err) and exists and os.path.getsize(out) > 0, "path": out, "status_error": err,
            "bytes": os.path.getsize(out) if exists else 0, **(_wav_stats(out) if exists else {})}


def load_audio(args):
    """Put an audio file on an object's sound track at `frame` (RAudio.LoadAudioToObject). PROVEN-RUNTIME 8.75.5630.1
    (2026-10-07) with RenderAudio as the proof: the rendered window was non-silent afterwards.
    # CLAUDE-NOTE (2026-10-07, measured): the call's float return is NOT a success flag — a MISSING file returned the same
    # 5.572 as the real one (= the real clip's duration, i.e. the track's existing content). So the file is checked first and,
    # with verify=true (default), a 1 s window at `frame` is rendered before and after and compared; ok requires a change."""
    from tools.objects import find_by_name
    obj = find_by_name(args["object"])
    # CLAUDE-NOTE (2026-10-07, measured): LoadAudioToObject on a CAMERA killed iClone 8.75 outright (process gone, twice);
    # avatars and props take it. Fail closed on anything else.
    if not isinstance(obj, (RLPy.RIAvatar, RLPy.RIProp)):
        raise ValueError(f"{args['object']!r} is a {type(obj).__name__}; audio only goes on avatars or props (a camera crashed iClone)")
    path = _win(args["path"])
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    frame, loops = int(args.get("frame", 0)), int(args.get("loop_count", 1))
    fade_in, fade_out = int(args.get("fade_in_frames", 0)), int(args.get("fade_out_frames", 0))
    verify = args.get("verify", True)
    tmp = os.path.join(os.environ.get("TEMP", "."), "icmcp_audio_probe_%s.wav")
    before = render_audio({"start_frame": frame, "end_frame": frame + 60, "output_path": tmp % "before"}) if verify else None
    reported = RLPy.RAudio.LoadAudioToObject(obj, path, _t(frame), loops, _t(fade_in), _t(fade_out))
    after = render_audio({"start_frame": frame, "end_frame": frame + 60, "output_path": tmp % "after"}) if verify else None
    changed = None
    if verify:
        changed = (before.get("peak"), before.get("nonzero_samples")) != (after.get("peak"), after.get("nonzero_samples"))
        for f in (tmp % "before", tmp % "after"):
            if os.path.exists(f):
                os.remove(f)
    return {"ok": bool(reported) and (changed is not False), "object": obj.GetName(), "path": path, "frame": frame,
            "reported_seconds": reported, "verified": verify, "audio_changed": changed,
            "window_peak_before": before.get("peak") if before else None, "window_peak_after": after.get("peak") if after else None}


def _project_dock():
    from PySide2 import QtWidgets
    docks = [d for d in _main_window().findChildren(QtWidgets.QDockWidget) if d.windowTitle() == "Project"]
    if not docks:
        raise RuntimeError("no 'Project' dock panel found (Edit > Project Settings); iClone build changed?")
    return docks[0]


def set_project_fps(args):
    """Set the PROJECT frame rate (12/24/25/30/60/120) through the Project panel's FPS combo — Tier C (Qt): RLPy has no
    setter. PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): combo 60 -> 24 read back as RGlobal.GetFps() 24.0, project length
    1800 -> 720 frames (same seconds), no prompt. Readback through RLPy is the proof; the panel is hidden again if it was.
    # CLAUDE-NOTE (2026-10-07): 'Edit > Project Settings' is a CHECKABLE action toggling the 'Project' QDockWidget (not a
    # dialog); the combo is objectName 'qtFpsComboBox' and reacts to setCurrentIndex + activated(idx). This does not touch
    # the Render panel fps (set_render_output). Not the `fps` of existing motion clips either — they re-time."""
    from PySide2 import QtWidgets
    want = str(int(args["fps"]))
    before = _fps().ToFloat()
    len_before = _fps().GetFrameIndex(RLPy.RGlobal.GetProjectLength())
    dock = _project_dock()
    was_visible = dock.isVisible()
    dock.show(); QtWidgets.QApplication.processEvents()
    combo = dock.findChild(QtWidgets.QComboBox, "qtFpsComboBox")
    if combo is None:
        raise RuntimeError("Project panel has no qtFpsComboBox (iClone build changed?)")
    choices = [combo.itemText(i) for i in range(combo.count())]
    idx = combo.findText(want)
    if idx < 0:
        raise ValueError(f"fps {want} not offered by iClone; choices: {choices}")
    combo.setCurrentIndex(idx); QtWidgets.QApplication.processEvents()
    combo.activated.emit(idx); QtWidgets.QApplication.processEvents()
    if not was_visible:
        dock.hide()
    after = _fps().ToFloat()
    return {"ok": abs(after - float(want)) < 0.01, "fps_before": before, "fps_now": after, "choices": choices,
            "project_length_frames_before": len_before, "project_length_frames_now": _fps().GetFrameIndex(RLPy.RGlobal.GetProjectLength())}


_WALK_MOTION = os.path.join(CONTENT_ROOT, "Custom", "iClone 7 Custom", "MographMotion", "02_Female", "Walk.iMotion")
_IDLE_MOTION = os.path.join(CONTENT_ROOT, "Custom", "iClone 7 Custom", "MographMotion", "02_Female", "Stand00.iMotion")


def _hip_xy(sk, frame):
    from PySide2 import QtWidgets
    RLPy.RGlobal.SetTime(_t(frame + 3)); QtWidgets.QApplication.processEvents()
    RLPy.RGlobal.SetTime(_t(frame)); QtWidgets.QApplication.processEvents()
    for b in sk.GetSkinBones():
        if b.GetName() == "CC_Base_Hip":
            W = b.WorldTransform(); v = W.T(); return (round(v.x, 1), round(v.y, 1))
    W = sk.GetRootBone().WorldTransform(); v = W.T(); return (round(v.x, 1), round(v.y, 1))


def walk_to(args):
    """Blocking move: the avatar walks in a straight line from `from` (default: where it is at start_frame) to `to`, facing
    the travel direction. A ROOT-MOTION walk clip (default iClone 7 Walk.iMotion, ~76 cm/s) carries the distance: the tool
    calibrates the clip on this avatar, scales its speed for speed_cm_s / duration_s, chains as many copies as the distance
    needs (keying each boundary at the measured hip position) and trims the last one to arrive. Proof = CC_Base_Hip xy at
    the arrival frame vs `to` (hip_error_cm).
    # CLAUDE-NOTE (2026-10-07, all measured): heading 0 faces -Y, +h CCW -> heading = atan2(dx, -dy). Transform keys ADD to
    # root motion, so every key here is a STEP key. SetLength past a clip's natural length holds the last pose instead of
    # continuing the travel, and a clip loaded after another RESTARTS from the avatar transform -> one clip per ~420 cm, a
    # Step key at each boundary at the measured hip xy. Root-motion distance is sub-linear in SetSpeed (1.53x -> 1.25x), so
    # speed and the final length are corrected by measurement, never modelled. The iClone 8 template Walk_2Loop barely
    # moved the legs on ActorCore avatars, and the foot bone z is pinned at the floor-contact offset (useless as a metric).
    # replace_clips=true (default) wipes the motion track first, like motion_track."""
    import math
    from PySide2 import QtWidgets
    from tools.common import euler_degrees_to_quaternion
    av = _avatar(args["avatar"]); sk = av.GetSkeletonComponent(); fps = _fps(); fsec = fps.ToFloat()
    start = int(args.get("start_frame", 0))
    ctrl = av.GetControl("Transform")
    RLPy.RGlobal.SetTime(_t(start)); QtWidgets.QApplication.processEvents()
    cur = RLPy.RTransform(); ctrl.GetValue(_t(start), cur)
    frm = args.get("from") or {"x": cur.T().x, "y": cur.T().y, "z": cur.T().z}
    to = args["to"]
    z = float(to.get("z", frm.get("z", cur.T().z)))
    fx, fy, tx, ty = float(frm["x"]), float(frm["y"]), float(to["x"]), float(to["y"])
    dist = math.hypot(tx - fx, ty - fy)
    if dist < 1.0:
        raise ValueError("destination is within 1 cm of the start; nothing to walk")
    heading = round(math.degrees(math.atan2(tx - fx, -(ty - fy))), 2)
    q = euler_degrees_to_quaternion(0, 0, heading)

    def step_key(frame, x, y):
        ctrl.SetValue(_t(frame), RLPy.RTransform(cur.S(), q, RLPy.RVector3(float(x), float(y), z)))
        ctrl.SetKeyTransition(_t(frame), RLPy.ETransitionType_Step, 50.0)

    if ctrl.GetKeyCount() == 0 and start > 0:
        step_key(0, fx, fy)
    step_key(start, fx, fy)
    path = _win(args.get("motion", _WALK_MOTION))
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    from tools.fight_tools import _delete_all_clips
    if args.get("replace_clips", True):
        _delete_all_clips(sk)

    def load_clip(frame, speed):
        before = sk.GetClipCount()
        RLPy.RFileIO.LoadMotion(path, _t(frame), av)
        if sk.GetClipCount() <= before:
            raise RuntimeError(f"LoadMotion added no clip for {os.path.basename(path)}")
        clip = sk.GetClipByTime(_t(frame + 1)) or sk.GetClip(sk.GetClipCount() - 1)
        clip.SetSpeed(speed)
        natural = clip.GetClipLength().ToInt() / 6000.0   # GetClipLength is SCENE seconds (already speed-adjusted, measured)
        return clip, max(1, int(round(natural * fsec)))

    def travelled(x0, y0, frame):
        h = _hip_xy(sk, frame); return math.hypot(h[0] - x0, h[1] - y0), h

    # calibration: one clip at the estimated speed -> per-clip distance and achieved pace
    speed = 1.0
    calib = []
    for _ in range(3):
        clip, n = load_clip(start, speed)
        d_clip, _h = travelled(fx, fy, start + n)
        if d_clip < 5.0:
            raise RuntimeError(f"{os.path.basename(path)} has no usable root motion on {av.GetName()} ({d_clip:.1f} cm per clip)")
        pace = d_clip / (n / fsec)
        calib.append({"clip_speed": round(speed, 3), "cm_per_clip": round(d_clip, 1), "pace_cm_s": round(pace, 1)})
        wanted = (dist / float(args["duration_s"])) if args.get("duration_s") else float(args.get("speed_cm_s", 0) or 0)
        sk.DeleteClip(clip)
        if not wanted or abs(pace - wanted) / wanted < 0.05:
            break
        speed *= wanted / pace
    # build the chain
    x, y, t, remaining, clips_used = fx, fy, start, dist, 0
    while remaining > 5.0 and clips_used < 12:
        clip, n = load_clip(t, speed)
        clips_used += 1
        d_clip, h = travelled(x, y, t + n)
        if d_clip < remaining - 5.0:
            x, y, t, remaining = h[0], h[1], t + n, remaining - d_clip
            step_key(t, x, y)
            continue
        # last clip: trim so the hip lands on `to` (two measured corrections for the start-up ramp)
        frames = max(1, int(round(n * remaining / d_clip)))
        for _ in range(3):
            clip.SetLength(RLPy.RTime.FromValue(int(round(frames / fsec * speed * 6000))))
            QtWidgets.QApplication.processEvents()
            d_now, h = travelled(x, y, t + frames)
            if abs(d_now - remaining) < 5.0 or d_now < 1.0:
                break
            frames = max(1, int(round(frames * remaining / d_now)))
        t, x, y, remaining = t + frames, h[0], h[1], 0.0
    end = t
    hip_end = _hip_xy(sk, end)
    err_end = round(math.hypot(hip_end[0] - tx, hip_end[1] - ty), 1)
    step_key(end + 1, hip_end[0], hip_end[1])
    idle = None
    if args.get("idle_after", True):
        # CLAUDE-NOTE (2026-10-07): outside any clip iClone shows the bind pose, so park the avatar in an in-place idle
        # from arrival to the project end (Stand00 measured in-place); the Step key at end+1 keeps the position.
        ipath = _win(args.get("idle_motion", _IDLE_MOTION))
        if os.path.isfile(ipath):
            RLPy.RFileIO.LoadMotion(ipath, _t(end + 1), av)
            iclip = sk.GetClipByTime(_t(end + 2))
            proj_end = fps.GetFrameIndex(RLPy.RGlobal.GetProjectLength())
            hold = max(1, proj_end - (end + 1))
            if iclip is not None:
                iclip.SetLength(RLPy.RTime.FromValue(int(round(hold / fsec * iclip.GetSpeed() * 6000))))
                QtWidgets.QApplication.processEvents()
                h_idle = _hip_xy(sk, min(proj_end, end + 1 + hold // 2))
                idle = {"motion": os.path.basename(ipath), "hold_frames": hold, "hip_drift_cm": round(math.hypot(h_idle[0] - hip_end[0], h_idle[1] - hip_end[1]), 1)}
        else:
            idle = {"error": f"idle motion not found: {ipath}"}
    return {"ok": err_end < 30.0, "avatar": av.GetName(), "from": {"x": fx, "y": fy}, "to": {"x": tx, "y": ty},
            "heading_deg": heading, "distance_cm": round(dist, 1), "start_frame": start, "end_frame": end,
            "duration_s": round((end - start) / fsec, 3), "clip_speed": round(speed, 3), "calibration": calib,
            "clips_used": clips_used, "clips": _clip_rows(sk), "hip_end_xy": hip_end, "hip_error_cm": err_end, "idle": idle}


_MOTION_IMPORT_TITLE = "Motion Import Settings"


def _motion_import_dialog():
    from PySide2 import QtWidgets
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.isVisible() and isinstance(w, QtWidgets.QDialog) and _MOTION_IMPORT_TITLE in w.windowTitle():
            return w
    return None


def _new_files(folder, before, exts=(".rlmotion", ".imotion")):
    try:
        return sorted(f for f in os.listdir(folder) if f.lower().endswith(exts) and f not in before)
    except OSError:
        return []


def convert_external_motion(args):
    """Convert a Mixamo / Rokoko / Xsens / ... FBX (or BVH) motion to an iClone .rlMotion through iClone's own
    'File > Import > Convert External Motion' flow, which auto-detects the source rig (Motion Profile). PROVEN-RUNTIME
    8.75.5630.1 (2026-10-07): a skinless Mixamo X-Bot fight_idle.fbx -> fight_idle.rlMotion in ~5 s, played back on an
    ActorCore avatar (fists-up render). Runs on the HTTP thread: the native Windows 'Open' dialog blocks the Qt main
    thread, so the path is typed into it with SendInput, then the Qt 'Motion Import Settings' dialog is driven through
    the main thread (dispatch.run).
    # CLAUDE-NOTE (2026-10-07): RFileIO.ConvertFbxFileToRLMotion failed outright on these files and LoadFbxFile imported
    # the skeleton as a prop; the UI route is the one that works (Ilyas: "iClone has its own conversion module with
    # presets - Mixamo is one of them"). Qt dialog objectNames: qtCharacterProfileComboBox, qtMotionFolderLineEdit,
    # qtMotionFpsRadioButton / qtCustomFpsRadioButton + qtSampleLineEdit, qtKeepRootMotionCheckbox, qtConvertPushButton."""
    from dispatch import run
    from tools import native_ui
    src = _win(args["path"])
    if not os.path.isfile(src):
        raise FileNotFoundError(src)
    timeout = float(args.get("timeout_s", 90))

    def fire_menu():
        from PySide2 import QtCore
        act = _menu_action_for("File > Import > Convert External Motion")
        if not act.isEnabled():
            raise RuntimeError("'Convert External Motion' menu item is disabled")
        QtCore.QTimer.singleShot(200, act.trigger)
        return True
    run(fire_menu)
    hwnd = native_ui.wait_window("Open", 15)
    if hwnd is None:
        raise RuntimeError("the native 'Open' file dialog did not appear within 15 s")
    native_ui.type_text(hwnd, src, enter=True)
    # the Qt settings dialog follows; it still services the bridge
    t0, dlg_info = time.time(), None
    while time.time() - t0 < 30 and dlg_info is None:
        time.sleep(0.5)

        def read_dialog():
            from PySide2 import QtWidgets
            w = _motion_import_dialog()
            if w is None:
                return None
            combo = w.findChild(QtWidgets.QComboBox, "qtCharacterProfileComboBox")
            folder = w.findChild(QtWidgets.QLineEdit, "qtMotionFolderLineEdit")
            return {"profiles": [combo.itemText(i) for i in range(combo.count())], "detected_profile": combo.currentText(),
                    "folder": folder.text()}
        dlg_info = run(read_dialog)
    if dlg_info is None:
        raise RuntimeError("'Motion Import Settings' dialog did not appear (is the file a supported motion FBX/BVH?)")
    want_profile = args.get("profile")
    if want_profile and want_profile not in dlg_info["profiles"]:
        run(lambda: _motion_import_dialog().findChild(__import__("PySide2").QtWidgets.QPushButton, "qtCancelPushButton").click())
        raise ValueError(f"profile {want_profile!r} not offered; choices: {dlg_info['profiles']}")
    folder = _win(args.get("motion_folder") or dlg_info["folder"])
    os.makedirs(folder, exist_ok=True)
    before = set(os.listdir(folder))

    def configure_and_convert():
        from PySide2 import QtWidgets, QtCore
        w = _motion_import_dialog()
        if want_profile:
            c = w.findChild(QtWidgets.QComboBox, "qtCharacterProfileComboBox"); c.setCurrentIndex(c.findText(want_profile)); c.activated.emit(c.currentIndex())
        if args.get("motion_folder"):
            w.findChild(QtWidgets.QLineEdit, "qtMotionFolderLineEdit").setText(folder)
        if args.get("force_fps"):
            w.findChild(QtWidgets.QRadioButton, "qtCustomFpsRadioButton").setChecked(True)
            w.findChild(QtWidgets.QLineEdit, "qtSampleLineEdit").setText(str(int(args["force_fps"])))
        kr = w.findChild(QtWidgets.QCheckBox, "qtKeepRootMotionCheckbox")
        if kr is not None and kr.isEnabled() and "keep_root_motion" in args:
            kr.setChecked(bool(args["keep_root_motion"]))
        used = w.findChild(QtWidgets.QComboBox, "qtCharacterProfileComboBox").currentText()
        QtCore.QTimer.singleShot(100, w.findChild(QtWidgets.QPushButton, "qtConvertPushButton").click)
        return used
    used_profile = run(configure_and_convert)
    t0, produced = time.time(), []
    while time.time() - t0 < timeout:
        time.sleep(1.0)

        def takes_page():
            from PySide2 import QtWidgets, QtCore
            w = _motion_import_dialog()
            if w is None:
                return "closed"
            proceed = w.findChild(QtWidgets.QPushButton, "qtProceedPushButton")
            if proceed is not None and proceed.isVisible():
                sel = w.findChild(QtWidgets.QPushButton, "qtSelectAllPushButton")
                if sel is not None and sel.isVisible():
                    sel.click()
                QtCore.QTimer.singleShot(100, proceed.click)
                return "proceeded"
            return "open"
        state = run(takes_page)
        produced = _new_files(folder, before)
        if produced and state == "closed":
            break
    return {"ok": bool(produced), "source": src, "profiles_offered": dlg_info["profiles"], "detected_profile": dlg_info["detected_profile"],
            "profile_used": used_profile, "motion_folder": folder, "produced": [os.path.join(folder, f) for f in produced],
            "seconds": round(time.time() - t0, 1), "note": None if produced else "no new motion file appeared; check list_dialogs / the Motion Folder"}


def _path_position_spin(obj):
    """The Modify > Attribute 'Path Position (%)' spin box for the selected follower (section is built lazily)."""
    from PySide2 import QtWidgets
    RLPy.RScene.SelectObject(obj); QtWidgets.QApplication.processEvents()
    mod = [d for d in _main_window().findChildren(QtWidgets.QDockWidget) if d.windowTitle() == "Modify"]
    if not mod:
        raise RuntimeError("no 'Modify' dock found")
    mod = mod[0]
    for bar in mod.findChildren(QtWidgets.QTabBar):
        if bar.count() and bar.tabText(0) == "Attribute":
            bar.setCurrentIndex(0); QtWidgets.QApplication.processEvents()
    labels = [l for l in mod.findChildren(QtWidgets.QLabel, "Position") if l.text().startswith("Path Position")]
    if not labels:
        raise RuntimeError(f"{obj.GetName()} shows no 'Path Position (%)' field: pick a path first (follow_path / path=)")
    spin = labels[0].parentWidget().findChild(QtWidgets.QDoubleSpinBox, "qtDoubleSpinBox")
    if spin is None:
        raise RuntimeError("Path Position spin box not found next to its label (iClone build changed?)")
    return spin


def path_position_key(args):
    """Key WHERE an object is along its path at `frame`, in percent (0 = start, 100 = end, 200 = twice round), via the
    Modify panel's Path Position (%) field — the only route that creates a key. PROVEN-RUNTIME 8.75.5630.1 (2026-10-07):
    50 % at frame 60 on a circle → key count 1→2, prop at the quarter point at frame 30 and the half point at 60.
    # CLAUDE-NOTE (2026-10-07): RLPy's PathPosition.SetValue returns Success but never creates a key (upstream
    # set_path_position is a silent no-op) and AddKey(RFloatKey) crashes iClone; the UI spin box's setter is what works.
    # The RFloatControl stores 0..1 while the UI shows 0..100 — readback divides accordingly. Optional path= picks the
    # path first (obj.FollowPath at `frame`, snapping the object to the path start)."""
    from PySide2 import QtWidgets
    from tools.objects import find_by_name
    obj = find_by_name(args["object"])
    frame, pct = int(args.get("frame", 0)), float(args["percent"])
    if args.get("path"):
        st = obj.FollowPath(find_by_name(args["path"]), _t(frame))
        if hasattr(st, "IsError") and st.IsError():
            raise RuntimeError(f"FollowPath failed for {args['object']!r} on {args['path']!r}")
    ctl = obj.GetControl("PathPosition")
    keys_before = ctl.GetKeyCount() if ctl else None
    now = RLPy.RGlobal.GetTime()
    RLPy.RGlobal.SetTime(_t(frame)); QtWidgets.QApplication.processEvents()
    spin = _path_position_spin(obj)
    spin.setValue(pct); QtWidgets.QApplication.processEvents()
    spin.editingFinished.emit(); QtWidgets.QApplication.processEvents()
    ctl = obj.GetControl("PathPosition")
    RLPy.RGlobal.SetTime(_t(frame + 7)); QtWidgets.QApplication.processEvents()
    RLPy.RGlobal.SetTime(_t(frame)); QtWidgets.QApplication.processEvents()
    value = ctl.GetValue(_t(frame), 0.0)[1] * 100.0 if ctl else None
    W = obj.WorldTransform(); v = W.T()
    if max(abs(v.x), abs(v.y), abs(v.z)) > 1e7:
        # CLAUDE-NOTE (2026-10-07, measured): the first WorldTransform read right after the key write returned ~1e17 garbage
        # once (camera, 100 % key); a second nudge + read was correct.
        RLPy.RGlobal.SetTime(_t(frame + 1)); QtWidgets.QApplication.processEvents()
        RLPy.RGlobal.SetTime(_t(frame)); QtWidgets.QApplication.processEvents()
        W = obj.WorldTransform(); v = W.T()
    RLPy.RGlobal.SetTime(now)
    keys_after = ctl.GetKeyCount() if ctl else None
    return {"ok": value is not None and abs(value - pct) < 0.5, "object": obj.GetName(), "frame": frame, "percent": pct,
            "percent_now": round(value, 2) if value is not None else None, "keys_before": keys_before, "keys_after": keys_after,
            "position_at_frame": [round(v.x, 1), round(v.y, 1), round(v.z, 1)]}


def _set_camera_mode(name):
    """Select an entry of the toolbar camera list ('Preview', 'Switch', or a camera name); returns the entry now shown.
    # CLAUDE-NOTE (2026-10-07, measured): the Switcher track only drives the view and RenderImage when this combo
    # (objectName qtCameraSwitchAction) is on 'Switch' — manual 20-Scene/Camera/Multiple_Camera_Switcher, last step."""
    from PySide2 import QtWidgets
    combo = _main_window().findChild(QtWidgets.QComboBox, "qtCameraSwitchAction")
    if combo is None:
        raise RuntimeError("toolbar camera list (qtCameraSwitchAction) not found")
    i = combo.findText(name)
    if i < 0:
        raise ValueError(f"{name!r} not in the camera list: {[combo.itemText(k) for k in range(combo.count())]}")
    combo.setCurrentIndex(i); combo.activated.emit(i); QtWidgets.QApplication.processEvents()
    return combo.currentText()


def _switch_cuts():
    """Switcher track as [{frame, camera}] (GetSwitchCameraFrameIndexs pairs are (RIObject camera, frame index))."""
    out = []
    for p in RLPy.RScene.GetSwitchCameraFrameIndexs(_fps()):
        cam, frame = p[0], p[1]
        out.append({"frame": int(frame), "camera": cam.GetName() if hasattr(cam, "GetName") else str(cam)})
    return sorted(out, key=lambda r: r["frame"])


def camera_cuts(args):
    """Write the Project > Switcher track: cuts=[{frame, camera}] (replace=true clears existing cuts first), turn the
    toolbar camera list to 'Switch' so playback and renders follow the cuts, then read everything back and report which
    camera is live at the middle of each shot. PROVEN-RUNTIME 8.75.5630.1 (2026-10-07): 3 cuts read back, GetCurrentCamera
    followed them in Switch mode, and a render at frame 70 came from the second camera."""
    from PySide2 import QtWidgets
    from tools.objects import find_by_name
    cuts = sorted(args["cuts"], key=lambda c: int(c["frame"]))
    cams = {c["camera"]: find_by_name(c["camera"]) for c in cuts}
    for n, c in cams.items():
        if not isinstance(c, RLPy.RICamera):
            raise ValueError(f"{n!r} is not a camera")
    if args.get("replace", True):
        RLPy.RScene.ClearSwitchCameraKeys()
    for c in cuts:
        st = RLPy.RScene.AddSwitchCameraKey(_t(int(c["frame"])), cams[c["camera"]])
        if hasattr(st, "IsError") and st.IsError():
            raise RuntimeError(f"AddSwitchCameraKey failed at frame {c['frame']}")
    mode = _set_camera_mode("Switch") if args.get("switch_mode", True) else None
    now = RLPy.RGlobal.GetTime()
    end = _fps().GetFrameIndex(RLPy.RGlobal.GetEndTime())
    live = []
    for i, c in enumerate(cuts):
        nxt = int(cuts[i + 1]["frame"]) if i + 1 < len(cuts) else max(int(c["frame"]) + 2, end)
        mid = (int(c["frame"]) + nxt) // 2
        RLPy.RGlobal.SetTime(_t(mid)); QtWidgets.QApplication.processEvents()
        live.append({"frame": mid, "expected": c["camera"], "live": RLPy.RScene.GetCurrentCamera().GetName()})
    RLPy.RGlobal.SetTime(now)
    readback = _switch_cuts()
    ok = [(r["frame"], r["camera"]) for r in readback] == [(int(c["frame"]), c["camera"]) for c in cuts] if args.get("replace", True) else True
    ok = ok and (mode != "Switch" or all(l["expected"] == l["live"] for l in live))
    return {"ok": ok, "camera_mode": mode, "switch_cuts": readback, "live_check": live}


def _q_forward(q):
    """World-space view direction of a camera rotation (camera rest pose looks down local -Z)."""
    x, y, z, w = q.x, q.y, q.z, q.w
    return (-(2 * (x * z + w * y)), -(2 * (y * z - w * x)), -(1 - 2 * (x * x + y * y)))


def _target_xyz(obj, bone_name=None):
    if bone_name and isinstance(obj, RLPy.RIAvatar):
        for b in obj.GetSkeletonComponent().GetSkinBones():
            if b.GetName() == bone_name:
                W = b.WorldTransform(); v = W.T(); return (v.x, v.y, v.z)
        raise ValueError(f"bone {bone_name!r} not on {obj.GetName()}")
    W = obj.WorldTransform(); v = W.T(); return (v.x, v.y, v.z)


def track_target(args):
    """Camera (or spotlight) FOLLOWS a moving target: bakes look-at rotation keys every `every` frames from start_frame to
    end_frame, keeping the camera's own (possibly animated) position. Avatar targets default to the head bone.
    Proof = aim error in degrees at the middle sample (camera forward vs direction to target).
    # CLAUDE-NOTE (2026-10-07): iClone's native Look At (Modify > Attribute > Look At: qtLookAtSubNodeToolButton 'Pick
    # Target', qtLookAtLineEdit, qtSetFreePushButton; manual 54-Look-At) needs a viewport pick, so this bakes the
    # equivalent with the proven aim_camera math (_look_quaternion; camera looks down local -Z). Position is read at each
    # sample frame before keying so a camera already moving (e.g. on a path) keeps its motion."""
    import math
    from PySide2 import QtWidgets
    from tools.objects import find_by_name
    cam = find_by_name(args["camera"]); tgt = find_by_name(args["target"])
    bone = args.get("bone") or ("CC_Base_Head" if isinstance(tgt, RLPy.RIAvatar) else None)
    start, end, every = int(args.get("start_frame", 0)), int(args["end_frame"]), max(1, int(args.get("every", 2)))
    if end <= start:
        raise ValueError("end_frame must be > start_frame")
    roll = float(args.get("roll_degrees", 0.0))
    ctrl = cam.GetControl("Transform")
    now = RLPy.RGlobal.GetTime()
    frames = list(range(start, end + 1, every))
    if frames[-1] != end:
        frames.append(end)
    samples = []
    for f in frames:   # read all positions first, then key, so new keys do not alter later reads
        RLPy.RGlobal.SetTime(_t(f)); QtWidgets.QApplication.processEvents()
        W = cam.WorldTransform(); Pv = W.T(); P = (Pv.x, Pv.y, Pv.z)   # hold W: T() of a temporary dangles
        samples.append((f, P, _target_xyz(tgt, bone)))
    _L = cam.LocalTransform(); _s = _L.S(); S = RLPy.RVector3(_s.x, _s.y, _s.z)   # copy: reused across later transform calls
    for f, P, T in samples:
        _key_transform(ctrl, _t(f), RLPy.RTransform(S, _look_quaternion(P, T, roll), RLPy.RVector3(*P)))
    mid = frames[len(frames) // 2]
    RLPy.RGlobal.SetTime(_t(mid + 1)); QtWidgets.QApplication.processEvents()
    RLPy.RGlobal.SetTime(_t(mid)); QtWidgets.QApplication.processEvents()
    # CLAUDE-NOTE (2026-10-07, measured): `obj.WorldTransform().T()` points INTO a temporary RTransform that SWIG frees at
    # the end of the statement; the next WorldTransform() call reused the memory, so a saved camera position silently
    # became the head position (aim error read 90 deg, distance 0). Keep the RTransform alive and copy to floats.
    W = cam.WorldTransform(); Pv = W.T(); P = (Pv.x, Pv.y, Pv.z); fwd = _q_forward(W.R()); T = _target_xyz(tgt, bone)
    d = (T[0] - P[0], T[1] - P[1], T[2] - P[2]); dn = math.sqrt(sum(v * v for v in d)) or 1.0
    err = round(math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(fwd, d)) / dn)))), 2)
    RLPy.RGlobal.SetTime(now)
    return {"ok": err < 2.0, "camera": cam.GetName(), "target": tgt.GetName(), "bone": bone, "start_frame": start,
            "end_frame": end, "every": every, "keys_written": len(frames),
            "transform_keys": ctrl.GetKeyCount() if hasattr(ctrl, "GetKeyCount") else None, "aim_error_deg": {str(mid): err}}


def register(registry):
    def reg(name, fn, desc, props, req, main_thread=True):
        registry[name] = {"handler": fn, "main_thread": main_thread, "description": desc,
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
    from tools import dialog_watch
    reg("list_dialogs", dialog_watch.list_dialogs, "List visible iClone popup dialogs (title, text, buttons) — check this when a call hangs or after launch.", {}, [])
    reg("dismiss_dialog", dialog_watch.dismiss_dialog, "Press a button (default OK) on a visible iClone dialog whose title/text contains `match`. Read list_dialogs first; never dismiss save/discard prompts blindly.",
        {"match": {"type": "string"}, "button": {"type": "string"}}, ["match"])
    reg("build_shot_list", build_shot_list, "Multi-shot previz: per shot a named camera (created via menu if missing), start/end framing keys (position+target, cm), lens, and a camera-switch key at the shot start so playback/render cuts like an edit. Times in seconds.",
        {"shots": {"type": "array", "items": {"type": "object"}}, "clear_switch_keys": {"type": "boolean"}}, ["shots"])
    reg("set_render_output", set_render_output, "Set the Render panel output fps (e.g. 24), width, height; returns the read-back values.",
        {"fps": {"type": "integer"}, "width": {"type": "integer"}, "height": {"type": "integer"}}, [])
    reg("place_object", place_object, "Block an avatar/prop so it HOLDS: writes the transform at frame 0 (default) and clears other transform keys (iClone auto-keys every change at the current frame). Use instead of set_transform for blocking.",
        {"name": {"type": "string"}, "position": {"type": "object"}, "rotation_degrees": {"type": "object"}, "frame": {"type": "integer"}, "clear_keys": {"type": "boolean"}}, ["name"])
    reg("python_exec", python_exec, "Run Python inside iClone 8 (RLPy imported; persistent namespace). Set _result to return a value.",
        {"code": {"type": "string"}}, ["code"])
    reg("render_snapshot", render_snapshot, "Render ONE still through the current camera (RenderImage) at an optional frame; verifies the file exists. Never pops the equal-time modal.",
        {"output_path": {"type": "string"}, "frame": {"type": "integer"}}, ["output_path"])
    reg("render_control_pass", render_control_pass, "Render an OpenPose / Depth / Normal / Canny / beauty image sequence for a frame range (end > start enforced; render size = project settings; project fps = iClone's, default 60). Verifies files were written.",
        {"pass": {"type": "string", "enum": list(_PASSES)}, "start_frame": {"type": "integer"}, "end_frame": {"type": "integer"},
         "output_path": {"type": "string", "description": "folder or file path prefix"}, "bFace": {"type": "boolean"},
         "bHand": {"type": "boolean"}, "bWholeHand": {"type": "boolean"}, "bWholeFace": {"type": "boolean"},
         "pose_format": {"type": "string", "description": "default COCO (other values rendered blank)"}, "gizmo_scale": {"type": "number"},
         "depth_raw_png": {"type": "boolean", "description": "use iClone 8-bit PNG depth (low precision) instead of EXR->equalized PNG"}, "depth_enhanced": {"type": "boolean"}, "allow_crash_risk": {"type": "boolean"}, "normalize": {"type": "boolean", "description": "depth: stretch foreground range (default true)"}, "camera": {"type": "string"},
         "canny_low": {"type": "integer"}, "canny_high": {"type": "integer"}},
        ["pass", "start_frame", "end_frame", "output_path"])
    reg("rename_object", rename_object, "Rename a scene avatar/prop/object.",
        {"name": {"type": "string"}, "new_name": {"type": "string"}}, ["name", "new_name"])
    reg("find_content", find_content, "Search the local Reallusion content library (default F:\\iCLONE) by path words; kind = motion|avatar|prop|scene|project|accessory|template|path. First call builds a cached index (rebuild=true after adding kinds).",
        {"query": {"type": "string"}, "kind": {"type": "string"}, "limit": {"type": "integer"}, "rebuild": {"type": "boolean"}}, [])
    reg("load_motion_verified", load_motion_verified, "Load a motion file onto an avatar at a frame and verify it applied (bone displacement over probe_frames).",
        {"avatar": {"type": "string"}, "path": {"type": "string"}, "frame": {"type": "integer"}, "probe_frames": {"type": "integer"}},
        ["avatar", "path"])
    reg("set_look_at", set_look_at, "Make an avatar LOOK AT a prop/camera (object mode) or another avatar's bone (bone mode, default CC_Base_Head, with transition_frames + head/body weights), keyed at frame; release=true (or no target) releases. Readback = head-bone rotation delta (head_moved).",
        {"avatar": {"type": "string"}, "target": {"type": "string"}, "bone": {"type": "string", "description": "bone on an avatar target (default CC_Base_Head)"},
         "frame": {"type": "integer"}, "transition_frames": {"type": "integer", "description": "bone mode only; ramps in BEFORE the key (default 30)"},
         "head_weight": {"type": "number"}, "body_weight": {"type": "number"}, "release": {"type": "boolean"}}, ["avatar"])
    reg("load_project", load_project, "Open an .iProject in-session (no relaunch, ~2 s). Saves the currently tracked project first unless save_current=false (iClone discards unsaved work without asking). The loaded file becomes the tracked project for checkpoints. Returns the scene object lists.",
        {"path": {"type": "string"}, "save_current": {"type": "boolean"}}, ["path"])
    reg("new_project", new_project, "Start an empty project in-session (File > New Project). Saves the tracked project first unless save_current=false, then clears the tracked path so no checkpoint can overwrite the old project with the empty scene.",
        {"save_current": {"type": "boolean"}}, [])
    reg("set_timeline_range", set_timeline_range, "Set the project length, play range (start/end) and/or preview range; unit = frames (default) or seconds. Reads every value back (frames_now) and reports mismatches. Setting project_length clamps end/preview_end down to it but GROWING it leaves end where it was (pass end too); shrinking does not delete keys.",
        {"project_length": {"type": "number"}, "start": {"type": "number"}, "end": {"type": "number"}, "preview_start": {"type": "number"},
         "preview_end": {"type": "number"}, "unit": {"type": "string", "enum": ["frames", "seconds"]}}, [])
    reg("edit_clip", edit_clip, "Clip surgery on an avatar's motion track: op=break (split at frame), merge (clip + next), mirror (clip; NOTE mirrors in world X so an off-centre actor moves to the other side), delete (clip). Returns clip rows before/after; mirror returns hip/hand positions at probe_frame as proof.",
        {"avatar": {"type": "string"}, "op": {"type": "string", "enum": ["break", "merge", "mirror", "delete"]}, "frame": {"type": "integer"},
         "clip": {"type": "integer", "description": "clip index from get_animation_clips (default 0)"}, "probe_frame": {"type": "integer"}}, ["avatar", "op"])
    reg("load_audio", load_audio, "Put an audio file (wav/mp3) on an AVATAR or PROP's sound track at frame (cameras crash iClone and are refused), with loop_count and fade frames. verify=true (default) renders a 1 s window before/after and reports audio_changed as proof (the API's return value is not a success flag).",
        {"object": {"type": "string"}, "path": {"type": "string"}, "frame": {"type": "integer"}, "loop_count": {"type": "integer"},
         "fade_in_frames": {"type": "integer"}, "fade_out_frames": {"type": "integer"}, "verify": {"type": "boolean"}}, ["object", "path"])
    reg("render_audio", render_audio, "Render the mixed scene audio for a frame range to a wav file and return seconds/peak/nonzero samples (silence check).",
        {"start_frame": {"type": "integer"}, "end_frame": {"type": "integer"}, "output_path": {"type": "string"}}, ["start_frame", "end_frame", "output_path"])
    reg("set_project_fps", set_project_fps, "Set the PROJECT frame rate (12/24/25/30/60/120) via the Project panel (no RLPy setter exists); read back through RLPy. Project length keeps its seconds (frames rescale). Render-panel fps is separate: set_render_output.",
        {"fps": {"type": "integer"}}, ["fps"])
    reg("walk_to", walk_to, "BLOCKING MOVE: avatar walks in a straight line from `from` (default: its position at start_frame) to `to` (cm), facing the travel direction, at speed_cm_s (default 120) or duration_s. Uses a ROOT-MOTION walk clip (default iClone 7 Walk.iMotion; override with motion=path), calibrates it on the avatar, chains as many copies as the distance needs and trims the last to arrive on end_frame, then holds there. replace_clips (default true) wipes the motion track first. Proof: hip xy error at the end frame.",
        {"avatar": {"type": "string"}, "to": {"type": "object"}, "from": {"type": "object"}, "start_frame": {"type": "integer"},
         "speed_cm_s": {"type": "number"}, "duration_s": {"type": "number"}, "motion": {"type": "string"}, "replace_clips": {"type": "boolean"},
         "idle_after": {"type": "boolean", "description": "park the avatar in an in-place idle from arrival to project end (default true)"},
         "idle_motion": {"type": "string"}}, ["avatar", "to"])
    reg("convert_external_motion", convert_external_motion, "Convert a Mixamo/Rokoko/Xsens/... FBX or BVH motion to an iClone .rlMotion via iClone's own 'Convert External Motion' (auto-detected Motion Profile; override with profile=). Returns the produced file(s) in motion_folder (default: iClone's External Motion folder). Then load with load_motion_verified / motion_track.",
        {"path": {"type": "string"}, "profile": {"type": "string"}, "motion_folder": {"type": "string"}, "force_fps": {"type": "integer"},
         "keep_root_motion": {"type": "boolean"}, "timeout_s": {"type": "number"}}, ["path"], main_thread=False)
    reg("path_position_key", path_position_key, "Key an object's position along its path at frame, in PERCENT (0 start, 100 end, 200 = twice round); path= picks the path first. Uses the Modify panel field because RLPy's PathPosition setter never creates a key (upstream set_path_position is a no-op). Reads the key back and returns the world position at that frame.",
        {"object": {"type": "string"}, "percent": {"type": "number"}, "frame": {"type": "integer"}, "path": {"type": "string"}}, ["object", "percent"])
    reg("camera_cuts", camera_cuts, "Edit the camera Switcher track (multi-camera cuts): cuts=[{frame, camera}], replace=true clears old cuts. Turns the toolbar camera list to 'Switch' (switch_mode, default true) so playback and renders follow the cuts; reads the cuts back and checks the live camera mid-shot.",
        {"cuts": {"type": "array", "items": {"type": "object"}}, "replace": {"type": "boolean"}, "switch_mode": {"type": "boolean"}}, ["cuts"])
    reg("track_target", track_target, "Camera (or spotlight) FOLLOWS a moving target: bakes look-at rotation keys every `every` frames (default 2) from start_frame to end_frame, keeping the camera's own position; avatar targets default to the head bone (bone=). Proof: aim error in degrees at the middle sample.",
        {"camera": {"type": "string"}, "target": {"type": "string"}, "bone": {"type": "string"}, "start_frame": {"type": "integer"},
         "end_frame": {"type": "integer"}, "every": {"type": "integer"}, "roll_degrees": {"type": "number"}}, ["camera", "target", "end_frame"])
