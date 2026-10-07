"""Offline test for camera_cuts: key writing, Switch mode, readback and the live-camera check (measured on 8.75.5630.1)."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes, _Status  # noqa: E402


class _Cam:
    def __init__(self, n): self.n = n
    def GetName(self): return self.n


class TestCameraCuts(unittest.TestCase):
    def setUp(self):
        self.a, self.b = _Cam("A"), _Cam("B")
        self.track, self.now, self.mode = [], 0, "A"
        _install_fakes([], {"A": self.a, "B": self.b, "Box": types.SimpleNamespace(GetName=lambda: "Box")})
        import RLPy
        RLPy.RICamera = _Cam
        fps = types.SimpleNamespace(IndexedFrameTime=lambda n: ("t", n), GetFrameIndex=lambda t: t[1])
        RLPy.RGlobal.GetFps = lambda: fps
        RLPy.RGlobal.GetEndTime = lambda: ("t", 300)
        RLPy.RGlobal.SetTime = lambda t: setattr(self, "now", t[1])

        def live():
            if self.mode != "Switch" or not self.track:
                return self.a
            return [c for f, c in sorted(self.track, key=lambda r: r[0]) if f <= self.now][-1]
        RLPy.RScene.ClearSwitchCameraKeys = lambda: (self.track.clear(), _Status())[1]
        RLPy.RScene.AddSwitchCameraKey = lambda t, cam: (self.track.append((t[1], cam)), _Status())[1]
        RLPy.RScene.GetSwitchCameraFrameIndexs = lambda f: [(c, fr) for fr, c in self.track]
        RLPy.RScene.GetCurrentCamera = live
        from tools import icmcp_extra
        self.x = icmcp_extra
        self.x._set_camera_mode = lambda name: (setattr(self, "mode", name), name)[1]

    def test_cuts_written_switch_mode_on_and_live_camera_checked(self):
        r = self.x.camera_cuts({"cuts": [{"frame": 90, "camera": "B"}, {"frame": 0, "camera": "A"}]})
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["camera_mode"], "Switch")
        self.assertEqual(r["switch_cuts"], [{"frame": 0, "camera": "A"}, {"frame": 90, "camera": "B"}])
        self.assertEqual([l["live"] for l in r["live_check"]], ["A", "B"])

    def test_without_switch_mode_live_check_is_not_enforced(self):
        r = self.x.camera_cuts({"cuts": [{"frame": 0, "camera": "A"}, {"frame": 90, "camera": "B"}], "switch_mode": False})
        self.assertTrue(r["ok"], r)
        self.assertIsNone(r["camera_mode"])

    def test_non_camera_rejected(self):
        with self.assertRaises(ValueError):
            self.x.camera_cuts({"cuts": [{"frame": 0, "camera": "Box"}]})


if __name__ == "__main__":
    unittest.main()
