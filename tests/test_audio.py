"""Offline tests for load_audio / render_audio with a fake RAudio/RenderAudio that writes real wav files.
# CLAUDE-NOTE (2026-10-07): measured on 8.75.5630.1 — LoadAudioToObject's float return was identical for a missing file,
# so the wrapper proves the load by comparing rendered windows; these tests guard that logic.
"""
import os
import struct
import sys
import tempfile
import types
import unittest
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes, _Status  # noqa: E402


def _write_wav(path, amplitude, seconds=1.0, rate=8000):
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
    w.writeframes(struct.pack("<%dh" % int(rate * seconds), *([amplitude] * int(rate * seconds)))); w.close()


class TestAudio(unittest.TestCase):
    def setUp(self):
        self.track = {"loaded": False}

        class _Prop:
            def GetName(self): return "Box"

        class _Camera:
            def GetName(self): return "Cam"
        _install_fakes([], {"Box": _Prop(), "Cam": _Camera()})
        import RLPy
        RLPy.RIProp, RLPy.RICamera = _Prop, _Camera
        RLPy.RAudio = types.SimpleNamespace(LoadAudioToObject=lambda *a: (self.track.update({"loaded": True}), 5.572)[1])

        def render(start, end, path):
            _write_wav(path, 3000 if self.track["loaded"] else 0)
            return _Status()
        RLPy.RGlobal.RenderAudio = render
        from tools import icmcp_extra
        self.x = icmcp_extra
        self.src = tempfile.NamedTemporaryFile(suffix=".wav", delete=False); self.src.close(); _write_wav(self.src.name, 100)
        self.out = os.path.join(tempfile.gettempdir(), "icmcp_test_render.wav")

    def tearDown(self):
        for f in (self.src.name, self.out):
            if os.path.exists(f):
                os.remove(f)

    def test_render_audio_reports_silence_stats(self):
        r = self.x.render_audio({"start_frame": 0, "end_frame": 60, "output_path": self.out})
        self.assertTrue(r["ok"])
        self.assertEqual(r["peak"], 0)
        self.assertEqual(r["seconds"], 1.0)

    def test_render_audio_rejects_equal_range(self):
        with self.assertRaises(ValueError):
            self.x.render_audio({"start_frame": 5, "end_frame": 5, "output_path": self.out})

    def test_load_audio_proves_change_by_rendering(self):
        r = self.x.load_audio({"object": "Box", "path": self.src.name, "frame": 0})
        self.assertTrue(r["ok"] and r["audio_changed"])
        self.assertEqual((r["window_peak_before"], r["window_peak_after"]), (0, 3000))
        self.assertEqual(r["reported_seconds"], 5.572)

    def test_load_audio_missing_file_is_rejected_before_calling_iclone(self):
        with self.assertRaises(FileNotFoundError):
            self.x.load_audio({"object": "Box", "path": r"C:\nope\missing.wav"})
        self.assertFalse(self.track["loaded"])

    def test_load_audio_refuses_cameras_before_calling_iclone(self):
        # measured 2026-10-07: LoadAudioToObject on a camera crashed iClone 8.75 twice
        with self.assertRaises(ValueError):
            self.x.load_audio({"object": "Cam", "path": self.src.name})
        self.assertFalse(self.track["loaded"])

    def test_load_audio_unverified_trusts_nothing_but_reports(self):
        r = self.x.load_audio({"object": "Box", "path": self.src.name, "verify": False})
        self.assertTrue(r["ok"])
        self.assertIsNone(r["audio_changed"])


if __name__ == "__main__":
    unittest.main()
