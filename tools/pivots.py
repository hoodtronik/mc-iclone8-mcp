"""Named pivot points on a bounding box (pure; used by tools.scene.set_pivot and the offline spec check)."""

PIVOT_SIDES = {"center": (0, 0, 0), "base": (0, 0, -1), "top": (0, 0, 1), "left": (-1, 0, -1), "right": (1, 0, -1),
               "front": (0, -1, -1), "back": (0, 1, -1)}


def pivot_point(lo, hi, where):
    """World point on a box [lo, hi] for a named side: x -1/0/+1 = min/mid/max ('left' = -X edge at the base,
    'front' = -Y edge at the base: a door hinge or the lip of a lid)."""
    sx, sy, sz = PIVOT_SIDES[where]
    pick = lambda a, b, s: (a + b) / 2.0 if s == 0 else (a if s < 0 else b)
    return (pick(lo[0], hi[0], sx), pick(lo[1], hi[1], sy), pick(lo[2], hi[2], sz))
