"""Edit an existing path: new shape (points), reverse direction, open/close the loop.
Tool: edit_path.
# CLAUDE-NOTE (2026-10-18, measured): RIPath has no point API and no .iPath template ships with the content, so a new
# SHAPE is a redraw: draw_path through the new points (clicks, ~1-3 cm), the old path removed, the new one takes its
# name, and listed followers are re-attached with FollowPath. Dragging a control point in Modify > Edit Point mode moved
# it along the wrong axis (a top-view drag sent the middle point 1.48 m UP) and 'Add Points' + a click appended
# nothing - neither is used. 'Reverse Direction' (qtInvertPathPushButton) swapped start/end exactly (measured).
"""
import time

try:
    import RLPy
except ImportError:          # offline tests import nothing here, kept for symmetry
    RLPy = None


def _modify_dock():
    from PySide2 import QtWidgets
    return next(w for w in QtWidgets.QApplication.instance().allWidgets()
                if isinstance(w, QtWidgets.QDockWidget) and w.windowTitle() == "Modify")


def _pump(n=10):
    from PySide2 import QtWidgets
    for _ in range(n):
        QtWidgets.QApplication.processEvents(); time.sleep(0.02)


def _path_keys(obj, fps):
    """[(frame, value 0..1, transition)] of an object's PathPosition keys."""
    c = obj.GetControl("PathPosition")
    out = []
    if c is None:
        return out
    for i in range(c.GetKeyCount()):
        t = RLPy.RTime()
        c.GetKeyTimeAt(i, t)
        v = c.GetValue(t, 0.0)
        v = v[1] if isinstance(v, (list, tuple)) else v
        tt = c.GetKeyTransitionType(t) if hasattr(c, "GetKeyTransitionType") else None
        out.append((fps.GetFrameIndex(t), float(v), tt))
    return out


def edit_path(args):
    from PySide2 import QtWidgets
    from tools.icmcp_extra import _path_length, draw_path
    name = args["name"]
    path = RLPy.RScene.FindObject(RLPy.EObjectType_Path, name)
    if path is None:
        raise ValueError(f"no path named {name!r}")
    out = {"name": name}
    if args.get("points"):
        fps = RLPy.RGlobal.GetFps()
        followers = []
        for fol in args.get("followers", []):
            obj = next((o for o in list(RLPy.RScene.GetProps()) + list(RLPy.RScene.GetAvatars())
                        + list(RLPy.RScene.GetCameras()) if o.GetName() == fol), None)
            if obj is None:
                raise ValueError(f"follower {fol!r} not found")
            followers.append((obj, _path_keys(obj, fps)))
        tmp = "_reshape_" + name
        r = draw_path({"name": tmp, "points": args["points"], "hide_objects": args.get("hide_objects", True)})
        if not r.get("ok"):
            raise RuntimeError(f"redraw failed: {r}")
        new = RLPy.RScene.FindObject(RLPy.EObjectType_Path, tmp)
        RLPy.RScene.RemoveObject(path)
        new.SetName(name)
        path = new
        out["redrawn"] = {k: r[k] for k in ("start_error_cm", "end_error_cm", "height_deviation_cm")}
        for obj, keys in followers:
            # CLAUDE-NOTE (2026-10-18, measured): FollowPath onto the new path drops the PathPosition keys (the cart sat
            # at the start); they are read first (RFloatControl, value 0..1 + transition) and re-keyed. Same timing on a
            # longer path = a faster move.
            from tools.icmcp_extra import path_position_key
            first = keys[0][0] if keys else int(args.get("follow_frame", 0))
            st = obj.FollowPath(path, fps.IndexedFrameTime(first))
            for f, v, tt in keys:
                path_position_key({"object": obj.GetName(), "percent": v * 100.0, "frame": f})
            pc = obj.GetControl("PathPosition")
            for f, v, tt in keys:
                if tt is not None and pc is not None:
                    pc.SetKeyTransition(fps.IndexedFrameTime(f), tt, 50.0)
            out.setdefault("followers", []).append({"name": obj.GetName(), "keys": len(keys),
                                                    "ok": not (hasattr(st, "IsError") and st.IsError())})
    if args.get("reverse") or args.get("closed") is not None:
        RLPy.RScene.SelectObject(path); _pump(5)
        d = _modify_dock()
        eb = d.findChild(QtWidgets.QToolButton, "qtEditPathButton")
        if eb is not None and eb.isChecked():
            eb.click(); _pump(5)
        if args.get("reverse"):
            d.findChild(QtWidgets.QPushButton, "qtInvertPathPushButton").click(); _pump()
            out["reversed"] = True
        if args.get("closed") is not None:
            cb = d.findChild(QtWidgets.QCheckBox, "qtClosePathCheckBox")
            if cb.isChecked() != bool(args["closed"]):
                cb.click(); _pump()
            out["closed"] = cb.isChecked()
    length, pts = _path_length(path, 40)
    out.update({"ok": True, "length_cm": round(length, 1), "start": [round(v, 1) for v in pts[0]],
                "end": [round(v, 1) for v in pts[-1]], "mid": [round(v, 1) for v in pts[len(pts) // 2]]})
    return out


def _md_tab(path):
    """Select the path and show the Modify panel's MD tab (Walkway Basic Settings / Walkway Behaviors)."""
    from PySide2 import QtWidgets
    RLPy.RScene.ClearSelectObjects(); _pump(3)
    RLPy.RScene.SelectObject(path); _pump(5)
    d = _modify_dock()
    bars = [t for t in d.findChildren(QtWidgets.QTabBar) if t.isVisible() and t.count() == 2]
    if not bars:
        raise RuntimeError("the path's Modify tabs are not visible (is the Modify panel open?)")
    bars[0].setCurrentIndex(1); _pump()
    return d


def set_walkway_width(args):
    """A path with a WIDTH is a walkway: Crowd Generator spawns across it and Motion Director spreads walkers over it."""
    # CLAUDE-NOTE (2026-10-18, measured): Modify > (path) MD tab > Walkway Basic Settings > Width (qtWidthComboSpinBox,
    # 0-1000 cm) - set 300, re-selected, read 300. 'Initial Bearing (Ratio)' slider qtStartDirectionSlider (0 = all
    # start at the Origin end, 100 = Destination, 50 default) sets which way walkers head.
    from PySide2 import QtWidgets
    path = RLPy.RScene.FindObject(RLPy.EObjectType_Path, args["name"])
    if path is None:
        raise ValueError(f"no path named {args['name']!r}")
    d = _md_tab(path)
    out = {"name": args["name"]}
    if args.get("width_cm") is not None:
        sp = [w for w in d.findChildren(QtWidgets.QWidget, "qtWidthComboSpinBox") if w.isVisible()][0].findChild(QtWidgets.QSpinBox)
        sp.setValue(int(args["width_cm"])); sp.editingFinished.emit(); _pump()
    if args.get("bearing") is not None:
        sl = [w for w in d.findChildren(QtWidgets.QSlider, "qtStartDirectionSlider") if w.isVisible()][0]
        sl.setValue(int(args["bearing"])); sl.sliderReleased.emit(); _pump()
    d = _md_tab(path)                    # re-select and read back
    out["width_cm"] = [w for w in d.findChildren(QtWidgets.QWidget, "qtWidthComboSpinBox") if w.isVisible()][0]         .findChild(QtWidgets.QSpinBox).value()
    out["bearing"] = [w for w in d.findChildren(QtWidgets.QSlider, "qtStartDirectionSlider") if w.isVisible()][0].value()
    out["ok"] = (args.get("width_cm") is None or out["width_cm"] == int(args["width_cm"])) and         (args.get("bearing") is None or out["bearing"] == int(args["bearing"]))
    return out


def register(registry):
    registry["set_walkway_width"] = {
        "handler": set_walkway_width, "main_thread": True,
        "description": "Make a path a WALKWAY: width_cm (0-1000, measured as the reach on EACH side of the line: 250 -> a 5 m band; Crowd Generator spawns across it, Motion Director walkers "
                       "spread over it) and bearing 0-100 (0 = walkers start heading from the origin end, 100 = from the "
                       "destination, 50 = both ways). Reads both back.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "width_cm": {"type": "integer"},
                                                         "bearing": {"type": "integer"}}, "required": ["name"]}}
    registry["edit_path"] = {
        "handler": edit_path, "main_thread": True, "timeout": 300,
        "description": "EDIT A PATH: points [{x,y,z?}] = a new shape (redrawn through iClone's Create Path clicks - every point "
                       "must be visible in the current view camera; the old path is replaced and keeps its name; followers "
                       "[names] are re-attached and their path-position keys copied over - same timing, so a longer path = faster), reverse (swap start/end), "
                       "closed true/false (loop). Returns measured start/mid/end and length.",
        "inputSchema": {"type": "object", "properties": {
            "name": {"type": "string"}, "points": {"type": "array", "items": {"type": "object"}},
            "followers": {"type": "array", "items": {"type": "string"}}, "follow_frame": {"type": "integer"},
            "reverse": {"type": "boolean"}, "closed": {"type": "boolean"}, "hide_objects": {"type": "boolean"}},
            "required": ["name"]}}
