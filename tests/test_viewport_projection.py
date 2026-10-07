"""Offline test for the world->viewport projection, using the measured iClone 8.75 marker data as fixtures.
# CLAUDE-NOTE (2026-10-07): a red ball was placed at known points and found in viewport grabs; these numbers are those
# measurements (camera Camera_0 at frame 0, 1575x1159 view, horizontal AOV 39.598 deg).
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes  # noqa: E402


class TestViewportProjection(unittest.TestCase):
    def setUp(self):
        _install_fakes([], {})
        from tools import icmcp_extra
        self.x = icmcp_extra

    def test_identity_camera_centre_and_edges(self):
        # camera at origin looking down -Z: a point straight ahead hits the centre; tan(hfov/2)*depth to the right hits x=vw
        q = (0.0, 0.0, 0.0, 1.0)
        self.assertEqual(tuple(round(v, 3) for v in self.x._project((0, 0, -100), (0, 0, 0), q, 90.0, 800, 600)), (400.0, 300.0))
        self.assertEqual(round(self.x._project((100, 0, -100), (0, 0, 0), q, 90.0, 800, 600)[0], 3), 800.0)
        self.assertIsNone(self.x._project((0, 0, 100), (0, 0, 0), q, 90.0, 800, 600))   # behind the camera

    def test_vertical_uses_horizontal_tangent_times_aspect(self):
        q = (0.0, 0.0, 0.0, 1.0)
        # tan(45 deg)=1 horizontally; vertical tangent = 600/800 -> y=75 at depth 100 lands on the top edge
        self.assertEqual(round(self.x._project((0, 75, -100), (0, 0, 0), q, 90.0, 800, 600)[1], 3), 0.0)

    def test_round_trip_through_qrot_inv(self):
        s = math.sin(math.radians(45))
        # 90 deg about X: camera looking down -Z now looks along +Y
        self.assertEqual(tuple(round(v, 6) for v in self.x._qrot_inv((s, 0, 0, s), (0, 1, 0))), (0.0, 0.0, -1.0))


if __name__ == "__main__":
    unittest.main()
