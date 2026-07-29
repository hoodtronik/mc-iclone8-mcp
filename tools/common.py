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
