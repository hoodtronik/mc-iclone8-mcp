"""Offline tests for track_target's math: camera forward from a quaternion, and the aim check."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes  # noqa: E402


class _Q:
    def __init__(self, x, y, z, w): self.x, self.y, self.z, self.w = x, y, z, w


class TestTrackTargetMath(unittest.TestCase):
    def setUp(self):
        _install_fakes([], {})
        from tools import icmcp_extra
        self.x = icmcp_extra

    def test_identity_camera_looks_down_minus_z(self):
        f = self.x._q_forward(_Q(0, 0, 0, 1))
        self.assertEqual(tuple(round(v, 6) for v in f), (0.0, 0.0, -1.0))

    def test_rotation_about_x_by_90_looks_plus_y(self):
        # measured camera at y=-700 aiming at the origin had q ~ (0.69, 0.06, 0.06, 0.72) -> forward ~ +Y
        s = math.sin(math.radians(45))
        f = self.x._q_forward(_Q(s, 0, 0, s))
        self.assertEqual(tuple(round(v, 6) for v in f), (0.0, 1.0, 0.0))

    def test_measured_quaternion_points_at_head(self):
        f = self.x._q_forward(_Q(0.7004809975624084, 0.05847759172320366, 0.059172555804252625, 0.7088056206703186))
        cam, head = (300.0, -700.0, 160.0), (182.79, -2.89, 151.65)
        d = [h - c for h, c in zip(head, cam)]; n = math.sqrt(sum(v * v for v in d))
        fn = math.sqrt(sum(v * v for v in f))   # measured quaternion is not exactly unit length
        err = math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(f, d)) / (n * fn)))))
        self.assertLess(err, 2.0)


if __name__ == "__main__":
    unittest.main()
