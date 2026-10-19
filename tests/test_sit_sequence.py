import pytest

from tools.sit_sequence import body_of, plan_clips, lift_keys


def test_body_from_stock_names():
    assert body_of("Casual_F_0019") == "F" and body_of("Business_M_0001") == "M"
    assert body_of("Anyone", "F") == "F"
    with pytest.raises(ValueError):
        body_of("Maureen_Callahan")


def test_plan_sits_idles_and_stands():
    lens = {"stand_to_sit": 140, "idle": 300, "sit_to_stand": 120}
    plan = plan_clips(30, 600, 900, lens)
    assert plan[0] == ("stand_idle", 0, 30)
    assert plan[1] == ("stand_to_sit", 30, 140)
    assert plan[2] == ("idle", 170, 300) and plan[3] == ("idle", 470, 130)     # second copy trimmed to the stand
    assert plan[4] == ("sit_to_stand", 600, 120) and plan[5] == ("stand_idle", 720, 180)


def test_plan_without_standing_up_idles_to_the_end():
    lens = {"stand_to_sit": 140, "idle": 300, "sit_to_stand": 120}
    plan = plan_clips(0, None, 400, lens)
    assert plan[0] == ("stand_to_sit", 0, 140) and plan[-1] == ("idle", 140, 260)


def test_lift_keys_only_while_seated():
    assert lift_keys(10, 40, 100, 130, 5.0) == [(0, 0.0), (10, 0.0), (40, 5.0), (100, 5.0), (130, 0.0)]
    assert lift_keys(10, 40, None, None, -3.0)[-1] == (40, -3.0)


def test_spec_sit_is_checked():
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import spec_check
    spec = {"length_s": 12, "set": [{"name": "Chair", "size": [50, 50, 45], "at": [0, 0]}],
            "cast": [{"name": "A", "avatar": "x", "sit": {"seat": "Chair", "sit_at_s": 1, "stand_at_s": 8}},
                     {"name": "B", "avatar": "x", "sit": {"seat": "Sofa", "sit_at_s": 1, "stand_at_s": 3}}]}
    errs, _ = spec_check.check(spec, ".")
    e = " | ".join(errs)
    assert "A:" not in e and "cast A" not in e
    assert "Sofa" in e and "stand_at_s" in e


def test_front_shift_clears_the_standing_hip_but_keeps_the_seat():
    from tools.sit_sequence import front_shift
    # facing axis: seat front edge at 23 (seat centre 0, 46 deep); standing hip only 5 past the edge
    assert front_shift([30, 28], contact=0, front=23) == 7.0
    # already clear: no shift
    assert front_shift([40, 45], contact=0, front=23) == 0.0
    # capped: contact may only move to 15 (8 cm inside the edge)
    assert front_shift([20], contact=10, front=23) == 5.0
