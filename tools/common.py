import RLPy


def current_time():
    return RLPy.RGlobal.GetTime()


def frame_time(frame=None):
    if frame is None:
        return current_time()
    return RLPy.RGlobal.GetFps().IndexedFrameTime(int(frame))


def current_frame():
    return RLPy.RGlobal.GetFps().GetFrameIndex(current_time())


def require_unit_interval(value, field):
    value = float(value)
    if value < 0.0 or value > 1.0:
        raise ValueError("%s must be between 0 and 1" % field)
    return value


def require_success(result, message):
    if result != RLPy.RStatus.Success:
        raise RuntimeError(message)
    return result


def rl_string(value):
    if value is None:
        return None
    to_string = getattr(value, "ToString", None)
    if callable(to_string):
        try:
            return to_string()
        except Exception:
            pass
    return str(value)


def euler_degrees_to_quaternion(x=0.0, y=0.0, z=0.0):
    """XYZ Euler (degrees) -> RQuaternion.
    # CLAUDE-NOTE (2026-09-26, hoodtronik fork): on iClone 8.74 RMatrix3.FromEulerAngle RETURNS a list
    # [RMatrix3, x, y, z] and does not fill the receiver; passing that list to FromRotationMatrix raised
    # "argument 2 of type 'RL::CMatrix3< float > const &'" and broke set_transform / camera / path rotation."""
    import math
    result = RLPy.RMatrix3().FromEulerAngle(RLPy.EEulerOrder_XYZ, math.radians(x), math.radians(y), math.radians(z))
    matrix = result[0] if isinstance(result, (list, tuple)) else result
    quaternion = RLPy.RQuaternion()
    quaternion.FromRotationMatrix(matrix)
    return quaternion


# CLAUDE-NOTE (2026-09-26, hoodtronik fork): RLPy has no "current project path" getter and RFileIO.SaveProject() requires
# a path, so we track it: last path save_project wrote, else the .iProject on iClone's own command line (launch_iclone.py).
_CURRENT_PROJECT = {"path": None, "cleared": False}


def set_current_project(path):
    if path:
        _CURRENT_PROJECT["path"] = path
        _CURRENT_PROJECT["cleared"] = False


def clear_current_project():
    # CLAUDE-NOTE (2026-10-07): after new_project the old path (tracked OR on iClone's command line) must not receive the
    # next checkpoint save, or an empty scene silently overwrites the real project -> also suppress the command-line fallback.
    _CURRENT_PROJECT["path"] = None
    _CURRENT_PROJECT["cleared"] = True


def scene_is_empty():
    # CLAUDE-NOTE (2026-10-07): guard for every automatic save. After a manual File > New Project (or a raw menu_action) the
    # tracked path is STALE and still names the previous project; an automatic save then overwrote a 35 MB scratch project
    # with the empty scene (measured). Nothing in an empty scene is worth a checkpoint, so skip the save instead.
    import RLPy
    return not (RLPy.RScene.GetAvatars() or RLPy.RScene.GetCameras()
                or [p for p in RLPy.RScene.GetProps() if p.GetName() != "Shadow Catcher"])


def current_project_path():
    # CLAUDE-NOTE (2026-10-16, measured - DATA LOSS): the tracked path used to win over iClone's own. A scratch scene opened
    # with RFileIO.LoadFile(<default project>) kept the tracked ParkBench path, and a checkpoint (filmstrip) saved the
    # scratch scene OVER ParkBench.iProject. iClone's live path is the truth: if iClone says it is showing its built-in
    # default project (an unsaved scratch scene), there is NO path to save to - never fall back to an older project.
    try:
        import os
        cur = RLPy.RApplication.GetCurrentProjectPath()
        default = RLPy.RApplication.GetDefaultProjectPath()
        if cur:
            if os.path.normcase(os.path.normpath(cur)) == os.path.normcase(os.path.normpath(default)):
                return None
            return cur
    except Exception:
        pass
    if _CURRENT_PROJECT["path"]:
        return _CURRENT_PROJECT["path"]
    if _CURRENT_PROJECT["cleared"]:
        return None
    try:
        import ctypes, shlex
        ctypes.windll.kernel32.GetCommandLineW.restype = ctypes.c_wchar_p
        line = ctypes.windll.kernel32.GetCommandLineW()
        for tok in shlex.split(line, posix=False):
            tok = tok.strip('"')
            if tok.lower().endswith(".iproject"):
                return tok
    except Exception:
        pass
    return None


def _clip_signature(sk):
    rows = []
    for i in range(sk.GetClipCount()):
        c = sk.GetClip(i)
        rows.append((c.ClipTimeToSceneTime(RLPy.RTime.FromValue(0)).ToInt(), c.GetClipLength().ToInt()))
    return rows


def _pose_print(avatar, time):
    """Rounded world positions of every skin bone a few frames into `time` (playhead restored by the caller)."""
    RLPy.RGlobal.SetTime(RLPy.RTime.FromValue(time.ToInt() + 10 * 200))      # +10 frames at 30 fps (6000 ticks/s)
    out = []
    for b in avatar.GetSkeletonComponent().GetSkinBones():
        wt = b.WorldTransform()
        t = wt.T()
        out.append((round(t.x, 1), round(t.y, 1), round(t.z, 1)))
    return out


def load_motion_clip(avatar, path, time, allow_unchanged=False):
    """Put a motion file on `avatar` starting at RTime `time`; returns the new RIClip.
    # CLAUDE-NOTE (2026-10-16, measured on 6 avatars incl. Motion Dummy, iClone 8.75): RFileIO.LoadMotion(path, t, av)
    # applies clips with the FEET GLUED to the floor (toe z constant, foot spread ~18 cm, a backflip became a fold-over;
    # walks glide with slide_ratio ~0.92). RFileIO.LoadFile(path) on the selected avatar at the playhead - what a UI drop
    # does - plays the same clip correctly (backflip feet 184 cm up; walk slide_ratio 0.04, stride 58 cm, toe lift 8 cm)
    # and a clip loaded right after another CONTINUES from where it ended. Never call LoadMotion for avatars."""
    sk = avatar.GetSkeletonComponent()
    before = _clip_signature(sk)
    now = RLPy.RGlobal.GetTime()
    selected = list(RLPy.RScene.GetSelectedObjects())
    try:
        pose_before = _pose_print(avatar, time)
        RLPy.RGlobal.SetTime(time)
        RLPy.RScene.ClearSelectObjects()
        RLPy.RScene.SelectObject(avatar)
        RLPy.RFileIO.LoadFile(path)
        pose_after = _pose_print(avatar, time) if _clip_signature(sk) == before else None
    finally:
        RLPy.RScene.ClearSelectObjects()
        if selected:
            RLPy.RScene.SelectObjects(selected)        # SelectObject replaces the selection; restore all of it
        RLPy.RGlobal.SetTime(now)
    # CLAUDE-NOTE (2026-10-16, measured): a freshly loaded avatar carries a 0-length placeholder clip at frame 0 and
    # LoadFile REPLACES a clip under the playhead, so the clip COUNT can stay the same on success; compare the clip list.
    # CLAUDE-NOTE (2026-10-16, measured): replacing a clip with one of the SAME length (Actor Group members F1/F2) leaves
    # the list unchanged too (14 false failures in the sit catalog), so then compare the pose a few frames in.
    if pose_after is not None and pose_after == pose_before and not allow_unchanged:
        # allow_unchanged: declarative callers re-applying the SAME clip at the same time (idempotent re-runs)
        raise RuntimeError("loading %s changed no motion on %s (file not applied, or the same clip was already there)"
                           % (path, avatar.GetName()))
    return sk.GetClipByTime(RLPy.RTime.FromValue(time.ToInt() + 1)) or sk.GetClip(sk.GetClipCount() - 1)
