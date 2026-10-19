from tools.clip_ops import planted_foot, seam_jump


def test_planted_foot_is_the_one_that_moves_less():
    still = [(0, 0, 10), (0.1, 0, 10), (0.2, 0, 10)]
    swing = [(0, 20, 15), (5, 20, 18), (10, 20, 16)]
    assert planted_foot(still, swing) == "left_foot"
    assert planted_foot(swing, still) == "right_foot"


def test_planted_foot_tie_goes_to_the_lower_foot():
    a = [(0, 0, 12), (0, 0, 12)]
    b = [(0, 20, 9), (0, 20, 9)]
    assert planted_foot(a, b) == "right_foot"


def test_seam_jump_is_the_largest_bone_step():
    before = {"hip": (0, 0, 90), "l": (0, 0, 10)}
    at = {"hip": (3, 4, 90), "l": (0, 0, 10)}
    assert seam_jump(before, at) == 5.0
