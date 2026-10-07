"""Offline tests for convert_external_motion's guards and helpers (the dialog flow itself was measured on 8.75.5630.1)."""
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes  # noqa: E402


class TestConvertExternalMotion(unittest.TestCase):
    def setUp(self):
        _install_fakes([], {})
        sys.modules["dispatch"] = types.SimpleNamespace(run=lambda fn: fn())
        from tools import icmcp_extra
        self.x = icmcp_extra

    def tearDown(self):
        sys.modules.pop("dispatch", None)

    def test_missing_source_is_rejected_before_touching_iclone(self):
        with self.assertRaises(FileNotFoundError):
            self.x.convert_external_motion({"path": r"C:\nope\missing.fbx"})

    def test_new_files_only_reports_motion_files_added_after_snapshot(self):
        d = tempfile.mkdtemp()
        open(os.path.join(d, "old.rlMotion"), "w").close()
        before = set(os.listdir(d))
        open(os.path.join(d, "new.rlMotion"), "w").close(); open(os.path.join(d, "note.txt"), "w").close()
        self.assertEqual(self.x._new_files(d, before), ["new.rlMotion"])
        self.assertEqual(self.x._new_files(r"C:\nope\dir", set()), [])

    def test_tool_is_registered_off_the_main_thread(self):
        reg = {}
        self.x.register(reg)
        self.assertFalse(reg["convert_external_motion"]["main_thread"])
        self.assertTrue(reg["set_look_at"]["main_thread"])


if __name__ == "__main__":
    unittest.main()
