"""Offline test for path_position_key with a fake spin box whose setter creates the key (the measured iClone behaviour)."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes, _Status  # noqa: E402


class _Ctl:
    def __init__(self): self.keys = {0: 0.0}
    def GetKeyCount(self): return len(self.keys)
    def GetValue(self, t, d): return [_Status(), self.keys.get(t[1], 0.0)]


class _Spin:
    def __init__(self, world): self.world, self.editingFinished = world, types.SimpleNamespace(emit=lambda: None)
    def setValue(self, v): self.world["ctl"].keys[self.world["frame"]] = v / 100.0   # UI % -> control 0..1, keyed at current time


class TestPathPositionKey(unittest.TestCase):
    def setUp(self):
        self.world = {"ctl": _Ctl(), "frame": 0}
        self.follow_calls = []
        obj = types.SimpleNamespace(GetName=lambda: "Box", GetControl=lambda k: self.world["ctl"] if k == "PathPosition" else None,
                                    WorldTransform=lambda: types.SimpleNamespace(T=lambda: types.SimpleNamespace(x=-100.0, y=0.0, z=250.0)),
                                    FollowPath=lambda path, t: (self.follow_calls.append((path.GetName(), t[1])), _Status())[1])
        path = types.SimpleNamespace(GetName=lambda: "Circle01")
        _install_fakes([], {"Box": obj, "Circle01": path})
        import RLPy
        RLPy.RGlobal.SetTime = lambda t: self.world.__setitem__("frame", t[1])
        from tools import icmcp_extra
        self.x = icmcp_extra
        self.x._path_position_spin = lambda o: _Spin(self.world)

    def test_percent_key_created_and_read_back(self):
        r = self.x.path_position_key({"object": "Box", "percent": 50, "frame": 60})
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["keys_before"], r["keys_after"]), (1, 2))
        self.assertEqual(r["percent_now"], 50.0)
        self.assertEqual(r["position_at_frame"], [-100.0, 0.0, 250.0])

    def test_path_argument_picks_path_first(self):
        self.x.path_position_key({"object": "Box", "percent": 0, "frame": 0, "path": "Circle01"})
        self.assertEqual(self.follow_calls, [("Circle01", 0)])


if __name__ == "__main__":
    unittest.main()
