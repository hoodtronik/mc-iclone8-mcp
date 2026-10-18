"""Offline tests for tools.lighting.sun_direction."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import lighting as Lt  # noqa: E402


def test_sun_from_plus_x_low_shines_toward_minus_x_and_down():
    d = Lt.sun_direction(90.0, 20.0)
    assert d[0] < -0.9 and abs(d[1]) < 1e-9 and d[2] < 0


def test_sun_behind_camera_shines_toward_plus_y():
    d = Lt.sun_direction(0.0, 45.0)
    assert abs(d[0]) < 1e-9 and d[1] > 0.7 and abs(d[2] + math.sqrt(0.5)) < 1e-9


def test_quat_forward_is_local_minus_z():
    from tools.lighting import quat_forward
    assert quat_forward(0, 0, 0, 1) == (0, 0, -1)            # rest pose looks straight down
    s = math.sqrt(0.5)
    fx, fy, fz = quat_forward(s, 0, 0, s)                     # +90 deg about X tips -Z to +Y
    assert abs(fx) < 1e-9 and abs(fy - 1) < 1e-9 and abs(fz) < 1e-9


def test_find_atmosphere_by_name(tmp_path):
    import pytest
    from tools.lighting import find_atmosphere
    (tmp_path / "2.Basic").mkdir()
    (tmp_path / "2.Basic" / "IBL Mist.iAtm").write_text("x")
    assert find_atmosphere("ibl mist", [str(tmp_path)]).endswith("IBL Mist.iAtm")
    assert find_atmosphere("IBL Mist.iAtm", [str(tmp_path)]).endswith("IBL Mist.iAtm")
    with pytest.raises(ValueError, match="IBL Mist"):
        find_atmosphere("IBL Misty", [str(tmp_path)])
