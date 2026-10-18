"""Offline tests for scripts/spec_check.py (name references, times, gaits; no stock files needed)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import spec_check  # noqa: E402


def _errors(spec):
    return spec_check.check(spec, ".")[0]


def test_dangling_names_and_times_are_reported():
    spec = {"length_s": 10,
            "set": [{"name": "Bench", "size": [100, 40, 45], "at": [0, 0]}],
            "paths": [{"name": "P", "points": [[0, 0], [100, 0]]}],
            "walkers": [{"name": "W", "avatar": "x", "path": "Q", "imd": "female_jog", "actions": []}],
            "shots": [{"id": "A", "start_s": 0, "end_s": 12, "frame": {"subjects": ["Nobody"], "size": "mid"}}]}
    e = " | ".join(_errors(spec))
    for want in ("path 'Q' is not in `paths`", "imd 'female_jog' unknown", "walkers have no `actions`",
                 "end_s 12.0 is past length_s 10.0", "subject 'Nobody'", "size 'mid'"):
        assert want in e, want


def test_unknown_top_level_key_gets_a_suggestion():
    warn = spec_check.check({"length_s": 5, "shot": []}, ".")[1]
    assert any("'shot'" in w and "'shots'" in w for w in warn)


def test_did_you_mean_offers_close_stems(monkeypatch):
    monkeypatch.setitem(spec_check._CACHE, "motion", {"HD Idle 01_F": "1.Acting/HD Idle 01_F.iMotionPlus"})
    assert "HD Idle 01_F" in spec_check.did_you_mean("motion", "HD Idle_F")


def test_reel_page_lists_the_edit_and_each_shot():
    import reel
    page = reel._page({"name": "Cafe"}, [{"id": "Barista", "start_s": 3, "end_s": 6, "prompt": "",
                                          "passes_video": "Barista_passes.mp4", "passes": ["beauty", "depth"],
                                          "poster": "Barista.jpg"}])
    assert "edit.mp4" in page and "Barista_passes.mp4" in page and "playsinline" in page
