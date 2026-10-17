"""Measure every stock SITTING clip once and write examples/catalog/sit_clips.json: the seat height each clip was authored
for, so a scene can pick a seat height (or a clip) that keeps the body on the seat AND the feet on the floor.

  python scripts/sit_catalog.py                    # opens a scratch project (discards the open scene's unsaved work)
  python scripts/sit_catalog.py --limit 5          # quick check

Per clip: loads it on a stock male or female (by the clip's M/F tag), runs fit_sitter (measure only, no seat) over the
clip and records authored_seat_height_cm, its ratio to the avatar's hip height (to scale for other bodies), how much
the seated contact moves during the clip, and whether the feet stay on the floor.
# CLAUDE-NOTE (2026-10-16): built after the park bench showed two stock "Sit Talk" clips wanting seats 10 cm apart
# (male ~33 cm, female ~43 cm): seat height is a property of the CLIP, so measure it once and look it up.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from icall import call  # noqa: E402
from build_scene import PUBLIC, ok, py  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "examples", "catalog", "sit_clips.json")
SCRATCH = os.path.join(os.path.expanduser("~"), "Documents", "Reallusion", "_scratch", "SitCatalog", "SitCatalog.iProject")
AVATARS = {"M": "Business/Business_M_0001.iAvatar", "F": "Business/Business_F_0004.iAvatar"}
SEARCH = [os.path.join(PUBLIC, "Reallusion Templates", "Animation"),
          os.path.join(PUBLIC, "Template", "iClone 7 Template", "iClone Template", "MographMotion")]
EXTS = (".rlmotion", ".imotion", ".imotionplus")
SKIP = re.compile(r"(?i)_to_|to sit|to stand|sit drop|child|_C\.")      # transitions / parkour / child bodies


def find_clips():
    out = []
    for root in SEARCH:
        for d, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith(EXTS) and "sit" in f.lower() and not SKIP.search(os.path.join(d, f)):
                    out.append(os.path.join(d, f))
    return sorted(out)


def gender(path):
    p = path.replace("\\", "/")
    if re.search(r"(?i)female|_F\d?\.|_F_|/2\.Human Female/", p):
        return "F"
    return "M"


MEASURE = r'''
import RLPy
from tools.common import load_motion_clip
from tools.seating import fit_sitter, _bind_data, _find_avatar
av = _find_avatar(%(name)r)
clip = load_motion_clip(av, %(path)r, RLPy.RTime.FromValue(0))
fps = RLPy.RGlobal.GetFps()
n = fps.GetFrameIndex(clip.GetClipLength())
r = fit_sitter({"avatar": %(name)r, "apply": False, "start_frame": 0, "end_frame": max(2, n - 1), "samples": 16})
_, bind, _ = _bind_data(av)
r["hip_height_cm"] = round(bind["CC_Base_Hip"][0][2], 1)
r["clip_frames"] = n
_result = r
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    clips = find_clips()[: a.limit or None]
    print(f"{len(clips)} sit clips")
    py("import RLPy\nRLPy.RFileIO.LoadFile(RLPy.RApplication.GetDefaultProjectPath())", silent=True)
    ok(call("set_timeline_range", {"project_length": 120, "start": 0, "end": 120, "unit": "seconds"}), "length")
    os.makedirs(os.path.dirname(SCRATCH), exist_ok=True)
    ok(call("save_project", {"path": SCRATCH}), "save scratch")        # checkpoints must never hit another project
    names = {}
    for g, rel in AVATARS.items():
        py("import RLPy\nRLPy.RScene.ClearSelectObjects()")             # a selected avatar would be REPLACED
        r = call("load_object", {"path": os.path.join(PUBLIC, "Reallusion Templates", "Actor", "Character", rel)})
        if r.get("status") != "ok":
            raise SystemExit(f"load avatar {rel}: {r}")
        names[g] = r["name"]
    rows = []
    for path in clips:
        g = gender(path)
        rel = os.path.relpath(path, PUBLIC).replace("\\", "/")
        try:
            r = py(MEASURE % {"name": names[g], "path": path})
        except Exception as e:                                          # keep going; record why
            rows.append({"clip": rel, "error": str(e)[:200]})
            print(f"  ERR {rel}: {str(e)[:120]}")
            continue
        h = r["authored_seat_height_cm"]
        c0, c1 = r["contact_z_now"]
        s0, s1 = r["sole_z_now"]
        row = {"clip": rel, "body": g, "avatar": AVATARS[g], "authored_seat_height_cm": h,
               "seat_ratio_to_hip": round(h / r["hip_height_cm"], 3), "contact_motion_cm": round(c1 - c0, 1),
               "feet_lift_cm": round(s1 - s0, 1), "seconds": round(r["clip_frames"] / 30.0, 1)}
        rows.append(row)
        print(f"  {h:5.1f} cm  ratio {row['seat_ratio_to_hip']:.3f}  moves {row['contact_motion_cm']:4.1f}  {rel}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"about": "Seat height each stock sit clip expects (feet on floor). Scale for another body: "
                            "seat = seat_ratio_to_hip * that avatar's hip height. Measured by scripts/sit_catalog.py "
                            "with fit_sitter.", "clips": rows}, f, indent=1)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
