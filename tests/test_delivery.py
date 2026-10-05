import json
import struct
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from performance_support import SDK, load


def glb(document):
    raw = json.dumps(document).encode()
    raw += b" " * (-len(raw) % 4)
    return (
        struct.pack("<4sII", b"glTF", 2, 20 + len(raw))
        + struct.pack("<I4s", len(raw), b"JSON")
        + raw
    )


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.sdk = SDK()
        self.p = load("performance", self.sdk)
        self.d = load("delivery", self.sdk, self.p)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.backup = str(self.root / "backup.iProject")
        self.shot = {
            "id": "Cam",
            "start_s": 0,
            "end_s": 1,
            "position": {"x": 0, "y": -10, "z": 1},
            "target": {"x": 0, "y": 0, "z": 1},
        }
        self.extra = types.SimpleNamespace(
            _PASSES={
                "beauty": "RenderImageSequence",
                "openpose": "RenderImageSequenceOpenPoseKeyPoint",
            },
            build_shot_list=lambda args: {"ok": True, "shots": args["shots"]},
            set_render_output=self.set_config,
            render_control_pass=self.render,
        )
        import tools

        self.extra_patch = patch.object(tools, "icmcp_extra", self.extra, create=True)
        self.extra_patch.start()
        self.addCleanup(self.extra_patch.stop)
        self.qt_patch = patch.dict(__import__("sys").modules, {"PySide2": self.sdk.Qt})
        self.qt_patch.start()
        self.addCleanup(self.qt_patch.stop)
        self.render_args = {
            "camera": "Cam",
            "output_dir": str(self.root / "bundle"),
            "start_frame": 0,
            "end_frame": 2,
            "fps": 24,
            "width": 16,
            "height": 16,
            "execute": True,
            "backup_path": self.backup,
        }
        self.render_calls = []

    def set_config(self, args):
        self.sdk.config.update(args)
        return dict(self.sdk.config)

    def render(self, args):
        from PIL import Image

        self.render_calls.append(args)
        path = Path(args["output_path"])
        for i in range(args["end_frame"] - args["start_frame"] + 1):
            Image.new(
                "RGB",
                (int(self.sdk.config["width"]), int(self.sdk.config["height"])),
                (100, 20, 20),
            ).save(path.with_name(path.stem + "%04d.png" % i))
        return {"ok": True}

    def test_shot_preflight_normalizes_without_edits(self):
        result = self.d.validate_shot_list({"shots": [self.shot]})
        self.assertTrue(result["validated"])
        self.assertEqual(result["shots"][0]["near_cm"], 1)
        self.assertEqual(self.sdk.edits, [])

    def test_later_bad_shot_fails_before_builder_or_backup(self):
        bad = dict(self.shot, id="Next", start_s=1, end_s=2, focal_length_mm=-1)
        with self.assertRaises(ValueError):
            self.d.build_shot_list_verified(
                {"shots": [self.shot, bad], "execute": True, "backup_path": self.backup}
            )
        self.assertFalse(self.sdk.saved)

    def test_shot_duplicate_overlap_target_and_offframe_refused(self):
        cases = [
            [self.shot, self.shot],
            [self.shot, dict(self.shot, id="Next", start_s=0.5)],
            [dict(self.shot, end_s=0.9)],
            [dict(self.shot, target=self.shot["position"])],
        ]
        for shots in cases:
            with self.subTest(shots=shots), self.assertRaises(ValueError):
                self.d.validate_shot_list({"shots": shots})

    def test_builder_defaults_preserve_switch_keys(self):
        observed = []
        self.extra.build_shot_list = lambda args: (
            observed.append(args) or {"ok": True, "shots": args["shots"]}
        )
        self.d.build_shot_list_verified(
            {"shots": [self.shot], "execute": True, "backup_path": self.backup}
        )
        self.assertFalse(observed[0]["clear_switch_keys"])

    def test_face_schedule_explicit_times_without_playhead_changes(self):
        self.sdk.tick = 444
        args = {
            "avatar": "Actor",
            "beats": [
                {"seconds": 1, "expressions": {"Smile": 80}},
                {"seconds": 2, "expressions": {"Frown": 20}},
            ],
            "execute": True,
            "backup_path": self.backup,
        }
        self.d.schedule_face_performance(args)
        self.assertEqual([e[1] for e in self.sdk.edits], [6000, 12000])
        self.assertFalse(self.sdk.face.editing)
        self.assertEqual(self.sdk.tick, 444)

    def test_invalid_later_expression_or_missing_clip_cannot_write(self):
        args = {
            "avatar": "Actor",
            "beats": [
                {"seconds": 1, "expressions": {"Smile": 20}},
                {"seconds": 2, "expressions": {"Typo": 20}},
            ],
            "execute": True,
            "backup_path": self.backup,
        }
        with self.assertRaises(ValueError):
            self.d.schedule_face_performance(args)
        args["beats"].pop()
        self.sdk.face.GetClipByTime = lambda t: None
        with self.assertRaises(ValueError):
            self.d.schedule_face_performance(args)
        self.assertEqual(self.sdk.edits, [])
        self.assertEqual(self.sdk.saved, [])

    def test_face_failure_ends_edit_session(self):
        self.sdk.face.fail = True
        with self.assertRaises(RuntimeError):
            self.d.schedule_face_performance(
                {
                    "avatar": "Actor",
                    "beats": [{"seconds": 1, "expressions": {"Smile": 20}}],
                    "execute": True,
                    "backup_path": self.backup,
                }
            )
        self.assertFalse(self.sdk.face.editing)

    def test_bundle_writes_manifest_with_counts_hashes_and_mapping(self):
        self.sdk.tick = 3333
        self.d.export_previz_bundle(self.render_args)
        manifest = json.loads((self.root / "bundle/manifest.json").read_text())
        self.assertEqual(len(manifest["passes"]["beauty"]), 3)
        self.assertEqual(manifest["passes"]["openpose"][2]["project_frame"], 2)
        self.assertEqual(len(manifest["passes"]["beauty"][0]["sha256"]), 64)
        self.assertEqual(self.sdk.config, {"fps": 24, "width": 32, "height": 32})
        self.assertEqual(self.sdk.tick, 3333)
        self.assertIs(self.sdk.active_camera, self.sdk.camera)
        self.assertTrue(
            all(not a["normalize"] and a["depth_raw_png"] for a in self.render_calls)
        )

    def test_bundle_dry_run_creates_no_files_or_backup(self):
        result = self.d.export_previz_bundle(dict(self.render_args, execute=False))
        self.assertFalse(result["executed"])
        self.assertFalse((self.root / "bundle").exists())
        self.assertEqual(self.sdk.saved, [])

    def test_bundle_mismatch_fails_and_restores_state(self):
        original = self.extra.render_control_pass

        def short(args):
            result = original(args)
            if args["pass"] == "openpose":
                Path(args["output_path"]).with_name("openpose0002.png").unlink()
            return result

        self.extra.render_control_pass = short
        self.sdk.tick = 321
        with self.assertRaisesRegex(RuntimeError, "frame count"):
            self.d.export_previz_bundle(self.render_args)
        self.assertEqual(self.sdk.tick, 321)
        self.assertEqual(self.sdk.config["width"], 32)
        self.assertFalse((self.root / "bundle/manifest.json").exists())

    def test_existing_output_and_mismatched_fps_refused(self):
        with self.assertRaises(ValueError):
            self.d.export_previz_bundle(dict(self.render_args, fps=30))
        (self.root / "bundle").mkdir()
        with self.assertRaises(ValueError):
            self.d.export_previz_bundle(self.render_args)
        self.assertEqual(self.sdk.saved, [])

    def test_render_camera_restored_after_error(self):
        old = object()
        self.sdk.active_camera = old
        self.extra.render_control_pass = lambda args: {"ok": False}
        with self.assertRaises(RuntimeError):
            self.d.export_previz_bundle(self.render_args)
        self.assertIs(self.sdk.active_camera, old)
        self.assertEqual(self.sdk.config["width"], 32)

    def test_glb_structural_inspection_and_external_resource_reporting(self):
        path = self.root / "test.glb"
        path.write_bytes(
            glb(
                {
                    "asset": {"version": "2.0"},
                    "nodes": [{}],
                    "animations": [{"name": "Walk"}],
                    "images": [{"uri": "external.png"}],
                }
            )
        )
        result = self.d.inspect_glb({"path": str(path)})
        self.assertTrue(result["structural_header_valid"])
        self.assertEqual(result["animation_names"], ["Walk"])
        self.assertEqual(result["external_resources"], ["external.png"])

    def test_glb_bad_header_and_truncated_chunk_refused(self):
        path = self.root / "test.glb"
        for raw in (
            b"bad",
            glb({"asset": {"version": "2.0"}})[:-1],
            struct.pack("<4sII", b"glTF", 2, 24)
            + struct.pack("<I4s", 100, b"JSON")
            + b"bad!",
        ):
            path.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.d.inspect_glb({"path": str(path)})

    def test_export_requires_explicit_constraint_attestation(self):
        with self.assertRaisesRegex(ValueError, "Bake constraints"):
            self.d.export_animation_package(
                {"avatar": "Actor", "path": str(self.root / "actor.glb")}
            )
        self.assertEqual(self.sdk.saved, [])

    def test_export_verifies_file_and_writes_manifest(self):
        def export(args):
            Path(args["path"]).write_bytes(
                glb({"asset": {"version": "2.0"}, "animations": [{"name": "Pose"}]})
            )
            return {"status": "ok"}

        import tools

        with patch.object(
            tools, "project", types.SimpleNamespace(export_glb=export), create=True
        ):
            self.d.export_animation_package(
                {
                    "avatar": "Actor",
                    "path": str(self.root / "actor.glb"),
                    "constraints_prebaked": True,
                    "execute": True,
                    "backup_path": self.backup,
                }
            )
        manifest = json.loads((self.root / "actor.glb.manifest.json").read_text())
        self.assertEqual(manifest["glb_inspection"]["animation_names"], ["Pose"])
        self.assertIn("not verified", manifest["constraints_prebaked"])

    def test_export_sdk_success_without_file_fails(self):
        import tools

        with patch.object(
            tools,
            "project",
            types.SimpleNamespace(export_glb=lambda args: {"status": "ok"}),
            create=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "nonempty"):
                self.d.export_animation_package(
                    {
                        "avatar": "Actor",
                        "path": str(self.root / "actor.glb"),
                        "constraints_prebaked": True,
                        "execute": True,
                        "backup_path": self.backup,
                    }
                )


if __name__ == "__main__":
    unittest.main()
