"""Offline test for walk_to with a fake avatar that reproduces the measured iClone behaviour: a root-motion clip travels
from the latest STEP transform key, holds its last pose after its natural length, restarts at the transform when another
clip is loaded, and its distance is sub-linear in clip speed.
# CLAUDE-NOTE (2026-10-07): all of that was measured on 8.75.5630.1; this guards geometry, calibration, chaining, trimming
# and the proof logic.
"""
import math
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes, _Status  # noqa: E402

NATIVE, NATURAL_S, FPS = 76.0, 5.35, 60.0


class _Tf:
    def __init__(self, s=None, r=None, t=None): self._s, self._r, self._t = s, r, t
    def S(self): return self._s
    def R(self): return self._r
    def T(self): return self._t


class _T(tuple):
    def ToInt(self): return self[1]


class _Ctrl:
    def __init__(self, world): self.keys, self.world, self.transitions = {}, world, []
    def GetKeyCount(self): return len(self.keys)
    def GetValue(self, t, tf): tf._t = types.SimpleNamespace(x=self.world["x"], y=self.world["y"], z=0.0); tf._s = "S"; return _Status()
    def SetValue(self, t, tf): self.keys[t[1]] = (tf.T().x, tf.T().y); return _Status()
    def SetKeyTransition(self, t, kind, strength): self.transitions.append((t[1], kind)); return _Status()
    def key_at(self, f):
        ks = [k for k in self.keys if k <= f]
        return self.keys[max(ks)] if ks else (self.world["x"], self.world["y"])


class _Clip:
    def __init__(self, start): self.start, self.speed, self.length_s = start, 1.0, NATURAL_S
    def GetClipLength(self): return _T(("t", int(NATURAL_S / self.speed * 6000)))   # scene seconds (measured)
    def ClipTimeToSceneTime(self, t): return ("t", self.start)
    def GetSpeed(self): return self.speed
    def SetSpeed(self, v): self.speed = v; return _Status()
    def SetLength(self, t): self.length_s = t[1] / 6000.0 / self.speed; return _Status()   # scene seconds


class _Skel:
    def __init__(self, world, ctrl): self.clips, self.world, self.ctrl, self.now = [], world, ctrl, 0
    def GetClipCount(self): return len(self.clips)
    def GetClip(self, i): return self.clips[i]
    def GetClipByTime(self, t): return max((c for c in self.clips if c.start <= t[1]), key=lambda c: c.start, default=None)
    def DeleteClip(self, c): self.clips.remove(c); return _Status()
    def GetSkinBones(self):
        f = self.now; c = self.GetClipByTime(("t", f))
        x, y = self.ctrl.key_at(f)
        if c is not None and not getattr(c, "idle", False):
            t = min((f - c.start) / FPS, min(c.length_s, NATURAL_S / c.speed))
            d = NATIVE * (c.speed ** 0.8) * t          # mildly sub-linear in speed, harsher than measured (~linear)
            h = math.radians(self.world["heading"]); x, y = x + d * math.sin(h), y - d * math.cos(h)
        return [types.SimpleNamespace(GetName=lambda: "CC_Base_Hip", WorldTransform=lambda: types.SimpleNamespace(T=lambda: types.SimpleNamespace(x=x, y=y, z=93.0)))]


class TestWalkTo(unittest.TestCase):
    def setUp(self):
        self.world = {"x": 0.0, "y": 0.0, "heading": 0.0}
        self.ctrl = _Ctrl(self.world); self.sk = _Skel(self.world, self.ctrl)
        av = types.SimpleNamespace(GetName=lambda: "A", GetSkeletonComponent=lambda: self.sk, GetControl=lambda k: self.ctrl)
        _install_fakes([av], {})
        import RLPy
        RLPy.RGlobal.GetFps = lambda: types.SimpleNamespace(IndexedFrameTime=lambda n: ("t", n), GetFrameIndex=lambda t: t[1], ToFloat=lambda: FPS)
        RLPy.RGlobal.SetTime = lambda t: setattr(self.sk, "now", t[1])
        RLPy.RTransform = _Tf
        RLPy.RVector3 = lambda x, y, z: types.SimpleNamespace(x=x, y=y, z=z)
        RLPy.RTime = types.SimpleNamespace(FromValue=lambda v: ("t", v))
        RLPy.ETransitionType_Step = "STEP"
        def load_motion(p, t, av):
            c = _Clip(t[1]); c.idle = p.endswith(".idle"); self.sk.clips.append(c)   # the idle fake is in-place
        RLPy.RFileIO = types.SimpleNamespace(LoadMotion=load_motion)
        RLPy.RMatrix3 = lambda: types.SimpleNamespace(FromEulerAngle=lambda order, x, y, z: [("m", math.degrees(z))])
        RLPy.EEulerOrder_XYZ = 0
        world = self.world

        class _Q:
            def FromRotationMatrix(self, m): world["heading"] = m[1]
        RLPy.RQuaternion = _Q
        fake_fight = types.ModuleType("tools.fight_tools"); fake_fight._delete_all_clips = lambda sk: [sk.DeleteClip(c) for c in list(sk.clips)]
        sys.modules["tools.fight_tools"] = fake_fight
        from tools import icmcp_extra
        self.x = icmcp_extra
        RLPy.RGlobal.GetProjectLength = lambda: ("t", 1800)
        self.motion = tempfile.NamedTemporaryFile(suffix=".iMotion", delete=False); self.motion.close()
        self.idle = tempfile.NamedTemporaryFile(suffix=".idle", delete=False); self.idle.close()

    def tearDown(self):
        os.unlink(self.motion.name); os.unlink(self.idle.name); sys.modules.pop("tools.fight_tools", None)

    def test_idle_after_parks_avatar_until_project_end(self):
        r = self.x.walk_to({"avatar": "A", "to": {"x": 200, "y": 0}, "motion": self.motion.name, "idle_motion": self.idle.name})
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["idle"]["hold_frames"], 1800 - (r["end_frame"] + 1))
        self.assertLess(r["idle"]["hip_drift_cm"], 1.0)
        self.assertEqual(self.sk.clips[-1].start, r["end_frame"] + 1)

    def test_idle_after_false_adds_no_clip(self):
        r = self.x.walk_to({"avatar": "A", "to": {"x": 200, "y": 0}, "motion": self.motion.name, "idle_after": False})
        self.assertIsNone(r["idle"])
        self.assertEqual(len(self.sk.clips), r["clips_used"])

    def test_short_walk_single_clip_trimmed(self):
        r = self.x.walk_to({"avatar": "A", "to": {"x": 200, "y": 0}, "motion": self.motion.name})
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["heading_deg"], 90.0)
        self.assertEqual(r["clips_used"], 1)
        self.assertLess(r["hip_error_cm"], 5.0)
        self.assertEqual(r["end_frame"], round(200 / NATIVE * FPS))
        self.assertIn((0, "STEP"), self.ctrl.transitions)
        self.assertIn(r["end_frame"] + 1, self.ctrl.keys)

    def test_long_walk_chains_clips_with_boundary_keys(self):
        r = self.x.walk_to({"avatar": "A", "to": {"x": 0, "y": -1000}, "motion": self.motion.name})
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["clips_used"], 3)                                   # 406 + 406 + trimmed
        boundary = round(NATURAL_S * FPS)
        self.assertIn(boundary, self.ctrl.keys)
        self.assertAlmostEqual(self.ctrl.keys[boundary][1], -NATIVE * NATURAL_S, places=0)
        self.assertLess(r["hip_error_cm"], 5.0)

    def test_pace_request_calibrates_sublinear_speed(self):
        r = self.x.walk_to({"avatar": "A", "to": {"x": 0, "y": -300}, "speed_cm_s": 152, "motion": self.motion.name})
        self.assertTrue(r["ok"], r)
        self.assertGreater(r["clip_speed"], 1.9)                               # 2x pace needs >2x clip speed under the fake's law
        self.assertLess(abs(r["duration_s"] - 300 / 152), 0.25)

    def test_duration_request(self):
        r = self.x.walk_to({"avatar": "A", "to": {"x": 100, "y": 100}, "duration_s": 1.0, "motion": self.motion.name})
        self.assertEqual(r["heading_deg"], 135.0)
        self.assertLess(abs(r["duration_s"] - 1.0), 0.25)

    def test_frame0_rule_writes_hold_key_when_track_empty(self):
        self.x.walk_to({"avatar": "A", "to": {"x": 100, "y": 0}, "start_frame": 30, "motion": self.motion.name})
        self.assertIn(0, self.ctrl.keys)
        self.assertEqual(self.ctrl.keys[0], self.ctrl.keys[30])

    def test_zero_distance_rejected(self):
        with self.assertRaises(ValueError):
            self.x.walk_to({"avatar": "A", "to": {"x": 0, "y": 0}, "motion": self.motion.name})


if __name__ == "__main__":
    unittest.main()
