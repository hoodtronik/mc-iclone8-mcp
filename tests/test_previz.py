import importlib.util
import json
import math
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

from mcp_handler import MCPHandler


class PrevizTests(unittest.TestCase):
    def setUp(self):
        self.original = object()
        self.avatar = Mock()
        self.avatar.GetName.return_value = "Actor"
        self.avatar.GetSkeletonComponent.return_value.GetClipCount.return_value = 3
        self.sdk = types.SimpleNamespace(
            RScene=types.SimpleNamespace(GetAvatars=lambda: [self.avatar]),
            RStatus=types.SimpleNamespace(Success=1),
            RGlobal=types.SimpleNamespace(GetFps=lambda: types.SimpleNamespace(IndexedFrameTime=lambda i: types.SimpleNamespace(ToInt=lambda: 100)), GetTime=lambda: self.original, IsPlaying=lambda: False,
                GetEndTime=lambda: types.SimpleNamespace(ToInt=lambda: 60000), SetTime=Mock(return_value=1)))
        self.fight = types.SimpleNamespace(_win=lambda s: s.replace("/", "\\"), _bone=Mock(),
                                          motion_track=Mock(return_value={"loaded": ["walk"]}), bone_track=Mock())
        spec = importlib.util.spec_from_file_location("previz_under_test", Path(__file__).parents[1] / "tools/previz.py")
        self.module = importlib.util.module_from_spec(spec)
        import tools
        with patch.dict(sys.modules, {"RLPy": self.sdk}), patch.object(tools, "fight_tools", self.fight, create=True):
            spec.loader.exec_module(self.module)
        self.files = patch.object(self.module.os.path, "isfile", return_value=True)
        self.files.start()
        self.addCleanup(self.files.stop)
        self.plan = {"avatar": "Actor", "clips": [{"path": "C:/walk.iMotion", "start_s": 0}]}
        self.contact = {"source": {"avatar": "Actor", "bone": "Foot"}, "seconds": [0, 1, 2]}

    def samples(self, points, target=None):
        self.fight.bone_track.return_value = {
            str(float(i)): dict({"Actor.Foot": p}, **({"Actor.Hand": target[i]} if target else {}))
            for i, p in enumerate(points)}

    def test_defaults_are_dry_run_and_append(self):
        result = self.module.safe_motion_track(self.plan)
        self.assertFalse(result["executed"])
        self.assertFalse(result["plan"]["replace"])
        self.assertEqual(result["existing_clip_count"], 3)
        self.fight.motion_track.assert_not_called()

    def test_execution_normalizes_sorts_and_preserves_flags(self):
        self.plan.update(execute=True, replace=True)
        self.plan["clips"] += [{"path": "C:/idle.iMotion", "start_s": 0.5, "speed": 2, "length_s": 1}]
        self.plan["clips"].reverse()
        self.module.safe_motion_track(self.plan)
        plan = self.fight.motion_track.call_args[0][0]
        self.assertTrue(plan["replace"])
        self.assertEqual([c["start_s"] for c in plan["clips"]], [0, .5])
        self.assertEqual(plan["clips"][0]["path"], "C:\\walk.iMotion")

    def test_later_missing_file_cannot_clear_existing_motion(self):
        self.plan.update(execute=True, replace=True)
        self.plan["clips"].append({"path": "C:/missing.iMotion", "start_s": 1})
        with patch.object(self.module.os.path, "isfile", side_effect=[True, False]), self.assertRaises(ValueError):
            self.module.safe_motion_track(self.plan)
        self.fight.motion_track.assert_not_called()

    def test_bad_nested_values_rejected_before_edit(self):
        for updates in ({"speed": 0}, {"speed": -1}, {"speed": math.nan}, {"start_s": math.inf},
                        {"start_s": -1}, {"start_s": True}, {"length_s": 0}, {"typo": 1},
                        {"speed": "2"}, {"speed": .001, "length_s": 1}, {"speed": 1e308, "length_s": 1e308}):
            with self.subTest(updates=updates):
                plan = dict(self.plan, execute=True, replace=True, clips=[dict(self.plan["clips"][0], **updates)])
                with self.assertRaises(ValueError):
                    self.module.safe_motion_track(plan)
        self.fight.motion_track.assert_not_called()

    def test_empty_plan_and_nonboolean_flags_rejected(self):
        for values in ({"clips": []}, {"replace": "false"}, {"execute": "false"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.module.safe_motion_track(dict(self.plan, **values))

    def test_duplicate_avatar_refused(self):
        self.sdk.RScene.GetAvatars = lambda: [self.avatar, self.avatar]
        with self.assertRaisesRegex(ValueError, "found 2"):
            self.module.safe_motion_track(self.plan)

    def test_stationary_foot_passes_and_playhead_restored(self):
        self.samples([[1, 2, 3]] * 3)
        result = self.module.check_contact(self.contact)
        self.assertTrue(result["passed"])
        self.assertEqual(result["max_drift_cm"], 0)
        self.sdk.RGlobal.SetTime.assert_called_once_with(self.original)

    def test_sliding_foot_reports_worst_time(self):
        self.samples([[0, 0, 0], [1, 0, 0], [4, 0, 0]])
        result = self.module.check_contact(self.contact)
        self.assertFalse(result["passed"])
        self.assertEqual(result["max_drift_cm"], 4)
        self.assertEqual(result["worst_seconds"], 2)

    def test_moving_target_uses_relative_translation(self):
        self.samples([[0, 0, 0], [5, 0, 0], [10, 0, 0]], [[2, 0, 0], [7, 0, 0], [12, 0, 0]])
        result = self.module.check_contact(dict(self.contact, target={"avatar": "Actor", "bone": "Hand"}))
        self.assertTrue(result["passed"])
        self.assertEqual(result["max_drift_cm"], 0)
        self.assertEqual(result["samples"][0]["distance_cm"], 2)

    def test_sampling_exception_still_restores_playhead(self):
        self.fight.bone_track.side_effect = RuntimeError("bad bone")
        with self.assertRaisesRegex(RuntimeError, "bad bone"):
            self.module.check_contact(self.contact)
        self.sdk.RGlobal.SetTime.assert_called_once_with(self.original)

    def test_restore_failure_is_reported(self):
        self.samples([[0, 0, 0]] * 3)
        self.sdk.RGlobal.SetTime.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "restore"):
            self.module.check_contact(self.contact)

    def test_bad_contact_inputs_cannot_seek(self):
        for values in ({"seconds": []}, {"seconds": [0, 0]}, {"seconds": [2, 1]},
                       {"seconds": [0, math.nan]}, {"seconds": [0, 11]}, {"tolerance_cm": -1},
                       {"target": self.contact["source"]}, {"source": {"avatar": "Actor", "bone": ""}}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.module.check_contact(dict(self.contact, **values))
        self.fight.bone_track.assert_not_called()
        self.sdk.RGlobal.SetTime.assert_not_called()

    def test_playback_refused(self):
        self.sdk.RGlobal.IsPlaying = lambda: True
        with self.assertRaisesRegex(ValueError, "Pause"):
            self.module.check_contact(self.contact)
        self.fight.bone_track.assert_not_called()

    def test_nonfinite_coordinates_cannot_report_success(self):
        self.samples([[0, 0, 0], [math.nan, 0, 0], [0, 0, 0]])
        with self.assertRaisesRegex(RuntimeError, "invalid coordinates"):
            self.module.check_contact(self.contact)

    def test_mcp_dry_run_and_validation_error(self):
        registry = {}
        self.module.register(registry)
        for tool in registry.values():
            tool["main_thread"] = False  # Host test; live registry always dispatches.
        handler = MCPHandler(registry)
        def call(args):
            return json.loads(handler(json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                                 "params": {"name": "safe_motion_track", "arguments": args}})))
        response = call(self.plan)
        self.assertFalse(json.loads(response["result"]["content"][0]["text"])["executed"])
        response = call(dict(self.plan, clips=[]))
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(response["id"], 7)


if __name__ == "__main__":
    unittest.main()
