"""Measure every stock avatar once and write examples/catalog/avatars.json: what a scene spec can cast.

  python scripts/avatar_catalog.py                 # opens a scratch project (discards the open scene's unsaved work)
  python scripts/avatar_catalog.py --limit 6       # quick check

Per avatar: spec path (relative to the avatar root, extension optional), gender/age read from the file name, height and
hip height, whether it has the CC skeleton that fit_sitter / Motion Director need, and how many seat/sole vertices the
seat fitter finds. Each group of avatars is also rendered as a lineup (front view) under the scratch folder so a person
or agent can look at them; the hand-written `look` field (outfit, age) is kept when the catalog is regenerated.
# CLAUDE-NOTE (2026-10-17): written after a Sonnet trial agent had no way to choose people by age/gender/outfit (stock
# avatars ship without thumbnails; names like Casual_M_0055 say nothing).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from icall import call  # noqa: E402
from build_scene import PUBLIC, ROOTS, ok, py  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "examples", "catalog", "avatars.json")
SCRATCH_DIR = os.path.join(os.path.expanduser("~"), "Documents", "Reallusion", "_scratch", "AvatarCatalog")
GROUP = 6
SPACING_CM = 110.0

MEASURE = r'''
import RLPy
from tools.seating import _find_avatar, _bind_data, bind_lower_body, bind_mismatch
av = _find_avatar(%(name)r)
mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
av.GetBounds(mx, c, mn)
r = {"height_cm": round(mx.z - mn.z, 1), "meshes": len(av.GetMeshes())}
try:
    bones, bind, verts = _bind_data(av)
    roles = [role for role, _ in bind_lower_body(verts, bind)]
    r.update(cc_skeleton=True, hip_height_cm=round(bind["CC_Base_Hip"][0][2], 1),
             seat_vertices=roles.count("seat"), sole_vertices=roles.count("sole"))
    bad = bind_mismatch(verts, bind) or (None if r["seat_vertices"] and r["sole_vertices"] else "no seat/sole surface")
    r["seat_fit"] = "ok" if not bad else "no: " + bad
except Exception as e:
    r.update(cc_skeleton=False, error=str(e)[:160])
_result = r
'''


def find_avatars():
    out = []
    for root in ROOTS["avatar"]:
        for d, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".iavatar"):
                    out.append((root, os.path.join(d, f)))
    return sorted(out, key=lambda rp: rp[1].lower())


def from_name(fname):
    n = os.path.basename(fname)
    g = "F" if re.search(r"(?i)_F_|female|katherine|jody", n) else ("M" if re.search(r"(?i)_M_|male|kevin|walter", n) else "?")
    age = "child" if re.search(r"(?i)kid", n) else "adult"          # _E0001 is NOT elderly (looked at the renders)
    return g, age


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    found = find_avatars()[: a.limit or None]
    print(f"{len(found)} avatars")
    old = {}
    if os.path.isfile(OUT):
        with open(OUT, encoding="utf-8") as fh:
            old = {r["spec"]: r for r in json.load(fh).get("avatars", [])}
    os.makedirs(SCRATCH_DIR, exist_ok=True)
    rows = []
    for gi in range(0, len(found), GROUP):
        group = found[gi:gi + GROUP]
        py("import RLPy\nRLPy.RFileIO.LoadFile(RLPy.RApplication.GetDefaultProjectPath())", silent=True)
        ok(call("save_project", {"path": os.path.join(SCRATCH_DIR, "AvatarCatalog.iProject")}), "save scratch")
        names = []
        for i, (root, path) in enumerate(group):
            spec = os.path.relpath(path, root).replace("\\", "/")
            py("import RLPy\nRLPy.RScene.ClearSelectObjects()")          # a selected avatar would be REPLACED
            r = call("load_object", {"path": path})
            if r.get("status") != "ok":
                rows.append({"spec": spec, "error": f"load failed: {json.dumps(r)[:160]}"})
                names.append(None)
                continue
            name = r["name"]
            names.append(name)
            ok(call("place_object", {"name": name, "frame": 0, "position": {"x": i * SPACING_CM, "y": 0, "z": 0}}), "place")
            g, age = from_name(path)
            row = {"spec": spec, "gender": g, "age": age, "loads_as": name,
                   "lineup": f"lineup_{gi // GROUP + 1:02d}.png #{i + 1} from left"}
            try:
                row.update(py(MEASURE % {"name": name}))
            except Exception as e:                                      # keep going; record why
                row["error"] = str(e)[:200]
            for k in ("gender", "age", "kind", "look"):                 # hand-written from the lineup renders
                if spec in old and old[spec].get(k):
                    row[k] = old[spec][k]
            rows.append(row)
            print(f"  {spec:45s} {row.get('height_cm', '?'):>6} cm  cc={row.get('cc_skeleton')}  "
                  f"seat={row.get('seat_vertices')} sole={row.get('sole_vertices')} fit={row.get('seat_fit')}")
        mid = (len(group) - 1) * SPACING_CM / 2.0
        ok(call("aim_camera", {"name": "_lineup", "position": {"x": mid, "y": -260 - 75 * len(group), "z": 110},
                               "target": {"x": mid, "y": 0, "z": 95}, "focal_length_mm": 35, "make_current": True,
                               "hold": True}), "camera")
        shot = os.path.join(SCRATCH_DIR, f"lineup_{gi // GROUP + 1:02d}.png")
        ok(call("render_snapshot", {"output_path": shot, "frame": 0}), "lineup render")
        print(f"  lineup -> {shot}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"about": "Stock avatars for scene specs (cast[].avatar / walkers[].avatar / wander people): `spec` is "
                            "the path to use (extension optional). gender/age come from the file name; `look` is "
                            "hand-written from the lineup renders. cc_skeleton=false: no fit_sitter / Motion Director. "
                            "Measured by scripts/avatar_catalog.py.", "avatars": rows}, f, indent=1)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
