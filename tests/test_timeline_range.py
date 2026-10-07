"""Offline test for set_timeline_range with a fake RGlobal that mimics the measured clamping (length clamps end/preview_end).
# CLAUDE-NOTE (2026-10-07): the clamp rules come from a runtime probe on 8.75.5630.1; this guards unit conversion, ordering,
# and the read-back/mismatch report.
"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes, _Status  # noqa: E402


class TestSetTimelineRange(unittest.TestCase):
    def setUp(self):
        _install_fakes([], {})
        import RLPy
        self.v = {"project_length": 1800, "start": 0, "end": 1800, "preview_start": 0, "preview_end": 1800, "current": 0}
        fps = types.SimpleNamespace(IndexedFrameTime=lambda n: ("t", n), GetFrameIndex=lambda t: t[1], ToFloat=lambda: 60.0)

        def setter(key):
            def _set(t):
                self.v[key] = t[1]
                if key == "project_length":
                    for k in ("end", "preview_end"):
                        self.v[k] = min(self.v[k], t[1])
                    self.v["current"] = min(self.v["current"], t[1])
                return _Status()
            return _set
        G = types.SimpleNamespace(GetFps=lambda: fps, GetTime=lambda: ("t", self.v["current"]), SetTime=lambda t: None)
        for key, getter, set_name in (("project_length", "GetProjectLength", "SetProjectLength"), ("start", "GetStartTime", "SetStartTime"),
                                      ("end", "GetEndTime", "SetEndTime"), ("preview_start", "GetPreviewStartTime", "SetPreviewStartTime"),
                                      ("preview_end", "GetPreviewEndTime", "SetPreviewEndTime")):
            setattr(G, getter, (lambda k=key: ("t", self.v[k])))
            setattr(G, set_name, setter(key))
        RLPy.RGlobal = G
        from tools import icmcp_extra
        self.tool = icmcp_extra.set_timeline_range

    def test_seconds_convert_at_project_fps_and_read_back(self):
        r = self.tool({"project_length": 4, "end": 2, "unit": "seconds"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["requested_frames"], {"project_length": 240, "end": 120})
        self.assertEqual(r["frames_now"]["end"], 120)
        self.assertEqual(r["frames_now"]["preview_end"], 240)   # clamped by the length change

    def test_length_applied_before_explicit_end_so_end_wins(self):
        r = self.tool({"project_length": 240, "end": 600})
        self.assertEqual(r["frames_now"]["end"], 600)
        self.assertIsNone(r["mismatch"])

    def test_mismatch_is_reported_not_hidden(self):
        import RLPy
        RLPy.RGlobal.SetStartTime = lambda t: _Status()   # silently ignores the write
        r = self.tool({"start": 30})
        self.assertFalse(r["ok"])
        self.assertEqual(r["mismatch"], {"start": {"requested": 30, "now": 0}})

    def test_nothing_requested_is_an_error(self):
        with self.assertRaises(ValueError):
            self.tool({})


if __name__ == "__main__":
    unittest.main()
