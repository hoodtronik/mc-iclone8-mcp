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
