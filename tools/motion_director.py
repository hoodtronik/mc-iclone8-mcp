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


def _clips(sk):
    return [(sk.GetClip(i).ClipTimeToSceneTime(RLPy.RTime.FromValue(0)).ToInt(), sk.GetClip(i).GetClipLength().ToInt())
            for i in range(sk.GetClipCount())]


def _prepare_walker(w):
    """Main thread: iMD on the avatar, Auto On Path mode, path assigned by a viewport pick. Returns prep info."""
    from PySide2 import QtWidgets
    av = _avatar(w["avatar"])
    path = RLPy.RScene.FindObject(RLPy.EObjectType_Path, w["path"])
    if path is None:
        raise ValueError(f"no path named {w['path']!r} (create one with draw_path)")
    imd = _apply_imd(av, w.get("imd"))
    length, pts = _path_length(path)
    if w.get("place_at_start", True) and len(pts) > 1:
        # CLAUDE-NOTE (2026-10-16, plaza test): MD walks the avatar from wherever it stands TO the path first; freshly
        # loaded avatars all stand at the origin, so five walkers overlapped for 1.5-7 s. Start them on their path,
        # facing along it (CC front = -Y: heading = atan2(dx, -dy)).
        from tools.icmcp_extra import place_object
        (x0, y0), (x1, y1) = pts[0][:2], pts[min(3, len(pts) - 1)][:2]
        place_object({"name": av.GetName(), "frame": 0, "position": {"x": x0, "y": y0, "z": 0.0},
                      "rotation_degrees": {"x": 0, "y": 0, "z": math.degrees(math.atan2(x1 - x0, -(y1 - y0)))}})
    _select_only(av)
    _set_start_mode("Record Selected")
    mode = _ensure_auto_on_path_mode()
    # pick: the dialog's avatar ids are not RLPy ids -> try each and verify through the engine
    vp, px = world_to_viewport([p for p in pts[len(pts) // 4: 3 * len(pts) // 4 + 1]])
    inside = [p for p in px if p and 5 < p[0] < vp.width() - 5 and 5 < p[1] < vp.height() - 5]
    if not inside:
        raise RuntimeError(f"path {w['path']} is not visible in the current camera; aim a camera at it (aim_camera)")
    pick_px = inside[len(inside) // 2]
    _pick_path(av, path.GetName(), vp, pick_px)
    return {"avatar": av.GetName(), "path": path.GetName(), "imd": imd, "path_length_cm": round(length, 1),
            "path_pts": [(p[0], p[1]) for p in pts], "pick": (vp, pick_px), "mode": mode,
            "before": _clips(av.GetSkeletonComponent())}


_DLG_IDS = {}       # avatar name -> MD dialog avatar id, learned by observation


def _md_avatars():
    return [a for a in RLPy.RScene.GetAvatars() if _md().GetMainMDName(_handle(a))]


def _pick_path(av, path_name, vp, pick_px):
    """Assign path_name as av's auto path through the MD dialog (setAvatarsPicked + pickAutoPathObject + viewport pick).
    # CLAUDE-NOTE (2026-10-16, plaza test): the dialog's avatar ids are not RLPy ids. Trying ids blindly assigns the
    # path to OTHER avatars too (5 walkers all ended on the last walker's path P5). Order: a learned id; else the id at
    # the avatar's index among MD-enabled avatars (ids rise in load order, matching scene order); else trial, learning
    # each id's owner from which avatar's path changed."""
    from PySide2 import QtWidgets
    if _auto_path_name(av) == path_name:
        return
    ids = _js_call("dlg.getAvatarIds()") or []
    mds = _md_avatars()
    order = []
    if av.GetName() in _DLG_IDS:
        order.append(_DLG_IDS[av.GetName()])
    names = [a.GetName() for a in mds]
    if len(names) == len(ids) and av.GetName() in names:
        order.append(ids[names.index(av.GetName())])
    order += [i for i in ids if i not in order and i not in _DLG_IDS.values()]
    for aid in order:
        before = {a.GetName(): _auto_path_name(a) for a in mds}
        _select_only(av)
        _js_call("dlg.setAvatarsPicked(['%s'])" % aid)
        _js_call("dlg.pickAutoPathObject(['%s'])" % aid)
        for _ in range(10):
            QtWidgets.QApplication.processEvents(); time.sleep(0.03)
        _post_viewport_clicks(vp, [pick_px], finish=False)
        for _ in range(15):
            QtWidgets.QApplication.processEvents(); time.sleep(0.03)
        changed = [n for n in before if _auto_path_name(_avatar(n)) != before[n]]
        if len(changed) == 1:
            _DLG_IDS[changed[0]] = aid
        if _auto_path_name(av) == path_name:
            _DLG_IDS[av.GetName()] = aid
            return
    raise RuntimeError(f"could not assign {path_name} as {av.GetName()}'s auto path (tried dialog ids {order})")


def _verify_walker(prep):
    from tools import scene_qa as Q
    av = _avatar(prep["avatar"])
    fps = RLPy.RGlobal.GetFps()
    new = [c for c in _clips(av.GetSkeletonComponent()) if c not in prep["before"]]
    if not new:
        return {"ok": False, "avatar": av.GetName(), "error": "no new clip after the MD run"}
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


def _record_take(walkers, seconds, start_frame):
    """Prepare every walker, select them all, record ONE MD take (Record Selected), verify each."""
    from dispatch import run
    preps = [run(lambda w=w: _prepare_walker(w)) for w in walkers]

    def recheck():
        # a later pick can still land on an earlier walker; re-pick until every assignment holds (ids learned by now)
        for _ in range(3):
            wrong = [p for p in preps if _auto_path_name(_avatar(p["avatar"])) != p["path"]]
            if not wrong:
                return {}
            for p in wrong:
                _pick_path(_avatar(p["avatar"]), p["path"], *p["pick"])
        return {p["avatar"]: _auto_path_name(_avatar(p["avatar"])) for p in preps
                if _auto_path_name(_avatar(p["avatar"])) != p["path"]}
    bad = run(recheck)
    if bad:
        raise RuntimeError(f"auto path assignments did not hold: {bad}")
    dur = float(seconds) if seconds else max(p["path_length_cm"] for p in preps) / 100.0 + 3.0

    def start():
        from PySide2 import QtWidgets
        # CLAUDE-NOTE (2026-10-16, measured): RScene.SelectObject REPLACES the selection (3 calls -> 1 selected; only
        # the last walker recorded). SelectObjects(list) selects them all.
        RLPy.RScene.ClearSelectObjects()
        RLPy.RScene.SelectObjects([_avatar(p["avatar"]) for p in preps])
        QtWidgets.QApplication.processEvents()
        RLPy.RGlobal.SetTime(RLPy.RGlobal.GetFps().IndexedFrameTime(start_frame))
        _, acts = _toolbar_actions()
        acts["qtStartMotionMatchingToolBarAction"].trigger()
        return RLPy.RGlobal.GetMotionDirector().IsRunning()
    if not run(start):
        raise RuntimeError("Motion Director did not start (check iclone_eyes.py popups for a dialog)")
    time.sleep(dur)                       # HTTP thread waits; iClone's main thread runs the MD simulation

    def stop():
        _, acts = _toolbar_actions()
        acts["qtStopMotionMatchingToolBarAction"].trigger()
        return True
    run(stop)
    time.sleep(3.0)                       # the recorded clips are committed after stop
    return [run(lambda p=p: _verify_walker(p)) for p in preps], dur


def md_walk_path(args):
    res, _ = _record_take([{"avatar": args["avatar"], "path": args["path"], "imd": args.get("imd")}],
                          args.get("seconds"), int(args.get("start_frame", 0)))
    out = dict(res[0])
    out.pop("ok", None)
    return dict(out, ok=res[0].get("ok", False))


def md_walk_paths(args):
    """Several walkers, each on its own path. Walkers sharing a start_frame record in ONE take (all selected)."""
    # CLAUDE-NOTE (2026-10-16): MD simulates in real time, so one take for N walkers costs the same wall time as one
    # walker; separate takes only for different start frames.
    groups = {}
    for w in args["walkers"]:
        groups.setdefault(int(w.get("start_frame", args.get("start_frame", 0))), []).append(w)
    results, takes = [], []
    for sf in sorted(groups):
        res, dur = _record_take(groups[sf], args.get("seconds"), sf)
        results += res
        takes.append({"start_frame": sf, "walkers": [w["avatar"] for w in groups[sf]], "seconds": round(dur, 1)})
    return {"ok": all(r.get("ok") for r in results), "takes": takes, "walkers": results}


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
    registry["md_walk_paths"] = {
        "handler": md_walk_paths, "main_thread": False,
        "description": "Several Motion Director walkers at once (a moving crowd on paths): walkers=[{avatar, path, imd?, "
                       "start_frame?}]. Walkers with the same start_frame record in ONE real-time take (all selected, "
                       "'Record Selected'), so N walkers cost one take. Every path must be visible in the current camera "
                       "(viewport pick). Returns per-walker gait metrics + path deviation.",
        "inputSchema": {"type": "object", "properties": {
            "walkers": {"type": "array", "items": {"type": "object"}}, "seconds": {"type": "number"},
            "start_frame": {"type": "integer"}}, "required": ["walkers"]}}
