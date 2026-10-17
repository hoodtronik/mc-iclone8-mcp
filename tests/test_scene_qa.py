"""Offline tests for tools.scene_qa's pure metric helpers (sampling/rendering are live-verified, see the module)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import scene_qa as Q  # noqa: E402

FPS = 30
FRAMES = list(range(60))
HIP = [(4.0 * i, 0.0, 90.0) for i in FRAMES]          # 120 cm/s along +X


def _stepping_foot(phase):
    """A foot that is planted for 15 frames, then swings 8 cm/frame for 15 (alternating with the other foot)."""
    x, out = 0.0, []
    for i in FRAMES:
        if (i // 15) % 2 == phase:
            x += 8.0
        out.append((x, 0.0, 2.0))
    return out


class TestAnalyzeAvatar(unittest.TestCase):
    def test_glide_scores_near_one(self):
        bones = {"CC_Base_Hip": HIP, "CC_Base_L_ToeBase": [(4.0 * i, -8, 2) for i in FRAMES],
                 "CC_Base_R_ToeBase": [(4.0 * i, 8, 2) for i in FRAMES]}
        r = Q.analyze_avatar(FRAMES, bones, FPS)
        self.assertEqual(r["slide_ratio"], 1.0)
        self.assertEqual(r["hip_speed_cm_s"], 120.0)

    def test_planted_steps_score_near_zero(self):
        bones = {"CC_Base_Hip": HIP, "CC_Base_L_ToeBase": _stepping_foot(0), "CC_Base_R_ToeBase": _stepping_foot(1)}
        self.assertEqual(Q.analyze_avatar(FRAMES, bones, FPS)["slide_ratio"], 0.0)

    def test_root_teleport_is_a_pop(self):
        hip = HIP[:30] + [(x + 50, y, z) for x, y, z in HIP[30:]]
        bones = {"CC_Base_Hip": hip, "CC_Base_L_ToeBase": _stepping_foot(0), "CC_Base_R_ToeBase": _stepping_foot(1)}
        r = Q.analyze_avatar(FRAMES, bones, FPS)
        self.assertEqual(r["pops"][0]["frame"], 30)
        self.assertGreater(r["pops"][0]["hip_speed_cm_s"], 450)

    def test_jog_stride_is_not_a_pop_but_a_seam_is(self):
        # DuskStreet jogger: hip 360 cm/s, toe swings 21.3 cm per frame relative to the hip every stride
        hip = [(12.0 * i, 0.0, 92.0) for i in FRAMES]
        toe = [(12.0 * i + (10.65 if i % 2 else -10.65), -8.0, 5.0) for i in FRAMES]
        bones = {"CC_Base_Hip": hip, "CC_Base_L_ToeBase": toe, "CC_Base_R_ToeBase": [(12.0 * i, 8.0, 5.0) for i in FRAMES]}
        self.assertEqual(Q.analyze_avatar(FRAMES, bones, FPS)["pop_count"], 0)
        seam = [(x, y + (50.0 if i >= 30 else 0.0), z) for i, (x, y, z) in enumerate(bones["CC_Base_R_ToeBase"])]
        r = Q.analyze_avatar(FRAMES, dict(bones, CC_Base_R_ToeBase=seam), FPS)
        self.assertEqual(r["pops"][0]["frame"], 30)

    def test_standing_avatar_has_no_slide_metric(self):
        bones = {"CC_Base_Hip": [(0, 0, 90)] * 10, "CC_Base_L_ToeBase": [(0, -8, 2)] * 10, "CC_Base_R_ToeBase": [(0, 8, 2)] * 10}
        r = Q.analyze_avatar(list(range(10)), bones, FPS)
        self.assertEqual(r["moving_frames"], 0)
        self.assertNotIn("slide_ratio", r)
        self.assertEqual(r["pop_count"], 0)


class TestHelpers(unittest.TestCase):
    def test_overlap_runs(self):
        runs = Q.find_overlaps([0, 1, 2, 3], {"a": [(0, 0, 0)] * 4, "b": [(100, 0, 0), (30, 0, 0), (10, 0, 0), (90, 0, 0)]})
        self.assertEqual(runs, [{"a": "a", "b": "b", "from": 1, "to": 2, "min_cm": 10.0}])

    def test_frame_list(self):
        self.assertEqual(Q.frame_list({"start_frame": 0, "end_frame": 100, "count": 5}), [0, 25, 50, 75, 100])
        self.assertEqual(Q.frame_list({"frames": [3, 9]}), [3, 9])

    def test_crop_box_keeps_aspect_and_clamps(self):
        box = Q.crop_box([(10, 10), (50, 90), None], 100, 100, 0.1, 0.75)
        self.assertEqual(box, (0, 2, 66, 98))
        self.assertIsNone(Q.crop_box([None, None], 100, 100))


if __name__ == "__main__":
    unittest.main()
