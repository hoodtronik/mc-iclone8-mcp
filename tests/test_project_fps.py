"""Offline test for set_project_fps with a fake Project dock + QComboBox (Qt-tier wrapper; readback via fake RGlobal).
# CLAUDE-NOTE (2026-10-07): the real panel/combo (objectName qtFpsComboBox, choices 12/24/25/30/60/120) was measured on
# 8.75.5630.1; this guards choice validation, readback-based ok, and panel visibility restore.
"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes  # noqa: E402


class _Combo:
    def __init__(self, world): self.items, self.idx, self.world = ["12", "24", "25", "30", "60", "120"], 4, world
    def count(self): return len(self.items)
    def itemText(self, i): return self.items[i]
    def findText(self, t): return self.items.index(t) if t in self.items else -1
    def setCurrentIndex(self, i): self.idx = i
    @property
    def activated(self):
        def emit(i): self.world["fps"] = float(self.items[i])
        return types.SimpleNamespace(emit=emit)


class _Dock:
    def __init__(self, world): self.visible, self.combo = False, _Combo(world)
    def isVisible(self): return self.visible
    def show(self): self.visible = True
    def hide(self): self.visible = False
    def findChild(self, cls, name): return self.combo if name == "qtFpsComboBox" else None


class TestSetProjectFps(unittest.TestCase):
    def setUp(self):
        _install_fakes([], {})
        import RLPy
        self.world = {"fps": 60.0, "length_s": 30.0}
        fps = types.SimpleNamespace(ToFloat=lambda: self.world["fps"], GetFrameIndex=lambda t: int(t[1] * self.world["fps"]))
        RLPy.RGlobal.GetFps = lambda: fps
        RLPy.RGlobal.GetProjectLength = lambda: ("s", self.world["length_s"])
        sys.modules["PySide2.QtWidgets"].QComboBox = object
        sys.modules["PySide2.QtWidgets"].QDockWidget = object
        from tools import icmcp_extra
        self.x = icmcp_extra
        self.dock = _Dock(self.world)
        self.x._project_dock = lambda: self.dock

    def test_sets_24_reads_back_and_hides_panel_again(self):
        r = self.x.set_project_fps({"fps": 24})
        self.assertTrue(r["ok"])
        self.assertEqual((r["fps_before"], r["fps_now"]), (60.0, 24.0))
        self.assertEqual((r["project_length_frames_before"], r["project_length_frames_now"]), (1800, 720))
        self.assertFalse(self.dock.isVisible())

    def test_rejects_unoffered_rate(self):
        with self.assertRaises(ValueError):
            self.x.set_project_fps({"fps": 48})

    def test_leaves_panel_open_if_it_was_open(self):
        self.dock.visible = True
        self.x.set_project_fps({"fps": 30})
        self.assertTrue(self.dock.isVisible())


if __name__ == "__main__":
    unittest.main()
