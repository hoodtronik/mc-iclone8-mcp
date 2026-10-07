"""Offline tests for load_project / new_project (save-first guard and tracked-project bookkeeping) with fake RLPy.
# CLAUDE-NOTE (2026-10-07): runtime behaviour (no save prompt, 2.2 s load, handles invalidated) was measured on 8.75.5630.1;
# these only guard the wrapper logic that protects the previous project.
"""
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes, _Status  # noqa: E402


class TestProjectSession(unittest.TestCase):
    def setUp(self):
        self.scene = {"avatars": ["A"], "props": ["Shadow Catcher", "Box"], "cameras": []}
        _install_fakes([], {})
        import RLPy
        self.loaded = []
        RLPy.RFileIO = types.SimpleNamespace(LoadProject=lambda p: (self.loaded.append(p), _Status())[1])
        RLPy.RScene.GetAvatars = lambda: [types.SimpleNamespace(GetName=lambda n=n: n) for n in self.scene["avatars"]]
        RLPy.RScene.GetProps = lambda: [types.SimpleNamespace(GetName=lambda n=n: n) for n in self.scene["props"]]
        RLPy.RScene.GetCameras = lambda: [types.SimpleNamespace(GetName=lambda n=n: n) for n in self.scene["cameras"]]
        self.saves = []
        fake_project = types.ModuleType("tools.project")
        fake_project.save_project = lambda a: (self.saves.append(a["path"]), {"status": self.save_status, "path": a["path"]})[1]
        self.save_status = "ok"
        sys.modules["tools.project"] = fake_project
        from tools import common, icmcp_extra
        common._CURRENT_PROJECT.update({"path": None, "cleared": True})   # start untitled, no command-line fallback
        self.common, self.x = common, icmcp_extra
        self.x.menu_action = lambda a: (self.scene.update({"avatars": [], "props": ["Shadow Catcher"], "cameras": []}), {"ok": True, "path": a["path"]})[1]
        self.tmp = tempfile.NamedTemporaryFile(suffix=".iProject", delete=False); self.tmp.close()

    def tearDown(self):
        os.unlink(self.tmp.name)
        sys.modules.pop("tools.project", None)

    def test_load_untitled_scene_does_not_save_and_tracks_loaded_path(self):
        r = self.x.load_project({"path": self.tmp.name})
        self.assertTrue(r["ok"])
        self.assertFalse(r["saved_previous"])
        self.assertEqual(self.saves, [])
        self.assertEqual(self.loaded, [os.path.normpath(self.tmp.name)])
        self.assertEqual(self.common.current_project_path(), os.path.normpath(self.tmp.name))
        self.assertEqual(r["props"], ["Box"])   # Shadow Catcher filtered out

    def test_load_saves_tracked_project_first(self):
        self.common.set_current_project(r"G:\old.iProject")
        r = self.x.load_project({"path": self.tmp.name})
        self.assertEqual(self.saves, [r"G:\old.iProject"])
        self.assertTrue(r["saved_previous"])

    def test_failed_save_aborts_before_loading(self):
        self.common.set_current_project(r"G:\old.iProject")
        self.save_status = "failed"
        with self.assertRaises(RuntimeError):
            self.x.load_project({"path": self.tmp.name})
        self.assertEqual(self.loaded, [])

    def test_save_current_false_skips_the_save(self):
        self.common.set_current_project(r"G:\old.iProject")
        r = self.x.load_project({"path": self.tmp.name, "save_current": False})
        self.assertEqual(self.saves, [])
        self.assertEqual(r["reason"], "save_current=false")

    def test_empty_scene_is_never_saved_over_a_tracked_project(self):
        # measured 2026-10-07: a stale tracked path + empty scene overwrote the previous project
        self.common.set_current_project(r"G:\old.iProject")
        self.scene.update({"avatars": [], "props": ["Shadow Catcher"], "cameras": []})
        r = self.x.load_project({"path": self.tmp.name})
        self.assertEqual(self.saves, [])
        self.assertFalse(r["saved_previous"])
        self.assertIn("empty", r["reason"])

    def test_new_project_saves_then_clears_tracked_path(self):
        self.common.set_current_project(r"G:\old.iProject")
        r = self.x.new_project({})
        self.assertTrue(r["ok"])
        self.assertEqual(self.saves, [r"G:\old.iProject"])
        self.assertIsNone(self.common.current_project_path())
        self.assertEqual(r["avatars"], [])


if __name__ == "__main__":
    unittest.main()
