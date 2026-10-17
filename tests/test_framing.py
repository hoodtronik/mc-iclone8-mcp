import math

from tools import framing as F

ASPECT = 16 / 9


def test_project_centre_and_horizontal_aov():
    pos, aim = (0.0, -500.0, 100.0), (0.0, 0.0, 100.0)
    assert F.project((0.0, 0.0, 100.0), pos, aim, 35.0, ASPECT) == (0.0, 0.0)
    # 35 mm on 36 mm film = 54.43 deg horizontal AOV (measured in iClone): a point on the AOV edge projects to x = 1
    half = math.radians(54.432 / 2)
    x, y = F.project((500.0 * math.tan(half), 0.0, 100.0), pos, aim, 35.0, ASPECT)
    assert abs(x - 1.0) < 1e-3 and abs(y) < 1e-9
    assert F.project((0.0, -600.0, 100.0), pos, aim, 35.0, ASPECT) is None      # behind the camera


def _person(x=0.0):
    return {"head_top": (x, 0.0, 178.0), "sole": (x, 0.0, 0.0), "waist": (x, 0.0, 100.0), "l_sh": (x + 20, 0.0, 145.0),
            "r_sh": (x - 20, 0.0, 145.0)}


def _bounds(pos, aim, pts, lens=35.0):
    v = [F.project(p, pos, aim, lens, ASPECT) for p in pts]
    return min(p[1] for p in v), max(p[1] for p in v), min(p[0] for p in v), max(p[0] for p in v)


def test_full_shot_puts_head_and_feet_at_the_margins():
    p = _person()
    pos, aim, rep = F.solve_framing([p["head_top"]], [p["sole"]], list(p.values()), (0.0, 1.0, 0.0), 160.0,
                                    (0.0, 0.0, 0.0), 35.0, ASPECT, 0.86, 0.07)
    ymin, ymax, _, _ = _bounds(pos, aim, [p["head_top"], p["sole"]])
    assert abs(ymax - 0.86) < 0.01 and abs(ymin + 0.86) < 0.01
    assert pos[1] < -100 and abs(pos[0]) < 1e-6 and pos[2] == 160.0


def test_medium_cuts_at_the_waist_with_headroom():
    p = _person()
    pos, aim, _ = F.solve_framing([p["head_top"]], [p["waist"]], list(p.values()), (0.0, 1.0, 0.0), 160.0,
                                  (0.0, 0.0, 0.0), 35.0, ASPECT, 1.0, 0.07)
    ymin, ymax, _, _ = _bounds(pos, aim, [p["head_top"], p["waist"]])
    assert abs(ymax - 0.86) < 0.01 and abs(ymin + 1.14) < 0.02


def test_two_people_far_apart_widen_the_shot_and_fit_horizontally():
    a, b = _person(-250.0), _person(250.0)
    pts = list(a.values()) + list(b.values())
    pos, aim, rep = F.solve_framing([a["head_top"], b["head_top"]], [a["waist"], b["waist"]], pts, (0.0, 1.0, 0.0),
                                    160.0, (0.0, 0.0, 0.0), 35.0, ASPECT, 1.0, 0.07)
    _, _, xmin, xmax = _bounds(pos, aim, pts)
    assert rep["widened_to_fit"] and xmin >= -0.93 and xmax <= 0.93


def test_left_third_placement():
    p = _person()
    pos, aim, _ = F.solve_framing([p["head_top"]], [p["waist"]], list(p.values()), (0.0, 1.0, 0.0), 160.0,
                                  (0.0, 0.0, 0.0), 50.0, ASPECT, 1.0, 0.07, h_place=-1.0 / 3.0)
    _, _, xmin, xmax = _bounds(pos, aim, list(p.values()), 50.0)
    assert abs((xmin + xmax) / 2 + 1.0 / 3.0) < 0.02


def test_keep_point_stays_above_the_limit():
    p = _person()
    chin = (0.0, 0.0, 140.0)          # bowed head: the chin hangs below the collar cut line
    pos, aim, rep = F.solve_framing([p["head_top"]], [(0.0, 0.0, 150.0)], [p["head_top"], chin], (0.0, 1.0, 0.0), 160.0,
                                    (0.0, 0.0, 0.0), 50.0, ASPECT, 1.0, 0.03, keep_pts=[chin], keep_ymin=-0.75)
    assert F.project(chin, pos, aim, 50.0, ASPECT)[1] >= -0.76 and rep["widened_to_fit"]


def test_smooth_keeps_ends_and_averages_middle():
    pts = [(0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (0.0, 0.0, 0.0)]
    out = F.smooth(pts)
    assert out[1] == (1.0, 0.0, 0.0) and out[0] == (1.5, 0.0, 0.0) and len(out) == 3


def test_occluded_by_person_on_the_sight_line_or_camera_inside_someone():
    cam, tgt = (0.0, -500.0, 150.0), (0.0, 0.0, 150.0)
    assert F.occluded(cam, tgt, [(10.0, -250.0)])            # stands in the line
    assert not F.occluded(cam, tgt, [(120.0, -250.0)])       # beside it
    assert not F.occluded(cam, tgt, [(0.0, 50.0)])           # behind the subject
    assert F.occluded(cam, tgt, [(20.0, -510.0)])            # camera inside a person


def test_blocked_3d_sight_line():
    cam, face = (0.0, -300.0, 120.0), (0.0, 0.0, 120.0)
    assert F.blocked(cam, [face], [(5.0, -150.0, 118.0)])
    assert not F.blocked(cam, [face], [(60.0, -150.0, 118.0)])
    assert not F.blocked(cam, [face], [(0.0, -150.0, 60.0)])       # below the sight line (a chest far under)


def test_blocked_when_camera_is_in_a_bystanders_face():
    assert F.blocked((0.0, -300.0, 120.0), [(0.0, 0.0, 120.0)], [(300.0, -280.0, 120.0), (30.0, -310.0, 125.0)])


def test_far_apart_mixed_heights_stay_sane():
    # a seated and a standing person 4.9 m apart at different depths (EveningStreet two-shot that diverged)
    a = {"head_top": (35.0, 145.0, 120.0), "knee": (35.0, 120.0, 50.0), "l_sh": (55.0, 145.0, 100.0), "r_sh": (15.0, 145.0, 100.0)}
    b = {"head_top": (-436.0, -7.0, 180.0), "knee": (-436.0, -7.0, 50.0), "l_sh": (-416.0, -7.0, 150.0), "r_sh": (-456.0, -7.0, 150.0)}
    pts = list(a.values()) + list(b.values())
    pos, aim, rep = F.solve_framing([a["head_top"], b["head_top"]], [a["knee"], b["knee"]], pts, (0.3, 0.95, 0.0), 140.0,
                                    (-200.0, 70.0, 0.0), 35.0, ASPECT, 1.0, 0.07)
    assert rep["distance_cm"] < 3000 and 0.0 < aim[2] < 250.0
    _, _, xmin, xmax = _bounds(pos, aim, pts, 35.0)
    assert xmin >= -1.0 and xmax <= 1.0
