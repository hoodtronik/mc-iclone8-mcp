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
