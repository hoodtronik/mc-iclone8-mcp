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
