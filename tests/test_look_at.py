"""Offline test for tools.icmcp_extra.set_look_at with a fake RLPy/PySide2 (overload selection + head-rotation readback).
# CLAUDE-NOTE (2026-10-07): the real call shapes were measured on iClone 8.75.5630.1; this only guards the wrapper's routing.
"""
import math
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _V:
    def __init__(self, x, y, z, w=0.0): self.x, self.y, self.z, self.w = x, y, z, w


class _Status:
    def IsError(self): return False


class _Bone:
    def __init__(self, name, q): self._n, self._q = name, q
    def GetName(self): return self._n
    def WorldTransform(self): return types.SimpleNamespace(R=lambda: self._q, T=lambda: _V(0, 0, 0))


class _LookAt:
    def __init__(self, world): self.calls, self.world = [], world
    def AddLookAtKey(self, *args):
        self.calls.append(args)
        self.world["turned"] = args[-1] is not None if len(args) == 2 else True
        return _Status()


class _Skel:
    def __init__(self, world, la=None): self.world, self.la = world, la
    def GetSkinBones(self):
        q = _V(0.0, 0.0, math.sin(math.radians(20)), math.cos(math.radians(20))) if self.world.get("turned") else _V(0, 0, 0, 1)
        return [_Bone("CC_Base_Hip", _V(0, 0, 0, 1)), _Bone("CC_Base_Head", q)]
    def GetRootBone(self): return self.GetSkinBones()[0]
    def GetLookAtComponent(self): return self.la


class _Avatar:
    def __init__(self, name, skel): self._n, self._s = name, skel
    def GetName(self): return self._n
    def GetSkeletonComponent(self): return self._s


class _Prop:
    def GetName(self): return "Box"


def _install_fakes(avatars, objects):
    rl = types.ModuleType("RLPy")
    fps = types.SimpleNamespace(IndexedFrameTime=lambda n: ("t", n))
    rl.RGlobal = types.SimpleNamespace(GetFps=lambda: fps, SetTime=lambda t: None, GetTime=lambda: ("t", 0))
    rl.RScene = types.SimpleNamespace(GetAvatars=lambda: avatars, GetCurrentCamera=lambda: None,
                                      FindObject=lambda typ, name: objects.get(name))
    for n in ("EObjectType_Avatar", "EObjectType_Prop", "EObjectType_Camera", "EObjectType_Light", "EObjectType_Particle",
              "EObjectType_SpotLight", "EObjectType_PointLight", "EObjectType_DirectionalLight"):
        setattr(rl, n, n)
    rl.RIAvatar = _Avatar
    sys.modules["RLPy"] = rl
    qt = types.ModuleType("PySide2"); qtw = types.ModuleType("PySide2.QtWidgets")
    qtw.QApplication = types.SimpleNamespace(processEvents=lambda: None)
    qt.QtWidgets = qtw
    sys.modules["PySide2"], sys.modules["PySide2.QtWidgets"] = qt, qtw
    for m in [k for k in sys.modules if k.startswith("tools")]:
        del sys.modules[m]


class TestSetLookAt(unittest.TestCase):
    def setUp(self):
        self.world = {"turned": False}
        self.la = _LookAt(self.world)
        self.me = _Avatar("Me", _Skel(self.world, self.la))
        self.other = _Avatar("Other", _Skel({"turned": True}))
        _install_fakes([self.me, self.other], {"Box": _Prop(), "Other": self.other})
        from tools import icmcp_extra
        self.tool = icmcp_extra.set_look_at

    def test_object_target_uses_two_arg_overload_and_reads_back_turn(self):
        r = self.tool({"avatar": "Me", "target": "Box", "frame": 10})
        self.assertEqual(len(self.la.calls[0]), 2)
        self.assertEqual(r["mode"], "object")
        self.assertTrue(r["ok"] and r["head_moved"])
        self.assertAlmostEqual(r["head_turn_deg"]["10"], 40.0, places=0)

    def test_avatar_target_defaults_to_head_bone_five_arg_overload(self):
        r = self.tool({"avatar": "Me", "target": "Other", "frame": 0, "transition_frames": 12, "head_weight": 1.0, "body_weight": 0.0})
        call = self.la.calls[0]
        self.assertEqual(len(call), 5)
        self.assertEqual(call[1], ("t", 12))
        self.assertEqual(call[2].GetName(), "CC_Base_Head")
        self.assertEqual(call[3:], (1.0, 0.0))
        self.assertEqual(r["bone"], "CC_Base_Head")

    def test_bone_on_prop_is_rejected(self):
        with self.assertRaises(ValueError):
            self.tool({"avatar": "Me", "target": "Box", "bone": "CC_Base_Head"})

    def test_release_passes_none_and_reports_no_motion(self):
        r = self.tool({"avatar": "Me", "release": True, "frame": 5})
        self.assertEqual(self.la.calls[0], (("t", 5), None))
        self.assertEqual(r["mode"], "release")
        self.assertTrue(r["ok"])
        self.assertFalse(r["head_moved"])
        self.assertIn("unchanged", r["note"])


if __name__ == "__main__":
    unittest.main()
