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


def test_hands_lights_and_focus_are_checked():
    spec = {"length_s": 10,
            "walkers": [{"name": "W", "avatar": "x", "from": [0, 0], "to": [100, 0],
                         "hands": [{"pose": "fist", "at_s": 1, "until_s": 4}, {"pose": "point", "at_s": 3, "until_s": 5},
                                   {"pose": "wave", "hand": "l"}]}],
            "lights": [{"kind": "lamp"}, {"kind": "point"}],
            "shots": [{"id": "A", "start_s": 0, "end_s": 5, "position": [0, -300, 160], "target": [0, 0, 150],
                       "focus": {"look": "blurry", "keys": [{"at_s": 7, "target": "Ghost"}]}}]}
    e = " | ".join(_errors(spec))
    for want in ("overlaps hands[0]", "pose 'wave'", "kind must be spot", "lights[1] None: needs `position`",
                 "focus.look", "focus target 'Ghost'", "focus key at_s 7"):
        assert want in e, want


def test_crowds_expand_into_cast_facing_the_focus():
    import math
    import build_scene as B
    spec = {"length_s": 10, "crowds": [{"name": "Aud", "count": 7, "formation": "rows", "at": [0, 300],
                                        "focus": [0, 0], "avatars": ["a", "b"], "clips": ["Clap"]}]}
    out = B.expand_crowds(spec)
    assert "crowds" in spec and "crowds" not in out                # input untouched
    cast = out["cast"]
    assert [m["name"] for m in cast][:2] == ["Aud01", "Aud02"] and len(cast) == 7
    assert cast[1]["avatar"] == "b" and cast[0]["motion"]["clip"] == "Clap"
    for m in cast:
        x, y, _ = m["place"]["at"]
        want = B.face_turn(x, y, (0, 0))
        assert abs((m["place"]["turn"] - want + 180) % 360 - 180) <= 8.0   # jitter <= 8 deg
    # the first row is the one nearest the focus
    near = min(cast, key=lambda m: math.hypot(*m["place"]["at"][:2]))
    assert cast.index(near) < 4


def test_face_turn_matches_the_turn_convention():
    import build_scene as B
    assert abs(B.face_turn(0, 0, (0, -100))) < 1e-9               # look -Y: turn 0
    assert abs(B.face_turn(0, 0, (100, 0)) - 90) < 1e-9           # look +X: turn 90 (CCW from above)


def test_arc_rings_the_performer_and_scatter_keeps_spacing():
    import math
    import build_scene as B
    pts = B.formation_points("arc", 5, (0, 0), radius=200)
    assert all(abs(math.hypot(x, y) - 200) < 1e-6 for x, y in pts) and all(y > 0 for x, y in pts)
    sc = B.formation_points("scatter", 6, (0, 0), size=[500, 300], spacing=100, seed=3)
    assert all(math.hypot(a[0] - b[0], a[1] - b[1]) >= 100 for i, a in enumerate(sc) for b in sc[i + 1:])
    assert all(abs(x) <= 250 and abs(y) <= 150 for x, y in sc)


def test_pose_entries_are_checked():
    spec = {"length_s": 10, "walkers": [{"name": "W", "avatar": "x", "from": [0, 0], "to": [100, 0],
                                         "laugh": [{"at_s": 1}],
                                         "pose": [{"bones": {"head": {"yaw": 30}}, "at_s": 1, "until_s": 3},
                                                  {"bones": {"head": {"pitch": 5}, "tail": {"yaw": 1}}, "at_s": 4},
                                                  {"bones": {"chest": {"twist": 3}}, "at_s": 5}]}]}
    e = " | ".join(_errors(spec))
    for want in ("bone 'tail'", "takes {yaw, pitch, roll}", "move the same bone", "the laugh would wipe the pose"):
        assert want in e, want
