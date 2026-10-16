"""Motion Director (MD): natural, motion-matched locomotion recorded to the timeline.
Tools: md_walk_path (an avatar walks/idles along a path under MD's Auto On Path mode; the run is recorded as a clip).
# CLAUDE-NOTE (2026-10-16, all measured on iClone 8.75 with the default Casual_Walk iMDs):
#  - MD needs iMD behaviour data on the avatar: RFileIO.LoadFile(<.iMD>) with the avatar selected (Main iMD then reads
#    via RLPy2.MotionDirector.GetMainMDName). Default packs install under Reallusion Templates\\Animation\\Motion Director
#    (needs the user's Reallusion login; RLPy2.MotionDirector.Start(True) triggers the install the first time).
#  - The MD Controls dock (IC::CMotionMatchingDlg) exposes Q_INVOKABLEs; PySide2 has no Q_RETURN_ARG, so they are called
#    through a QJSEngine wrapping the dock (getAvatarIds, pickAutoPathObject, getMatchingManagerSetting, getRecords...).
#  - setMatchingManagerSetting* does NOT set AutoPathName; the path is assigned only by a PICK: setAvatarsPicked([id]) +
#    pickAutoPathObject([id]) + a click on the path in the viewport (posted to the viewport window, no real cursor).
#  - RLPy2.MotionDirector.ActivateAutoPathMode returns RL_OK but does not switch mode; the QML 'Auto On Path' button does.
#  - RIMotionDirectorManager.BeginCommand(bRecord) only produces MACROS; toolbar start mode 'Record Selected' + the
#    toolbar Start/Stop actions produce a timeline CLIP for the selected avatar.
#  - Result on a 8.5 m curved path: slide_ratio 0.0, stride 76 cm, 0 pops, follows the curve within ~40 cm.
#  - MD simulates in real time on iClone's main thread, so this tool runs on the HTTP thread and only hops onto the main
#    thread (dispatch.run) for short steps; never block the main thread while MD plays.
"""
import math
import os
import time

import RLPy

from tools.icmcp_extra import _avatar, _main_window, _path_length, _post_viewport_clicks, world_to_viewport

MD_ROOT = os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Documents", "Reallusion", "Reallusion Templates",
                       "Animation", "Motion Director")
DEFAULT_IMD = {"male": os.path.join(MD_ROOT, "Neutral", "Casual_Walk_M_N.iMD"),
               "female": os.path.join(MD_ROOT, "Female", "Casual_Walk_F.iMD")}


def _dock():
    from PySide2 import QtWidgets
    ds = [d for d in _main_window().findChildren(QtWidgets.QDockWidget) if d.windowTitle().replace(" ", "") == "MDControls"]
    if not ds:
        raise RuntimeError("MD Controls dock not found (Window > MD Control Center)")
    return ds[0]


def _js_call(expr):
    """Evaluate JS against the MD Controls dialog (bound as `dlg`); returns the JSON-decoded value."""
    import json
    from PySide2 import QtQml
    eng = QtQml.QJSEngine()
    eng.globalObject().setProperty("dlg", eng.newQObject(_dock()))
    v = eng.evaluate("JSON.stringify(" + expr + ")")
    if v.isError():
        raise RuntimeError("MD dialog call failed: " + v.toString())
    s = v.toString()
    return json.loads(s) if s and s != "undefined" else None


def _handle(obj):
    import RLPy2
    return RLPy2.System.GetInterface().ToHandle(obj.GetID())


def _md():
    import RLPy2
    return RLPy2.MotionDirector.GetInterface()


def _auto_path_name(av):
    import RLPy2
    return RLPy2.Query.GetInterface().HandleName(_md().GetAutoPathObject(_handle(av)))


def _select_only(obj):
    from PySide2 import QtWidgets
    RLPy.RScene.ClearSelectObjects(); RLPy.RScene.SelectObject(obj); QtWidgets.QApplication.processEvents()


def _toolbar_actions():
    from PySide2 import QtWidgets
    tb = _main_window().findChild(QtWidgets.QToolBar, "qtMotionDirectorToolBar")
    return tb, {a.objectName(): a for a in tb.actions()}


def _set_start_mode(text="Record Selected"):
    from PySide2 import QtWidgets
    c = _main_window().findChild(QtWidgets.QComboBox, "qtStartModeToolBarAction")
    i = c.findText(text)
    if i < 0:
        raise RuntimeError(f"MD start mode {text!r} not offered: {[c.itemText(k) for k in range(c.count())]}")
    c.setCurrentIndex(i); c.activated.emit(i)
    return c.currentText()


def _apply_imd(av, imd):
    if _md().GetMainMDName(_handle(av)):
        return _md().GetMainMDName(_handle(av))
    path = DEFAULT_IMD.get(str(imd or "male").lower(), imd)
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"iMD not found: {path!r}. Default packs: {DEFAULT_IMD} (install via the user's "
                                f"Reallusion login; see the iclone-mcp skill, rlpy2.md > Motion Director)")
    _select_only(av)
    RLPy.RFileIO.LoadFile(path)
    name = _md().GetMainMDName(_handle(av))
    if not name:
        raise RuntimeError(f"loading {os.path.basename(path)} did not give {av.GetName()} a Main iMD")
    return name


def _ensure_auto_on_path_mode():
    import RLPy2
    from tools import qml_ui
    d = _dock()
    if not d.isVisible():
        d.show()
    from PySide2 import QtWidgets
    for _ in range(10):
        QtWidgets.QApplication.processEvents(); time.sleep(0.02)
    w = qml_ui.window_with_text("Start Record by Selected")
    if w is None:
        raise RuntimeError("MD Controls QML panel not found")
    sec = qml_ui.find(w, text="Control Settings", cls_prefix="RLSectionButton")
    btn = qml_ui.find(w, tooltip="Auto On Path")
    if btn is None and sec is not None:            # the mode buttons live in the collapsed Control Settings section
        qml_ui.click(sec)
        w = qml_ui.window_with_text("Start Record by Selected")
        btn = qml_ui.find(w, tooltip="Auto On Path")
    if btn is None:
        raise RuntimeError("'Auto On Path' button not found in MD Controls")
    if str(btn.property("checked")) != "True":
        qml_ui.click(btn)
    return str(RLPy2.EMotionMatchingControlMode.AutoPathMode)


def md_walk_path(args):
    from dispatch import run
    seconds = args.get("seconds")
    start_frame = int(args.get("start_frame", 0))

    def prepare():
        from PySide2 import QtWidgets
        av = _avatar(args["avatar"])
        path = RLPy.RScene.FindObject(RLPy.EObjectType_Path, args["path"])
        if path is None:
            raise ValueError(f"no path named {args['path']!r} (create one with draw_path)")
        imd = _apply_imd(av, args.get("imd"))
        length, pts = _path_length(path)
        _select_only(av)
        _set_start_mode("Record Selected")
        mode = _ensure_auto_on_path_mode()
        # pick: the dialog's avatar ids are not RLPy ids -> try each and verify through the engine
        vp, px = world_to_viewport([p for p in pts[len(pts) // 4: 3 * len(pts) // 4 + 1]])
        inside = [p for p in px if p and 5 < p[0] < vp.width() - 5 and 5 < p[1] < vp.height() - 5]
        if not inside:
            raise RuntimeError("the path is not visible in the current camera; aim a camera at it (aim_camera) and retry")
        pick_px = inside[len(inside) // 2]
        picked = _auto_path_name(av) == path.GetName()
        tried = []
        for aid in (_js_call("dlg.getAvatarIds()") or []):
            if picked:
                break
            _select_only(av)
            _js_call("dlg.setAvatarsPicked(['%s'])" % aid)
            _js_call("dlg.pickAutoPathObject(['%s'])" % aid)
            for _ in range(10):
                QtWidgets.QApplication.processEvents(); time.sleep(0.03)
            _post_viewport_clicks(vp, [pick_px], finish=False)
            for _ in range(15):
                QtWidgets.QApplication.processEvents(); time.sleep(0.03)
            tried.append(aid)
            picked = _auto_path_name(av) == path.GetName()
        if not picked:
            raise RuntimeError(f"could not assign {path.GetName()} as {av.GetName()}'s auto path (tried dialog ids {tried})")
        _select_only(av)
        sk = av.GetSkeletonComponent()
        before = [(sk.GetClip(i).ClipTimeToSceneTime(RLPy.RTime.FromValue(0)).ToInt(), sk.GetClip(i).GetClipLength().ToInt())
                  for i in range(sk.GetClipCount())]
        RLPy.RGlobal.SetTime(RLPy.RGlobal.GetFps().IndexedFrameTime(start_frame))
        return {"imd": imd, "path_length_cm": round(length, 1), "path_pts": [(p[0], p[1]) for p in pts], "mode": mode,
                "before": before}

    prep = run(prepare)
    dur = float(seconds) if seconds else prep["path_length_cm"] / 100.0 + 3.0

    def start():
        _, acts = _toolbar_actions()
        acts["qtStartMotionMatchingToolBarAction"].trigger()
        return RLPy.RGlobal.GetMotionDirector().IsRunning()
    if not run(start):
        raise RuntimeError("Motion Director did not start (check list_dialogs / retk window tools for a popup)")
    time.sleep(dur)                       # HTTP thread waits; iClone's main thread runs the MD simulation

    def stop():
        _, acts = _toolbar_actions()
        acts["qtStopMotionMatchingToolBarAction"].trigger()
        return True
    run(stop)
    time.sleep(3.0)                       # the recorded clip is committed after stop

    def verify():
        from tools import scene_qa as Q
        av = _avatar(args["avatar"])
        sk = av.GetSkeletonComponent()
        fps = RLPy.RGlobal.GetFps()
        clips = [(sk.GetClip(i).ClipTimeToSceneTime(RLPy.RTime.FromValue(0)).ToInt(), sk.GetClip(i).GetClipLength().ToInt())
                 for i in range(sk.GetClipCount())]
        new = [c for c in clips if c not in prep["before"]]
        if not new:
            return {"ok": False, "error": "no new clip after the MD run", "clips": clips}
        c0, clen = new[0]
        f0, f1 = fps.GetFrameIndex(RLPy.RTime.FromValue(c0)), fps.GetFrameIndex(RLPy.RTime.FromValue(c0 + clen))
        frames = list(range(f0, f1 + 1))
        data = Q._sample([av], frames)[av.GetName()]
        rep = Q.analyze_avatar(frames, data, fps.ToFloat())
        hips = data["CC_Base_Hip"]
        pts = prep["path_pts"]
        dev = max(min(math.hypot(h[0] - p[0], h[1] - p[1]) for p in pts) for h in hips[::max(1, len(hips) // 60)])
        end_gap = min(math.hypot(hips[-1][0] - p[0], hips[-1][1] - p[1]) for p in pts[-3:])
        return {"ok": True, "avatar": av.GetName(), "imd": prep["imd"], "path_length_cm": prep["path_length_cm"],
                "recorded_s": round(clen / 6000.0, 2), "clip_frames": [f0, f1],
                "slide_ratio": rep.get("slide_ratio"), "hip_speed_cm_s": rep.get("hip_speed_cm_s"),
                "pop_count": rep.get("pop_count"), "max_path_deviation_cm": round(dev, 1),
                "end_distance_to_path_end_cm": round(end_gap, 1)}
    return run(verify)


def register(registry):
    registry["md_walk_path"] = {
        "handler": md_walk_path, "main_thread": False,
        "description": "NATURAL LOCOMOTION via Motion Director: the avatar walks (with motion-matched starts, turns, idles) "
                       "along an existing path (draw_path) under MD 'Auto On Path', recorded as a timeline clip from "
                       "start_frame. Applies a default iMD if the avatar has none (imd: 'male'|'female'|path). The path "
                       "must be visible in the current camera (the path is assigned by a viewport pick). Returns gait "
                       "metrics + path deviation. seconds defaults to path length / 1 m/s + 3 s.",
        "inputSchema": {"type": "object", "properties": {
            "avatar": {"type": "string"}, "path": {"type": "string"}, "seconds": {"type": "number"},
            "start_frame": {"type": "integer"}, "imd": {"type": "string"}}, "required": ["avatar", "path"]}}
