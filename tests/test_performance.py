import json
import math
import tempfile
import unittest
from pathlib import Path

from performance_support import SDK, Clip, Time, load

from mcp_handler import MCPHandler


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.sdk = SDK()
        self.p = load("performance", self.sdk)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backup = str(Path(self.tmp.name) / "backup.iProject")
        self.plan = {
            "avatar": "Actor",
            "keys": [
                {"seconds": 3, "bones": {"Arm_R": {"rotation_degrees": {"x": 30}}}}
            ],
        }

    def test_scene_to_clip_time_and_masked_dry_run(self):
        result = self.p.set_pose_keys(self.plan)
        self.assertFalse(result["executed"])
        self.assertEqual(result["keys"][0]["clip_tick"], 12000)
        self.assertAlmostEqual(result["keys"][0]["after"], math.pi / 6)
        self.assertEqual(self.sdk.edits, [])
        self.assertEqual(self.sdk.saved, [])

    def test_execution_preserves_other_channels_and_restores_readback(self):
        result = self.p.set_pose_keys(
            dict(self.plan, execute=True, backup_path=self.backup)
        )
        self.assertTrue(result["executed"])
        self.assertEqual(len(self.sdk.edits), 1)
        clip = self.sdk.sk.clips[0]
        self.assertAlmostEqual(
            clip.channels[("Arm_R", "Rotation/RotationX")].values[12000], math.pi / 6
        )
        self.assertFalse(any(name == "Arm_L" for name, path in clip.channels))
        self.assertTrue(Path(self.backup).exists())

    def test_delta_adds_to_existing_value(self):
        result = self.p.set_pose_keys(dict(self.plan, mode="delta"))
        self.assertAlmostEqual(result["keys"][0]["after"], 0.2 + math.pi / 6)

    def test_bad_later_bone_cannot_write_earlier_key(self):
        self.plan["keys"].append(
            {"seconds": 4, "bones": {"Missing": {"rotation_degrees": {"x": 0}}}}
        )
        with self.assertRaises(ValueError):
            self.p.set_pose_keys(dict(self.plan, execute=True, backup_path=self.backup))
        self.assertEqual(self.sdk.edits, [])
        self.assertEqual(self.sdk.saved, [])

    def test_duplicate_after_quantization_refused(self):
        self.plan["keys"].append(
            {"seconds": 3.00001, "bones": {"Arm_R": {"rotation_degrees": {"x": 0}}}}
        )
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.p.set_pose_keys(self.plan)

    def test_quantized_boundary_and_gap_rejected(self):
        for s in (1, 6, 5.99999):
            with self.subTest(s=s), self.assertRaises(ValueError):
                self.p.set_pose_keys(
                    dict(
                        self.plan,
                        keys=[{"seconds": s, "bones": self.plan["keys"][0]["bones"]}],
                    )
                )

    def test_nonfinite_bool_axis_and_empty_update_rejected(self):
        for update in (
            {"rotation_degrees": {"x": math.nan}},
            {"rotation_degrees": {"q": 2}},
            {"position_cm": {"x": True}},
            {},
            {"rotation_degrees": {}},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.p.set_pose_keys(
                    dict(self.plan, keys=[{"seconds": 3, "bones": {"Arm_R": update}}])
                )

    def test_backup_required_new_nonempty_and_before_edits(self):
        with self.assertRaises(ValueError):
            self.p.set_pose_keys(dict(self.plan, execute=True))
        Path(self.backup).write_bytes(b"existing")
        with self.assertRaises(ValueError):
            self.p.set_pose_keys(dict(self.plan, execute=True, backup_path=self.backup))
        self.assertEqual(Path(self.backup).read_bytes(), b"existing")
        self.assertEqual(self.sdk.edits, [])

    def test_backup_failure_cannot_write(self):
        self.sdk.RFileIO.SaveProject = lambda path: 0
        with self.assertRaises(RuntimeError):
            self.p.set_pose_keys(dict(self.plan, execute=True, backup_path=self.backup))
        self.assertEqual(self.sdk.edits, [])

    def test_partial_failure_reports_backup_and_applied_steps(self):
        clip = self.sdk.sk.clips[0]
        bone = self.sdk.sk.bones[0]
        self.p.channel(clip, bone, "Rotation", "y").fail = True
        self.plan["keys"][0]["bones"]["Arm_R"]["rotation_degrees"]["y"] = 20
        with self.assertRaisesRegex(
            RuntimeError, "Partial edit; backup=.*applied=.*Rotation.x"
        ):
            self.p.set_pose_keys(dict(self.plan, execute=True, backup_path=self.backup))
        self.assertTrue(Path(self.backup).is_file())

    def test_silent_setter_rejection_detected(self):
        clip = self.sdk.sk.clips[0]
        self.p.channel(clip, self.sdk.sk.bones[0], "Rotation", "x").reject = True
        with self.assertRaisesRegex(RuntimeError, "readback"):
            self.p.set_pose_keys(dict(self.plan, execute=True, backup_path=self.backup))

    def test_capture_apply_preserves_explicit_mask(self):
        pose = self.p.capture_pose(
            {"avatar": "Actor", "seconds": 3, "bones": ["Arm_R", "Arm_L"]}
        )
        result = self.p.apply_pose(
            {"avatar": "Actor", "seconds": 4, "bones": ["Arm_L"], "pose": pose}
        )
        self.assertEqual({r["bone"] for r in result["keys"]}, {"Arm_L"})
        self.assertFalse(result["executed"])

    def test_hand_rotation_only_and_exact_mask(self):
        args = {
            "avatar": "Actor",
            "seconds": 3,
            "finger_bones": ["Finger_R"],
            "pose": {"bones": {"Finger_R": {"rotation_degrees": {"x": 20}}}},
        }
        self.assertEqual(self.p.apply_hand_pose(args)["keys"][0]["bone"], "Finger_R")
        args["pose"]["bones"]["Finger_R"]["position_cm"] = {"x": 1}
        with self.assertRaises(ValueError):
            self.p.apply_hand_pose(args)

    def test_named_preset_roundtrip_and_no_overwrite(self):
        pose = self.p.capture_pose(
            {"avatar": "Actor", "seconds": 3, "bones": ["Finger_R"]}
        )
        path = str(Path(self.tmp.name) / "can_grip.json")
        self.p.save_pose_preset({"name": "Can grip", "path": path, "pose": pose})
        loaded = self.p.load_pose_preset({"path": path})
        self.assertEqual(loaded["name"], "Can grip")
        self.assertEqual(loaded["pose"], pose)
        with self.assertRaises(FileExistsError):
            self.p.save_pose_preset({"name": "Other", "path": path, "pose": pose})

    def test_preset_nonfinite_values_rejected_before_creation(self):
        path = str(Path(self.tmp.name) / "bad.json")
        with self.assertRaises(ValueError):
            self.p.save_pose_preset(
                {
                    "name": "Bad",
                    "path": path,
                    "pose": {
                        "bones": {"Finger_R": {"rotation_degrees": {"x": math.inf}}}
                    },
                }
            )
        self.assertFalse(Path(path).exists())

    def test_preset_invalid_metadata_does_not_create_file(self):
        path = str(Path(self.tmp.name) / "invalid_metadata.json")
        for metadata in ({"seconds": math.nan}, {"avatar": {}}, {"clip_index": True}):
            pose = {"bones": {"Finger_R": {"rotation_degrees": {"x": 0}}}}
            pose.update(metadata)
            with self.assertRaises(ValueError):
                self.p.save_pose_preset({"name": "Bad", "path": path, "pose": pose})
            self.assertFalse(Path(path).exists())

    def test_transition_range_strength_and_readback(self):
        result = self.p.set_clip_transition(
            {
                "avatar": "Actor",
                "clip_index": 0,
                "duration_sdk_s": 0.5,
                "execute": True,
                "backup_path": self.backup,
                "strength": 80,
            }
        )
        self.assertTrue(result["executed"])
        self.assertEqual(
            self.p.inspect_clip_transition({"avatar": "Actor", "clip_index": 0})[
                "fade_in_strength"
            ],
            80,
        )

    def test_transition_invalid_values_do_not_save(self):
        for value in (-1, 100, math.inf, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.p.set_clip_transition(
                    {"avatar": "Actor", "clip_index": 0, "duration_sdk_s": value}
                )
        self.assertEqual(self.sdk.saved, [])

    def test_split_count_and_margin(self):
        with self.assertRaises(ValueError):
            self.p.split_motion_clip({"avatar": "Actor", "seconds": 2.001})
        self.p.split_motion_clip(
            {
                "avatar": "Actor",
                "seconds": 3,
                "execute": True,
                "backup_path": self.backup,
            }
        )
        self.assertEqual(self.sdk.sk.GetClipCount(), 2)

    def test_split_rejected_status_exposes_partial_warning(self):
        self.sdk.sk.BreakClip = lambda t: 0
        with self.assertRaisesRegex(RuntimeError, "Partial edit"):
            self.p.split_motion_clip(
                {
                    "avatar": "Actor",
                    "seconds": 3,
                    "execute": True,
                    "backup_path": self.backup,
                }
            )

    def test_trim_converts_scene_duration_through_speed(self):
        self.p.trim_motion_clip(
            {
                "avatar": "Actor",
                "clip_index": 0,
                "length_scene_s": 1,
                "execute": True,
                "backup_path": self.backup,
            }
        )
        self.assertEqual(self.sdk.sk.clips[0].length, 2)
        with self.assertRaises(ValueError):
            self.p.trim_motion_clip(
                {"avatar": "Actor", "clip_index": 0, "length_scene_s": 2}
            )

    def test_merge_requires_touching_adjacent_clips(self):
        self.sdk.sk.clips.append(Clip(self.sdk, 6, 1, 1))
        result = self.p.merge_motion_clips(
            {
                "avatar": "Actor",
                "first_index": 0,
                "second_index": 1,
                "execute": True,
                "backup_path": self.backup,
            }
        )
        self.assertTrue(result["executed"])
        self.assertEqual(self.sdk.sk.GetClipCount(), 1)
        self.sdk.sk.clips.append(Clip(self.sdk, 9, 1, 1))
        with self.assertRaises(ValueError):
            self.p.merge_motion_clips(
                {"avatar": "Actor", "first_index": 0, "second_index": 1}
            )

    def test_near_hold_reports_and_checks_retimed_slice(self):
        result = self.p.hold_motion_pose(
            {
                "avatar": "Actor",
                "seconds": 3,
                "duration_s": 2,
                "execute": True,
                "backup_path": self.backup,
            }
        )
        self.assertIn("not exact freeze", result["warning"])
        tail = self.sdk.sk.clips[1]
        self.assertAlmostEqual(tail.GetClipLength().tick / 6000, 2)
        self.assertEqual(tail.loops, 0)

    def test_contact_preflight_and_release_preserve_target_api(self):
        args = {
            "avatar": "Actor",
            "target_object": "GripAnchor",
            "start_s": 3,
            "end_s": 4,
        }
        self.assertEqual(self.p.plan_contact(args)["keys"][1]["key_type"], "release")
        self.assertEqual(self.sdk.edits, [])
        self.p.apply_contact_interval(dict(args, execute=True, backup_path=self.backup))
        self.assertEqual(len(self.sdk.edits), 2)

    def test_contact_conflict_refused_without_target_pointer_reads(self):
        self.sdk.reach_keys = [type("Key", (), {"GetTime": lambda self: Time(18000)})()]
        with self.assertRaisesRegex(ValueError, "Existing reach"):
            self.p.plan_contact(
                {"avatar": "Actor", "target_object": "Anchor", "start_s": 3, "end_s": 4}
            )
        self.assertEqual(self.sdk.edits, [])

    def test_mcp_dry_run_and_error_preserve_rpc_id(self):
        registry = {}
        self.p.register(registry)
        registry["set_pose_keys"]["main_thread"] = False
        handler = MCPHandler(registry)

        def call(args):
            return json.loads(
                handler(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 42,
                            "method": "tools/call",
                            "params": {"name": "set_pose_keys", "arguments": args},
                        }
                    )
                )
            )

        response = call(self.plan)
        self.assertEqual(response["id"], 42)
        self.assertFalse(
            json.loads(response["result"]["content"][0]["text"])["executed"]
        )
        self.assertTrue(call(dict(self.plan, keys=[]))["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
