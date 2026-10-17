"""Offline tests for tools.acting timing and clip resolution."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import acting as A  # noqa: E402


def test_plan_back_to_back_at_and_until():
    acts = [{"clip": "idle"}, {"clip": "turn", "at_s": 5}, {"clip": "talk", "until_s": 12}]
    p = A.plan(acts, 30, [60, 45, 100])
    assert p[0] == (0, 0)
    assert p[1] == (1, 150)                     # at_s 5 -> frame 150 (after idle ended at 61)
    assert p[2] == (2, 196)                     # turn ends 150+45, +1
    assert p[3] == (2, 297) and len(p) == 4     # repeated until frame 360


def test_resolve_by_stem():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "Standing Pack 1"))
        f = os.path.join(d, "Standing Pack 1", "Right_Turn_090.rlMotion")
        open(f, "w").close()
        assert A.resolve_clip("Right_Turn_090", [d]) == f
        assert A.resolve_clip("Standing Pack 1/Right_Turn_090.rlMotion", [d]) == f


def test_last_active_finds_end_of_motion():
    rows = [(0, 0, 0, 0), (6, 0, 0, 0), (12, 5, 0, 10), (18, 9, 0, 40), (24, 9.2, 0, 40.5), (30, 9.2, 0, 40.5)]
    assert A.last_active(rows) == 18
    assert A.last_active([(0, 0, 0, 0), (6, 0, 0, 0)]) is None


def test_continuity_fix_rotates_about_hip_and_moves_it_back():
    import math
    P = (100.0, 0.0, 0.0)                       # avatar root; hip_next 10 cm ahead in +X
    (nx, ny, nz), q = A.continuity_fix(P, (0.0, 0.0, 0.0, 1.0), (110.0, 0.0, 95.0), (50.0, 50.0, 95.0), 90.0)
    # root was 10 cm behind the hip along -X; after +90 deg it is 10 cm along -Y of the target hip
    assert abs(nx - 50.0) < 1e-9 and abs(ny - 40.0) < 1e-9 and nz == 0.0
    assert abs(q[2] - math.sin(math.radians(45))) < 1e-9
