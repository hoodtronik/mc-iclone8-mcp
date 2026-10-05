import math
import sys
import unittest
from unittest.mock import patch

from performance_support import SDK, load


class MotionAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.sdk = SDK()
        self.p = load("performance", self.sdk)
        self.a = load("motion_analysis", self.sdk, self.p)
        self.qt = patch.dict(sys.modules, {"PySide2": self.sdk.Qt})
        self.qt.start()
        self.addCleanup(self.qt.stop)
        self.source = self.sdk.sk.bones[0]
        self.target = self.sdk.sk.bones[1]
        self.args = {
            "source": {"avatar": "Actor", "bone": "Arm_R"},
            "target": {"avatar": "Actor", "bone": "Arm_L"},
            "seconds": [0, 1, 2],
            "tolerance_cm": 0.01,
            "tolerance_deg": 0.01,
        }

    def test_shared_translation_and_rotation_cancel_in_target_space(self):
        def rotation():
            angle = self.sdk.tick / 6000 * math.pi / 4
            return [0, 0, math.sin(angle / 2), math.cos(angle / 2)]

        self.target.world = lambda: ([self.sdk.tick / 6000, 0, 0], rotation())

        def source_world():
            local = self.a.rotate(rotation(), [2, 0, 0])
            return [local[0] + self.sdk.tick / 6000, local[1], local[2]], rotation()

        self.source.world = source_world
        result = self.a.check_contact_pose(dict(self.args, expected_distance_cm=2))
        self.assertTrue(result["passed"])
        self.assertAlmostEqual(result["max_drift_cm"], 0)
        self.assertAlmostEqual(result["max_rotation_drift_deg"], 0, places=5)
        self.assertEqual(self.sdk.tick, 0)

    def test_gap_can_fail_while_drift_passes(self):
        self.source.world = lambda: ([10, 0, 0], [0, 0, 0, 1])
        result = self.a.check_contact_pose(dict(self.args, expected_distance_cm=0))
        self.assertEqual(result["max_drift_cm"], 0)
        self.assertFalse(result["passed"])

    def test_rotation_drift_can_fail_without_translation(self):
        self.source.world = lambda: (
            [0, 0, 0],
            [0, 0, math.sin(self.sdk.tick / 12000), math.cos(self.sdk.tick / 12000)],
        )
        result = self.a.check_contact_pose(self.args)
        self.assertFalse(result["passed"])
        self.assertGreater(result["max_rotation_drift_deg"], 100)

    def test_quaternion_sign_is_equivalent(self):
        self.assertEqual(self.a.angular_error([0, 0, 0, 1], [0, 0, 0, -1]), 0)

    def test_world_mode_and_submillimeter_precision(self):
        self.source.world = lambda: ([self.sdk.tick / 6000 * 0.002, 0, 0], [0, 0, 0, 1])
        args = dict(self.args)
        args.pop("target")
        result = self.a.check_contact_pose(args)
        self.assertEqual(result["space"], "world")
        self.assertAlmostEqual(result["max_drift_cm"], 0.004)
        with self.assertRaises(ValueError):
            self.a.check_contact_pose(dict(args, expected_distance_cm=0))

    def test_sampling_error_restores_exact_playhead(self):
        self.sdk.tick = 12345
        self.source.world = lambda: ([math.nan, 0, 0], [0, 0, 0, 1])
        with self.assertRaises(ValueError):
            self.a.check_contact_pose(self.args)
        self.assertEqual(self.sdk.tick, 12345)

    def test_bad_samples_fail_without_seeking(self):
        self.sdk.tick = 333
        for stamps in ([0, 0], [0, 0.00001], [2, 1], [0, math.inf], [0, 11]):
            with self.subTest(stamps=stamps), self.assertRaises(ValueError):
                self.a.check_contact_pose(dict(self.args, seconds=stamps))
            self.assertEqual(self.sdk.tick, 333)

    def test_playback_refused_without_edit(self):
        self.sdk.RGlobal.IsPlaying = lambda: True
        with self.assertRaises(ValueError):
            self.a.check_contact_pose(self.args)

    def test_gaze_returns_direction_not_automatic_keys(self):
        self.target.world = lambda: ([0, 0, 10], [0, 0, 0, 1])
        result = self.a.plan_actor_gaze(dict(self.args, seconds=1))
        self.assertEqual(result["world_direction"], [0, 0, 1])
        self.assertAlmostEqual(result["world_elevation_deg"], 90)
        self.assertFalse(result["executed"])
        self.assertFalse(result["native_look_at"])
        self.assertEqual(self.sdk.edits, [])

    def test_coincident_gaze_target_refused(self):
        with self.assertRaisesRegex(ValueError, "coincides"):
            self.a.plan_actor_gaze(dict(self.args, seconds=1))


if __name__ == "__main__":
    unittest.main()
