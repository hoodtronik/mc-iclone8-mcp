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


def _ensure_mode(tooltip="Auto On Path"):
    """Check the MD Controls QML mode button `tooltip` ('Auto On Path' | 'Auto In Zone') for the selected avatar."""
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
    btn = qml_ui.find(w, tooltip=tooltip)
    if btn is None and sec is not None:            # the mode buttons live in the collapsed Control Settings section
        qml_ui.click(sec)
        w = qml_ui.window_with_text("Start Record by Selected")
        btn = qml_ui.find(w, tooltip=tooltip)
    if btn is None:
        raise RuntimeError(f"{tooltip!r} button not found in MD Controls")
    if str(btn.property("checked")) != "True":
        qml_ui.click(btn)
    return tooltip


def _dialog_id(name):
    """MD dialog avatar id for an avatar name.
    # CLAUDE-NOTE (2026-10-16, measured): dialog ids are not RLPy ids, and picking with the wrong id assigns the path /
    # zone to ANOTHER avatar (5 plaza walkers all got the last path). setAvatarsPicked([id]) + getCurrentAvatarName()
    # maps ids to names exactly."""
    # CLAUDE-NOTE (2026-10-16, measured): setAvatarsPicked costs ~0.37 s (panel refresh), so an unmapped lookup over 11
    # avatars took 4 s and an 11-person md_crowd spent >15 min in checks. Cache id -> name (ids are stable for an
    # avatar's lifetime); validate against getAvatarIds() and map unknown ids only.
    ids = _js_call("dlg.getAvatarIds()") or []
    for aid, n in list(_ID_NAMES.items()):
        if aid not in ids:
            del _ID_NAMES[aid]
    hit = [aid for aid, n in _ID_NAMES.items() if n == name]
    if hit:
        return hit[0]
    for aid in ids:
        if aid in _ID_NAMES:
            continue
        _js_call("dlg.setAvatarsPicked(['%s'])" % aid)
        _ID_NAMES[aid] = _js_call("dlg.getCurrentAvatarName()")
        if _ID_NAMES[aid] == name:
            return aid
    raise RuntimeError(f"{name} is not in Motion Director's avatar list (no iMD applied?)")


_ID_NAMES = {}      # MD dialog avatar id -> avatar name (see _dialog_id)


def _mgr(name):
    return _js_call("dlg.getMatchingManagerSetting('%s')" % _dialog_id(name)) or {}


def _pick(av, kind, target_name, vp, pick_px, check):
    """Assign a path (kind='Path') or zone (kind='Bound') to av via setAvatarsPicked + pickAuto<kind>Object + a viewport
    click on the target; `check()` confirms it."""
    from PySide2 import QtWidgets
    if check():
        return
    aid = _dialog_id(av.GetName())
    for attempt in range(2):
        _select_only(av)
        _js_call("dlg.setAvatarsPicked(['%s'])" % aid)
        _js_call("dlg.pickAuto%sObject(['%s'])" % (kind, aid))
        for _ in range(10):
            QtWidgets.QApplication.processEvents(); time.sleep(0.03)
        _post_viewport_clicks(vp, [pick_px], finish=False)
        for _ in range(15):
            QtWidgets.QApplication.processEvents(); time.sleep(0.03)
        if check():
            return
    raise RuntimeError(f"could not assign {target_name} to {av.GetName()} (pickAuto{kind}Object, dialog id {aid})")


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
    mode = _ensure_mode("Auto On Path")
    vp, px = world_to_viewport([p for p in pts[len(pts) // 4: 3 * len(pts) // 4 + 1]])
    inside = [p for p in px if p and 5 < p[0] < vp.width() - 5 and 5 < p[1] < vp.height() - 5]
    if not inside:
        raise RuntimeError(f"path {w['path']} is not visible in the current camera; aim a camera at it (aim_camera)")
    pick_px = inside[len(inside) // 2]
    _pick_path(av, path.GetName(), vp, pick_px)
    pname = path.GetName()
    return {"avatar": av.GetName(), "path": pname, "imd": imd, "path_length_cm": round(length, 1),
            "path_pts": [(p[0], p[1]) for p in pts], "mode": mode, "before": _clips(av.GetSkeletonComponent()),
            "assigned": lambda: _auto_path_name(av) == pname, "repick": lambda: _pick_path(av, pname, vp, pick_px)}


def _pick_path(av, path_name, vp, pick_px):
    _pick(av, "Path", path_name, vp, pick_px, lambda: _auto_path_name(av) == path_name)


def _take_clip(av, start_frame):
    """(start, length) ticks of the clip covering start_frame (the recorded take)."""
    t = RLPy.RGlobal.GetFps().IndexedFrameTime(start_frame).ToInt()
    for c0, clen in _clips(av.GetSkeletonComponent()):
        if c0 <= t < c0 + max(clen, 1):
            return c0, clen
    return None


def _verify_walker(prep, data, frames, step):
    from tools import scene_qa as Q
    fps = RLPy.RGlobal.GetFps()
    rep = Q.analyze_avatar(frames, data, fps.ToFloat(), step=step)
    hips = data["CC_Base_Hip"]
    pts = prep["path_pts"]
    dev = max(min(math.hypot(h[0] - p[0], h[1] - p[1]) for p in pts) for h in hips[::max(1, len(hips) // 60)])
    end_gap = min(math.hypot(hips[-1][0] - p[0], hips[-1][1] - p[1]) for p in pts[-3:])
    return {"imd": prep["imd"], "path_length_cm": prep["path_length_cm"],
            "slide_ratio": rep.get("slide_ratio"), "hip_speed_cm_s": rep.get("hip_speed_cm_s"),
            "pop_count": rep.get("pop_count"), "max_path_deviation_cm": round(dev, 1),
            "end_distance_to_path_end_cm": round(end_gap, 1)}


TRACE = []         # (seconds since take start, step) of the last take; read it via python_exec when a take is slow


def _trace(step, t0=[0.0]):
    if step == "begin":
        TRACE.clear(); t0[0] = time.time()
    TRACE.append((round(time.time() - t0[0], 2), step))


def _record_take(walkers, seconds, start_frame, prepare=None, before_start=None, avoidance_radius_cm=50.0,
                 retakes=0, collision_cm=30.0):
    """Prepare every walker, select them all, record ONE MD take (Record Selected), verify each.
    Each prep carries `assigned()` (does its path/zone assignment still hold?) and `repick()`."""
    from dispatch import run
    prepare = prepare or _prepare_walker
    _trace("begin")
    preps = []
    for w in walkers:
        preps.append(run(lambda w=w: prepare(w)))
        _trace("prepared " + w["avatar"])

    def recheck():
        # a later pick can still land on an earlier walker; re-pick until every assignment holds
        for _ in range(3):
            wrong = [p for p in preps if not p["assigned"]()]
            if not wrong:
                return []
            for p in wrong:
                p["repick"]()
        return [p["avatar"] for p in preps if not p["assigned"]()]
    bad = run(recheck)
    _trace("rechecked")
    if avoidance_radius_cm and len(preps) > 1:
        # CLAUDE-NOTE (2026-10-16, plaza QA): at the default CrowdAvoidanceAgentRadius (39 cm) two wanderers passed with
        # hips 3 cm apart; setMatchingManagerSetting([id], {CrowdAvoidanceAgentRadius}) is honoured (read back).
        import json
        run(lambda: _js_call("dlg.setMatchingManagerSetting(%s, %s)" % (
            json.dumps([_dialog_id(p["avatar"]) for p in preps]),
            json.dumps({"CrowdAvoidanceAgentRadius": float(avoidance_radius_cm)}))))
    if bad:
        raise RuntimeError(f"Motion Director assignments did not hold for {bad}")
    dur = float(seconds) if seconds else max(p.get("path_length_cm", 0) for p in preps) / 100.0 + 3.0

    def start():
        from PySide2 import QtWidgets
        # CLAUDE-NOTE (2026-10-16, measured): RScene.SelectObject REPLACES the selection (3 calls -> 1 selected; only
        # the last walker recorded). SelectObjects(list) selects them all.
        if before_start:
            before_start()
        RLPy.RScene.ClearSelectObjects()
        RLPy.RScene.SelectObjects([_avatar(p["avatar"]) for p in preps])
        QtWidgets.QApplication.processEvents()
        RLPy.RGlobal.SetTime(RLPy.RGlobal.GetFps().IndexedFrameTime(start_frame))
        _, acts = _toolbar_actions()
        acts["qtStartMotionMatchingToolBarAction"].trigger()
        return RLPy.RGlobal.GetMotionDirector().IsRunning()
    fps_v = RLPy.RGlobal.GetFps().ToFloat() if hasattr(RLPy.RGlobal.GetFps(), "ToFloat") else 30.0
    probe = [start_frame + 15, start_frame + max(16, int(dur * fps_v) - 15)]

    def fingerprint():
        # CLAUDE-NOTE (2026-10-16, plaza): a re-take of the same length leaves the clip list identical, so "no new
        # clip" was a false negative for all 11 people; compare hip positions at two frames of the take instead.
        from tools import scene_qa as Q
        avs = [_avatar(p["avatar"]) for p in preps]
        d = Q._sample(avs, probe)
        return {n: [tuple(round(c, 1) for c in h) for h in b.get("CC_Base_Hip", [])] for n, b in d.items()}
    def stop():
        _, acts = _toolbar_actions()
        acts["qtStopMotionMatchingToolBarAction"].trigger()
        return True

    def verify_all(before_fp):
        # CLAUDE-NOTE (2026-10-16, plaza): verifying each avatar on every frame cost 11 x 600 scene evaluations and
        # blew the 900 s call timeout; sample ALL avatars in one pass, every 3rd frame.
        from tools import scene_qa as Q
        after_fp = fingerprint()
        step = 3
        frames = list(range(start_frame, start_frame + int(dur * fps_v) + 1, step))
        avs = [_avatar(p["avatar"]) for p in preps]
        data = Q._sample(avs, frames)
        out = []
        for p in preps:
            av = _avatar(p["avatar"])
            clip = _take_clip(av, start_frame)
            recorded = clip is not None and (clip not in p["before"] or after_fp.get(av.GetName()) != before_fp.get(av.GetName()))
            if not recorded:
                out.append({"ok": False, "avatar": av.GetName(), "error": "no new clip after the MD run"})
                continue
            c0, clen = clip
            f = RLPy.RGlobal.GetFps()
            row = {"ok": True, "avatar": av.GetName(), "recorded_s": round(clen / 6000.0, 2),
                   "clip_frames": [f.GetFrameIndex(RLPy.RTime.FromValue(c0)), f.GetFrameIndex(RLPy.RTime.FromValue(c0 + clen))]}
            row.update(p.get("verify", _verify_walker)(p, data[av.GetName()], frames, step))
            out.append(row)
        hips = {n: b["CC_Base_Hip"] for n, b in data.items() if "CC_Base_Hip" in b}
        coll = [o for o in Q.find_overlaps(frames, hips, collision_cm)] if len(hips) > 1 else []
        return out, coll

    # CLAUDE-NOTE (2026-10-16, plaza): even with avoidance two wanderers walked through each other for 2 s; MD takes
    # are random, so re-record (same assignments) while people collide (hips < collision_cm), up to `retakes` times.
    # Each take REPLACES the previous clips, so the result reported is always the last (= the one on the timeline).
    for attempt in range(1 + max(0, int(retakes))):
        before_fp = run(fingerprint)
        _trace(f"starting take {attempt + 1}")
        started = run(start)
        _trace(f"started={started}")
        if not started:
            raise RuntimeError("Motion Director did not start (check iclone_eyes.py popups for a dialog)")
        time.sleep(dur)                       # HTTP thread waits; iClone's main thread runs the MD simulation
        _trace("stopping")
        run(stop)
        time.sleep(3.0)                       # the recorded clips are committed after stop
        _trace("verifying")
        out, coll = run(lambda: verify_all(before_fp))
        _trace(f"verified take {attempt + 1}: {len(coll)} collision run(s)")
        if not coll:
            break
    for row in out:
        row["takes"] = attempt + 1
        row["collisions"] = [{"with": c["b"] if c["a"] == row.get("avatar") else c["a"], "frames": [c["from"], c["to"]],
                              "min_cm": c["min_cm"]} for c in coll if row.get("avatar") in (c["a"], c["b"])]
    return out, dur


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
        res, dur = _record_take(groups[sf], args.get("seconds"), sf,
                                avoidance_radius_cm=float(args.get("avoidance_radius_cm", 50.0)))
        results += res
        takes.append({"start_frame": sf, "walkers": [w["avatar"] for w in groups[sf]], "seconds": round(dur, 1)})
    return {"ok": all(r.get("ok") for r in results), "takes": takes, "walkers": results}


def _zone_bounds(zone):
    mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
    zone.GetBounds(mx, c, mn)
    return (mn.x, mx.x, mn.y, mx.y, mx.z)


def _scatter(bounds, n, spacing, margin=0.15, seed=7):
    """n start points [x, y, heading] inside the zone footprint (grid cells with jitter)."""
    import random
    x0, x1, y0, y1, _ = bounds
    w, h = x1 - x0, y1 - y0
    x0, x1, y0, y1 = x0 + w * margin, x1 - w * margin, y0 + h * margin, y1 - h * margin
    cols = max(1, math.ceil(math.sqrt(n * (x1 - x0) / max(1.0, y1 - y0))))
    rows = max(1, math.ceil(n / cols))
    rnd = random.Random(seed)
    pts = []
    for i in range(n):
        cx = x0 + (i % cols + 0.5) * (x1 - x0) / cols
        cy = y0 + (i // cols + 0.5) * (y1 - y0) / rows
        j = min(spacing * 0.3, (x1 - x0) / cols * 0.25)
        pts.append([cx + rnd.uniform(-j, j), cy + rnd.uniform(-j, j), rnd.uniform(-180, 180)])
    return pts


def _prepare_wanderer(w):
    import json
    av = _avatar(w["avatar"])
    zone = RLPy.RScene.FindObject(RLPy.EObjectType_Prop, w["zone"])
    if zone is None:
        raise ValueError(f"no prop named {w['zone']!r} to use as the wander zone")
    imd = _apply_imd(av, w.get("imd"))
    b = _zone_bounds(zone)
    if w.get("start"):
        from tools.icmcp_extra import place_object
        x, y, hd = w["start"]
        place_object({"name": av.GetName(), "frame": 0, "position": {"x": x, "y": y, "z": b[4]},
                      "rotation_degrees": {"x": 0, "y": 0, "z": hd}})
    _select_only(av)
    _set_start_mode("Record Selected")
    mode = _ensure_mode("Auto In Zone")
    applied = {}
    if w.get("settings"):
        # CLAUDE-NOTE (2026-10-16, measured): setAutoSetting applies reliably ONE key per call, with the avatar selected
        # and the panel in zone mode; a multi-key map changed some keys, skipped others and altered IdleMoveFrequency.
        # Set key by key and read each back from getMatchingDataAutoSetting.
        aid = _dialog_id(av.GetName())
        for k, v in w["settings"].items():
            _js_call("dlg.setAutoSetting(['%s'], %s)" % (aid, json.dumps({k: v})))
        got = _js_call("dlg.getMatchingDataAutoSetting('%s')" % aid) or {}
        applied = {k: got.get(k) for k in w["settings"]}
        bad = {k: (v, got.get(k)) for k, v in w["settings"].items() if got.get(k) != v}
        if bad:
            raise RuntimeError(f"MD Action Settings not applied for {av.GetName()} (wanted, got): {bad}")
    # pick pixel: a point of the zone's top surface far from every avatar on screen (a click on an avatar picks it)
    grid = [(b[0] + (b[1] - b[0]) * fx, b[2] + (b[3] - b[2]) * fy, b[4]) for fx in (0.1, 0.3, 0.5, 0.7, 0.9)
            for fy in (0.1, 0.3, 0.5, 0.7, 0.9)]
    # CLAUDE-NOTE (2026-10-16, measured): the pick failed for the 2nd wanderer - transforms read right after
    # place_object are stale, so "far from avatars" used old positions and the click hit the 1st wanderer. Avoid the
    # KNOWN start positions (w["avoid"]) plus the other avatars, and try the 4 best pixels.
    heads = []
    for x, y in w.get("avoid", []):
        heads += [(x, y, b[4] + 20), (x, y, b[4] + 100)]
    for a in RLPy.RScene.GetAvatars():
        wt = a.WorldTransform()
        t = wt.T()
        heads += [(t.x, t.y, t.z + 20), (t.x, t.y, t.z + 100)]
    vp, px = world_to_viewport(grid + heads)
    gpx, apx = px[:len(grid)], [p for p in px[len(grid):] if p]
    cand = [p for p in gpx if p and 5 < p[0] < vp.width() - 5 and 5 < p[1] < vp.height() - 5]
    if not cand:
        raise RuntimeError(f"zone {w['zone']} is not visible in the current camera; aim a camera at it")
    cand.sort(key=lambda p: -min([math.hypot(p[0] - q[0], p[1] - q[1]) for q in apx] or [1e9]))
    zname = zone.GetName()

    def check():
        return _mgr(av.GetName()).get("BoundingName") == zname

    def pick():
        err = None
        for p in cand[:4]:
            try:
                return _pick(av, "Bound", zname, vp, p, check)
            except RuntimeError as e:
                err = e
        raise err
    pick()
    return {"avatar": av.GetName(), "zone": zname, "bounds": b, "imd": imd, "mode": mode, "settings": applied,
            "before": _clips(av.GetSkeletonComponent()), "assigned": check, "repick": pick,
            "verify": _verify_wanderer}


def _verify_wanderer(prep, data, frames, step):
    from tools import scene_qa as Q
    fps = RLPy.RGlobal.GetFps()
    rep = Q.analyze_avatar(frames, data, fps.ToFloat(), step=step)
    hips = data["CC_Base_Hip"]
    x0, x1, y0, y1, _ = prep["bounds"]
    inside = sum(1 for h in hips if x0 <= h[0] <= x1 and y0 <= h[1] <= y1) / max(1, len(hips))
    travel = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(hips, hips[1:]))
    return {"slide_ratio": rep.get("slide_ratio"), "pop_count": rep.get("pop_count"),
            "inside_zone": round(inside, 3), "travel_cm": round(travel), "settings": prep.get("settings")}


def md_wander(args):
    """Wandering crowd: Motion Director 'Auto In Zone' on a zone prop, all wanderers in one take."""
    # CLAUDE-NOTE (2026-10-16): zone = any prop (manual: Auto-Creating-Motions-in-Zone); assigned with the dialog's
    # pickAutoBoundObject + a viewport click on the prop, verified via getMatchingManagerSetting().BoundingName. Action
    # Settings (idle/move ratio, perform/mixer/speed/mode frequencies) go through setAutoSetting([id], {...}).
    res, dur = _record_take(_wander_people(args), float(args.get("seconds", 15)), int(args.get("start_frame", 0)),
                            _prepare_wanderer, avoidance_radius_cm=float(args.get("avoidance_radius_cm", 50.0)),
                            retakes=int(args.get("retakes", 0)))
    return {"ok": all(r.get("ok") for r in res), "seconds": round(dur, 1), "wanderers": res}


def _wander_people(block):
    """Per-wanderer dicts for one zone block: scattered start points, zone, avoid list, iMD and settings."""
    from dispatch import run
    zone = block["zone"]
    people = [dict(w) if isinstance(w, dict) else {"avatar": w} for w in block["avatars"]]
    if block.get("scatter", True):
        b = run(lambda: _zone_bounds(RLPy.RScene.FindObject(RLPy.EObjectType_Prop, zone)))
        for w, p in zip(people, _scatter(b, len(people), float(block.get("spacing_cm", 150)))):
            w.setdefault("start", p)
    starts = [tuple(w["start"][:2]) for w in people if w.get("start")]
    for w in people:
        w["zone"] = zone
        w["avoid"] = starts
        w.setdefault("imd", block.get("imd"))
        if block.get("settings"):
            w.setdefault("settings", block["settings"])
    return people


def md_crowd(args):
    """Path walkers + zone wanderers in ONE Motion Director take, so they avoid each other."""
    # CLAUDE-NOTE (2026-10-16, plaza test): wanderers and path walkers recorded in separate takes walked through each
    # other (MD crowd avoidance only acts inside one simulation): 6 on-screen hip overlaps. One take fixes that. Zone
    # props are hidden after the picks and before Start (a visible 1 cm zone slab made path walkers detour 2.5 m).
    from dispatch import run
    people = [dict(w) for w in args.get("walkers", [])]
    zones = []
    for block in args.get("wander", []):
        people += _wander_people(block)
        zones.append(block["zone"])

    def hide(visible):
        for z in zones:
            o = RLPy.RScene.FindObject(RLPy.EObjectType_Prop, z)
            if o:
                o.SetVisible(RLPy.RTime.FromValue(0), visible)
    hide_zones = args.get("hide_zones", True)
    # a zone hidden by an earlier take cannot be clicked for the pick (measured: Z1's pick failed after a re-run)
    run(lambda: hide(True))
    res, dur = _record_take(people, args.get("seconds"), int(args.get("start_frame", 0)),
                            lambda w: _prepare_wanderer(w) if w.get("zone") else _prepare_walker(w),
                            before_start=(lambda: hide(False)) if hide_zones and zones else None,
                            avoidance_radius_cm=float(args.get("avoidance_radius_cm", 50.0)),
                            retakes=int(args.get("retakes", 2)), collision_cm=float(args.get("collision_cm", 30.0)))
    return {"ok": all(r.get("ok") for r in res), "seconds": round(dur, 1), "zones_hidden": bool(hide_zones and zones),
            "takes": res[0].get("takes") if res else 0,
            "collisions": sorted({tuple(sorted((r["avatar"], c["with"]))) for r in res for c in r.get("collisions", [])}),
            "people": res}


def register(registry):
    registry["md_crowd"] = {
        "handler": md_crowd, "main_thread": False,
        "description": "A MIXED moving crowd in ONE Motion Director take (so everyone avoids everyone): walkers=[{avatar, "
                       "path, imd?}] on paths plus wander=[{zone, avatars, settings?, spacing_cm?, scatter?}] blocks "
                       "roaming zone props. Zones are hidden before Start (hide_zones, default true). seconds defaults to "
                       "the longest path / 1 m/s + 3 s. Paths and zones must be visible in the current camera.",
        "inputSchema": {"type": "object", "properties": {
            "walkers": {"type": "array"}, "wander": {"type": "array"}, "seconds": {"type": "number"},
            "start_frame": {"type": "integer"}, "hide_zones": {"type": "boolean"},
            "avoidance_radius_cm": {"type": "number", "description": "MD crowd avoidance radius (default 50; iClone default 39)"},
            "retakes": {"type": "integer", "description": "re-record up to N times while two people collide (default 2)"},
            "collision_cm": {"type": "number", "description": "hip distance counted as a collision (default 30)"}}}}
    registry["md_wander"] = {
        "handler": md_wander, "main_thread": False,
        "description": "WANDERING CROWD via Motion Director 'Auto In Zone': avatars ([names] or [{avatar, imd?, "
                       "start?: [x, y, heading]}]) roam inside a zone PROP (any prop, e.g. a flat box), scattered over it "
                       "first (scatter, spacing_cm), recorded in ONE real-time take of `seconds` (default 15). settings = "
                       "MD Action Settings, e.g. {IdleMoveFrequency, MoveTimeRangeStart/End, IdleTimeRangeStart/End, "
                       "EventFrequency, MixerFrequency, SwitchSpeedFrequency}. The zone must be visible in the current "
                       "camera. Returns slide, pops, fraction of time inside the zone, distance travelled.",
        "inputSchema": {"type": "object", "properties": {
            "avatars": {"type": "array"}, "zone": {"type": "string"}, "seconds": {"type": "number"},
            "start_frame": {"type": "integer"}, "imd": {"type": "string"}, "settings": {"type": "object"},
            "scatter": {"type": "boolean"}, "spacing_cm": {"type": "number"}}, "required": ["avatars", "zone"]}}
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
