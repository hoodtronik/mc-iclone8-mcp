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


def test_looks_are_checked():
    spec = {"length_s": 10, "set": [{"name": "Door", "size": [1, 1, 1], "at": [0, 0]}],
            "shots": [{"id": "Close", "start_s": 0, "end_s": 5, "position": [0, 0, 0], "target": [1, 0, 0]}],
            "cast": [{"name": "A", "avatar": "x", "looks": [{"target": "Close", "at_s": 1, "until_s": 3},
                                                            {"target": "Door", "at_s": 2},
                                                            {"target": "Nobody", "at_s": 5},
                                                            {"target": "A", "at_s": 6, "until_s": 6}]}]}
    e = " | ".join(_errors(spec))
    for want in ("overlaps the previous look", "'Nobody' is not a person", "cannot look at itself", "until_s must be after"):
        assert want in e, want
    assert "looks[0]" not in e


def test_set_moves_are_checked_and_planned():
    from build_scene import move_keys
    item = {"name": "Cart", "size": [50, 80, 90], "at": [0, 0], "turn": 10,
            "moves": [{"start_s": 2, "end_s": 4, "to": [300, 0]}, {"start_s": 4, "end_s": 5, "turn": 100}]}
    assert move_keys(item, 30) == [(0, 0, 0, 0.0, 10.0), (60, 0, 0, 0.0, 10.0), (120, 300, 0, 0.0, 10.0),
                                   (150, 300, 0, 0.0, 100.0)]
    bad = {"length_s": 6, "set": [{"name": "Cart", "size": [1, 1, 1], "at": [0, 0],
                                   "moves": [{"start_s": 2, "end_s": 4, "to": [1, 1]}, {"start_s": 3, "end_s": 7, "to": [2, 2]},
                                             {"start_s": 5, "end_s": 5.5, "transition": "bounce"}]}]}
    e = " | ".join(_errors(bad))
    for want in ("end_s <= length_s", "give at least one of", "transition must be"):
        assert want in e, want


def test_pins_are_checked():
    spec = {"length_s": 8, "cast": [{"name": "A", "avatar": "x", "pins": [
        {"effector": "left_foot", "at_s": 1, "until_s": 4}, {"effector": "left_foot", "at_s": 3, "until_s": 5},
        {"effector": "head", "at_s": 1, "until_s": 2}, {"effector": "right_foot", "at_s": 6, "until_s": 9}]}],
            "walkers": [{"name": "W", "avatar": "x", "from": [0, 0], "to": [1, 0], "pins": [{"at_s": 1, "until_s": 2}]}]}
    e = " | ".join(_errors(spec))
    for want in ("overlaps another pin on left_foot", "head cannot be pinned", "until_s <= length_s", "walkers have no `pins`"):
        assert want in e, want


def test_path_shots_are_checked():
    spec = {"length_s": 10, "cast": [{"name": "A", "avatar": "x"}], "shots": [
        {"id": "Ok", "start_s": 0, "end_s": 3, "path": {"orbit": {"center": [0, 0], "radius": 300}, "target": "A"}},
        {"id": "Both", "start_s": 3, "end_s": 5, "frame": {"subjects": ["A"]},
         "path": {"points": [[0, 0, 1], [1, 1, 1]], "orbit": {"center": [0, 0], "radius": 1}, "target": "Nobody"}},
        {"id": "Short", "start_s": 5, "end_s": 7, "path": {"points": [[0, 0, 1]], "target": [0, 0, 100], "timing": "fast"}}]}
    e = " | ".join(_errors(spec))
    for want in ("`frame` OR `path`", "points` [[x,y,z], ...] (2+) OR", "'Nobody' is not a person", "2+ [x, y, z] points",
                 "timing must be ease or linear"):
        assert want in e, want
    assert "'Ok'" not in e


def test_lighting_time_lapse_is_checked():
    spec = {"length_s": 10, "lighting": [{"preset": "golden_hour", "at_s": 0}, {"preset": "dusk", "at_s": 6},
                                         {"preset": "sunrise", "at_s": 8}, {"preset": "night", "at_s": 6},
                                         {"preset": "night", "at_s": 12}]}
    e = " | ".join(_errors(spec))
    for want in ("'sunrise' must be one of", "two lighting beats at 6", "at_s within 0..length_s"):
        assert want in e, want
    assert "lighting[0]" not in e and "lighting[1]" not in e
    assert _errors({"length_s": 5, "lighting": {"preset": "dusk"}}) == []


def test_atmosphere_is_checked(monkeypatch):
    import tools.lighting as L

    def fake(name, roots=None):
        if name != "IBL Mist":
            raise ValueError("no atmosphere 'x'; close: ['IBL Mist']")
        return "IBL Mist.iAtm"
    monkeypatch.setattr(L, "find_atmosphere", fake)
    e = " | ".join(_errors({"length_s": 5, "atmosphere": {"preset": "Misty", "fog": {"start": 500, "end": 100}},
                            "lighting": {"preset": "dusk"}}))
    for want in ("close: ['IBL Mist']", "`lighting` cannot follow it", "end must be beyond start"):
        assert want in e, want
    assert _errors({"length_s": 5, "atmosphere": "IBL Mist"}) == []


def test_weather_is_checked(monkeypatch):
    import tools.weather as W

    def fake(kind, env_dir=None):
        if kind not in ("rain", "snow"):
            raise ValueError("no weather 'hail'; kinds ['blizzard', 'rain', 'snow']")
        return kind
    monkeypatch.setattr(W, "weather_file", fake)
    e = " | ".join(_errors({"length_s": 6, "weather": [{"kind": "hail"}, {"kind": "rain", "start_s": 4, "stop_s": 2}]}))
    assert "no weather 'hail'" in e and "start_s < stop_s" in e
    assert _errors({"length_s": 6, "weather": [{"kind": "snow", "start_s": 1}]}) == []


def test_set_pivot_is_checked():
    spec = {"length_s": 5, "set": [
        {"name": "Gate", "size": [100, 5, 120], "at": [0, 0], "pivot": "left", "moves": [{"start_s": 1, "end_s": 2, "turn": 80}]},
        {"name": "Lid", "size": [50, 50, 5], "at": [0, 0], "pivot": "hinge"},
        {"name": "Cart", "size": [50, 50, 50], "at": [0, 0], "pivot": [0, 0, 0], "moves": [{"start_s": 1, "end_s": 2, "to": [100, 0]}]}]}
    errs, warns = spec_check.check(spec, ".")
    e = " | ".join(errs)
    assert "'Lid'" in e and "pivot must be" in e and "'Gate'" not in e
    assert any("where the PIVOT goes" in w for w in warns)
