import math

from tools import seating as S


def _qz(deg):
    h = math.radians(deg) / 2
    return (0.0, 0.0, math.sin(h), math.cos(h))


def _qx(deg):
    h = math.radians(deg) / 2
    return (math.sin(h), 0.0, 0.0, math.cos(h))


def _close(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_qrot_matches_rotation_about_z():
    assert _close(S.qrot(_qz(90), (1.0, 0.0, 0.0)), (0.0, 1.0, 0.0))


def test_compose_matches_live_convention():
    # child.T == parent.T + parent.R * child.local.T (verified live on CC bones, 10-16)
    parent = ((10.0, 0.0, 50.0), _qz(90))
    T, Q = S.compose(parent, ((0.0, 5.0, 0.0), _qz(90)))
    assert _close(T, (5.0, 0.0, 50.0))
    assert _close(S.qrot(Q, (1.0, 0.0, 0.0)), (-1.0, 0.0, 0.0))


def _bind_skeleton():
    """Standing legs along -Z, every bone frame = identity; the skeleton faces -Y."""
    ident = (0.0, 0.0, 0.0, 1.0)
    pos = {"CC_Base_Hip": (0, 0, 95), "CC_Base_Waist": (0, 0, 105), "CC_Base_Pelvis": (0, 0, 95),
           "CC_Base_L_Thigh": (10, 0, 88), "CC_Base_L_Calf": (10, 0, 48), "CC_Base_L_Foot": (10, 0, 9),
           "CC_Base_L_ToeBase": (10, -12, 2), "CC_Base_R_Thigh": (-10, 0, 88), "CC_Base_R_Calf": (-10, 0, 48),
           "CC_Base_R_Foot": (-10, 0, 9), "CC_Base_R_ToeBase": (-10, -12, 2)}
    return {k: (tuple(float(c) for c in v), ident) for k, v in pos.items()}


def test_identity_pose_reproduces_bind_vertices():
    bind = _bind_skeleton()
    verts = [(10.0, 8.0, 70.0), (-10.0, -6.0, 30.0), (10.0, -12.0, 0.0), (0.0, 10.0, 90.0)]
    bound = S.bind_lower_body(verts, bind)
    surf = S.posed_surface(bound, bind)
    got = sorted(p for role in surf.values() for p in role)
    assert all(_close(a, b) for a, b in zip(got, sorted(verts)))


def test_hands_and_upper_body_are_excluded():
    bind = _bind_skeleton()
    bound = S.bind_lower_body([(40.0, 0.0, 85.0), (0.0, 0.0, 140.0)], bind)
    assert bound == []


def test_seated_thigh_moves_its_underside_down_to_the_seat():
    bind = _bind_skeleton()
    # back-of-thigh vertex half way down the left thigh, 7 cm behind the bone
    verts = [(10.0, 7.0, 68.0)]
    bound = S.bind_lower_body(verts, bind)
    posed = dict(bind)
    # sit: thigh rotated -90 deg about X so it points forward (-Y); hip joint now at z=50
    q = _qx(-90)
    posed["CC_Base_L_Thigh"] = ((10.0, 0.0, 50.0), q)
    posed["CC_Base_Pelvis"] = ((0.0, 7.0, 57.0), bind["CC_Base_Pelvis"][1])
    p = S.posed_surface(bound, posed)["seat"][0]
    assert abs(p[1] - (-20.0)) < 1e-6            # 20 cm forward along the thigh
    assert abs(p[2] - 43.0) < 1e-6               # 7 cm below the thigh axis


def test_plan_fit_rests_on_seat_and_reports_authored_height():
    r = S.plan_fit([40.0, 41.0, 40.5], [5.0, 5.2, 4.8], seat_top=46.0)
    assert r["dz_cm"] == 5.5 and r["seat_gap_after_cm"] == 0.0
    assert r["authored_seat_height_cm"] == 35.5
    assert r["sole_z_after"] == 10.5 and "advice" in r


def test_plan_fit_feet_mode_and_no_advice_when_matched():
    r = S.plan_fit([46.0], [0.5], seat_top=46.0, mode="feet")
    assert r["mode_used"] == "feet" and r["dz_cm"] == -0.5 and "advice" not in r


def test_seat_contact_prefers_points_over_the_seat():
    pts = [(0, 0, 30.0), (100, 0, 20.0)]
    assert S.seat_contact(pts, (-50, 50, -20, 20)) == (0, 0, 30.0)
    assert S.seat_contact(pts) == (100, 0, 20.0)
