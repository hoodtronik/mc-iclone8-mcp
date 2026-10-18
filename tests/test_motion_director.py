"""Offline tests for motion_director's pure helpers (MD recording itself is live-verified, see the module notes)."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes  # noqa: E402


class TestScatter(unittest.TestCase):
    def setUp(self):
        _install_fakes([], {})
        from tools import motion_director
        self.md = motion_director

    def test_points_stay_inside_the_inset_zone(self):
        b = (-450.0, 450.0, -550.0, 50.0, 1.0)
        pts = self.md._scatter(b, 6, 160)
        self.assertEqual(len(pts), 6)
        for x, y, hd in pts:
            self.assertTrue(-450 * 0.7 - 1 <= x <= 450 * 0.7 + 1)
            self.assertTrue(-550 + 90 - 1 <= y <= 50 - 90 + 1)
            self.assertTrue(-180 <= hd <= 180)

    def test_points_are_spread_apart(self):
        pts = self.md._scatter((-450.0, 450.0, -550.0, 50.0, 1.0), 6, 160)
        gaps = [math.hypot(a[0] - b[0], a[1] - b[1]) for i, a in enumerate(pts) for b in pts[i + 1:]]
        self.assertGreater(min(gaps), 80.0)

    def test_deterministic(self):
        b = (0.0, 300.0, 0.0, 300.0, 0.0)
        self.assertEqual(self.md._scatter(b, 4, 100), self.md._scatter(b, 4, 100))


class TestSettle(unittest.TestCase):
    def setUp(self):
        _install_fakes([], {})
        from tools import motion_director
        self.md = motion_director

    def test_picks_the_still_feet_together_frame_before_leaving(self):
        frames = [0, 3, 6, 9, 12, 15, 18]
        hips = [(0, 0, 90), (20, 0, 90), (30, 0, 90), (31, 0, 90), (31, 0, 90), (40, 0, 90), (80, 0, 90)]
        lf = [(0, 10, 0), (0, 30, 0), (0, 25, 0), (0, 12, 0), (0, 10, 0), (0, 30, 0), (0, 30, 0)]
        rf = [(0, -10, 0)] * 7
        self.assertEqual(self.md.settle_frame(frames, hips, lf, rf, 6, ((30.0, 0.0), (0.0, 0.0)), 40.0), 12)


    def test_stuck_only_when_far_from_the_end_and_barely_moved(self):
        # CafeTrial: blocked by a Room box (moved ~40 cm); DuskStreet: a 12 m stroll still under way at the scene end
        self.assertTrue(self.md.stuck({"end_distance_to_path_end_cm": 330, "travel_cm": 40}, {"path_length_cm": 335}))
        self.assertFalse(self.md.stuck({"end_distance_to_path_end_cm": 141, "travel_cm": 1050}, {"path_length_cm": 1200}))
        self.assertFalse(self.md.stuck({"end_distance_to_path_end_cm": 30, "travel_cm": 20}, {"path_length_cm": 335}))

    def test_arrival_allows_sideways_drift_but_not_short_of_the_end(self):
        end = ((900.0, -130.0), (700.0, -125.0))        # StreetScene Sidewalk_E end, walking +X
        self.assertTrue(self.md.arrived((905.0, -75.0), end))       # 55 cm to the side at the end
        self.assertTrue(self.md.arrived((1092.0, -70.0), end))      # overshot
        self.assertFalse(self.md.arrived((846.0, -78.0), end))      # 54 cm short
        self.assertFalse(self.md.arrived((900.0, 60.0), end))       # on another lane


if __name__ == "__main__":
    unittest.main()
