"""Offline test for edit_clip with a fake skeleton component (routing, index validation, before/after proof).
# CLAUDE-NOTE (2026-10-07): the real effects (break/merge/mirror/delete, world-X mirroring) were measured on 8.75.5630.1.
"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes, _Status  # noqa: E402


class _Clip:
    def __init__(self, start, end): self.start, self.end = start, end
    def ClipTimeToSceneTime(self, t): return ("t", self.start)
    def GetClipLength(self): return ("t", self.end - self.start)
    def GetSpeed(self): return 1.0


class _Skel:
    def __init__(self): self.clips, self.calls, self.mirrored = [_Clip(0, 760)], [], False
    def GetClipCount(self): return len(self.clips)
    def GetClip(self, i): return self.clips[i]
    def BreakClip(self, t):
        self.calls.append(("break", t[1])); c = self.clips[0]; self.clips = [_Clip(c.start, t[1]), _Clip(t[1], c.end)]; return _Status()
    def MergeClips(self, a, b):
        self.calls.append(("merge",)); self.clips = [_Clip(a.start, b.end)]; return _Status()
    def MirrorClip(self, c):
        self.calls.append(("mirror",)); self.mirrored = True; return _Status()
    def DeleteClip(self, c):
        self.calls.append(("delete",)); self.clips.remove(c); return _Status()
    def GetSkinBones(self):
        x = -149.0 if not self.mirrored else 149.0
        return [types.SimpleNamespace(GetName=lambda: "CC_Base_Hip", WorldTransform=lambda: types.SimpleNamespace(T=lambda: types.SimpleNamespace(x=x, y=0.0, z=60.0)))]


class TestEditClip(unittest.TestCase):
    def setUp(self):
        self.sk = _Skel()
        av = types.SimpleNamespace(GetName=lambda: "A", GetSkeletonComponent=lambda: self.sk)
        _install_fakes([av], {})
        import RLPy
        RLPy.RTime = types.SimpleNamespace(FromValue=lambda v: ("t", v))
        RLPy.RGlobal.GetFps = lambda: types.SimpleNamespace(IndexedFrameTime=lambda n: ("t", n), GetFrameIndex=lambda t: t[1])
        from tools import icmcp_extra
        self.tool = icmcp_extra.edit_clip

    def test_break_then_merge_round_trip(self):
        r = self.tool({"avatar": "A", "op": "break", "frame": 60})
        self.assertTrue(r["ok"])
        self.assertEqual([(c["start_frame"], c["end_frame"]) for c in r["clips_after"]], [(0, 60), (60, 760)])
        r = self.tool({"avatar": "A", "op": "merge", "clip": 0})
        self.assertEqual([(c["start_frame"], c["end_frame"]) for c in r["clips_after"]], [(0, 760)])

    def test_merge_needs_two_adjacent_clips(self):
        with self.assertRaises(ValueError):
            self.tool({"avatar": "A", "op": "merge", "clip": 0})

    def test_mirror_reports_pose_change_as_proof(self):
        r = self.tool({"avatar": "A", "op": "mirror", "clip": 0})
        self.assertTrue(r["ok"] and r["changed"])
        self.assertEqual(r["pose_before"]["Hip"][0], -149.0)
        self.assertEqual(r["pose_after"]["Hip"][0], 149.0)

    def test_delete_empties_track_and_bad_index_rejected(self):
        self.assertEqual(self.tool({"avatar": "A", "op": "delete", "clip": 0})["clips_after"], [])
        with self.assertRaises(ValueError):
            self.tool({"avatar": "A", "op": "delete", "clip": 0})


if __name__ == "__main__":
    unittest.main()
