"""Offline tests for generate_crowd: preset JSON shape and argument validation (UI driving measured on 8.75.5630.1)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes  # noqa: E402


class TestGenerateCrowd(unittest.TestCase):
    def setUp(self):
        _install_fakes([], {})
        from tools import icmcp_extra
        self.x = icmcp_extra

    def test_preset_matches_the_panels_own_save_format(self):
        p = self.x._crowd_preset([{"path": r"F:\a\Party_F.iavatar"}, {"path": "F:/b/Kid.iavatar", "ratio": 3, "tags": ["Child"]}], True)
        self.assertEqual(p["Version"], "2.0")
        g = p["Group"][0]
        self.assertEqual(g["Name"], "Default Group")
        self.assertTrue(g["IsAvatarWithVariantMaterials"])
        self.assertEqual([a["Path"] for a in g["AvatarList"]], ["F:/a/Party_F.iavatar", "F:/b/Kid.iavatar"])
        self.assertEqual([a["Ratio"] for a in g["AvatarList"]], [1, 3])
        self.assertEqual(g["AvatarList"][1]["Tag"], ["Child"])
        self.assertTrue(all(a["Check"] for a in g["AvatarList"]))

    def test_motion_pool_entries_and_loop_flags_stay_off(self):
        p = self.x._crowd_preset([{"path": "F:/a/A.iavatar"}], False,
                                 [{"path": "F:/m/idle.rlMotion", "loop_count": 5, "tags": ["Adult"]}])
        g = p["Group"][0]
        self.assertEqual(g["MotionList"], [{"Check": True, "LoopCount": 5, "MotionOption": [], "MotionPath": "F:/m/idle.rlMotion", "Tag": ["Adult"]}])
        # AlwaysLoop / RandomStart true with a motion crashed iClone 8.75 on Load: they must stay false
        self.assertFalse(g["AlwaysLoop"])
        self.assertFalse(g["RandomStart"])

    def test_missing_actor_file_is_refused_before_touching_the_ui(self):
        with self.assertRaises(FileNotFoundError):
            self.x.generate_crowd({"actors": [os.path.join(tempfile.gettempdir(), "no_such_actor.iavatar")]})

    def test_empty_actor_list_is_refused(self):
        with self.assertRaises(ValueError):
            self.x.generate_crowd({"actors": []})

    def test_missing_motion_file_is_refused(self):
        here = os.path.abspath(__file__)
        with self.assertRaises(FileNotFoundError):
            self.x.generate_crowd({"actors": [here], "motions": [os.path.join(tempfile.gettempdir(), "no_such_motion.rlMotion")]})


if __name__ == "__main__":
    unittest.main()
