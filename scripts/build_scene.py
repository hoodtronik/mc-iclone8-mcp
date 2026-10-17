"""Build an iClone scene from a declarative JSON spec, stage by stage, verifying each stage. Made for agents: write a
spec (see examples/scenes/*.json and docs/SCENE_SPEC.md), run this, read the summary. Stdlib only; talks to the running
mc-iclone8-mcp server (scripts/icall.py).

  python scripts/build_scene.py examples/scenes/park_bench.json              # everything (discards the open scene!)
  python scripts/build_scene.py spec.json --stages cast,walks,qa             # selected stages on the open scene
  python scripts/build_scene.py spec.json --previz                           # + per-shot AI-video packages (slow)

Stages (in order): project, set, paths, cast, walks, dialog, sky, camera, qa. Each prints what it did and fails loudly
with the tool's own error. The final 'qa' stage runs motion_qa over the whole shot and saves a filmstrip.
# CLAUDE-NOTE (2026-10-16): encodes the rules learned building the park-bench scene: save the new project to its own
# path first (checkpoints save in place), clear the selection before loading avatars, set colours at frame 0, chain
# looping clips at end+1, give Motion Director a camera that sees the path. A weaker agent should only edit JSON.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from icall import call  # noqa: E402

PUBLIC = os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Documents", "Reallusion")
ROOTS = {
    "avatar": [os.path.join(PUBLIC, "Reallusion Templates", "Actor", "Character"),
               os.path.join(PUBLIC, "Template", "iClone 7 Template", "iClone Template", "Character")],
    "motion": [os.path.join(PUBLIC, "Reallusion Templates", "Animation", "Motion"),
               os.path.join(PUBLIC, "Reallusion Templates", "Animation"),          # "Motion Plus/Actor Group/..."
               os.path.join(PUBLIC, "Template", "iClone 7 Template", "iClone Template", "Motion"),
               os.path.join(PUBLIC, "Template", "iClone 7 Template", "iClone Template", "MographMotion")],
    "sky": [os.path.join(PUBLIC, "Template", "iClone 7 Template", "iClone Template", "Sky"),
            os.path.join(PUBLIC, "Reallusion Templates", "Stage", "Sky")],
}
STAGES = ["project", "set", "paths", "cast", "walks", "dialog", "sky", "camera", "qa"]


class BuildError(RuntimeError):
    pass


def ok(r, what):
    if not isinstance(r, dict) or r.get("isError") or r.get("rpc_error") or r.get("ok") is False or r.get("status") == "error":
        raise BuildError(f"{what}: {json.dumps(r)[:600]}")
    return r


def py(code, **kw):
    return ok(call("python_exec", {"code": code, **kw}), "python_exec")["result"]


def resolve(kind, rel, base_dir):
    """Absolute/env path as given; else relative to the spec file; else under the stock library roots for `kind`."""
    p = os.path.expandvars(os.path.expanduser(rel))
    for cand in [p, os.path.join(base_dir, p)] + [os.path.join(r, p) for r in ROOTS.get(kind, [])]:
        for c in (cand, cand + {"avatar": ".iAvatar", "motion": ".rlMotion", "sky": ".iSky"}.get(kind, "")):
            if os.path.isfile(c):
                return os.path.normpath(c)
    raise BuildError(f"{kind} file not found: {rel!r} (looked as given, next to the spec, and under {ROOTS.get(kind)})")


def vec(v, z=0.0):
    return {"x": float(v[0]), "y": float(v[1]), "z": float(v[2]) if len(v) > 2 else z}


class Builder:
    def __init__(self, spec, base_dir):
        self.s, self.base = spec, base_dir
        self.fps = int(spec.get("fps", 30))
        self.length_s = float(spec.get("length_s", 20))
        name = spec.get("name", "scene")
        self.project = os.path.expandvars(spec.get("project") or os.path.join(
            os.path.expanduser("~"), "Documents", "Reallusion", name, name + ".iProject"))
        self.out_dir = os.path.dirname(self.project)
        self.report = {}

    # ------------------------------------------------------------------------------------------------------- stages
    def project_stage(self):
        # new_project blocks on a discard prompt; a silent LoadFile of the default project does not. Then SAVE to our own
        # path immediately so checkpoint tools never touch another project.
        py("import RLPy\nRLPy.RFileIO.LoadFile(RLPy.RApplication.GetDefaultProjectPath())", silent=True)
        ok(call("set_project_fps", {"fps": self.fps}), "fps")
        ok(call("set_timeline_range", {"project_length": self.length_s, "start": 0, "end": self.length_s, "unit": "seconds"}), "length")
        os.makedirs(self.out_dir, exist_ok=True)
        ok(call("save_project", {"path": self.project}), "save")
        return {"project": self.project, "fps": self.fps, "length_s": self.length_s}

    def set_stage(self):
        made = []
        for item in self.s.get("set", []):
            size = item["size"]
            r = call("create_primitive", {"type": item.get("type", "box"), "name": item["name"],
                                          "position": vec(item["at"], float(item.get("bottom_z", 0))),
                                          "scale": {"x": size[0] / 100.0, "y": size[1] / 100.0, "z": size[2] / 100.0}})
            if r.get("status") != "ok":
                raise BuildError(f"primitive {item['name']}: {r}")
            if item.get("color"):
                call("set_timeline", {"frame": 0})        # material colour is KEYED at the current frame
                c = item["color"]
                ok(call("set_material_color", {"name": item["name"], "color": {"r": c[0], "g": c[1], "b": c[2]}}), f"colour {item['name']}")
            made.append(item["name"])
        return {"primitives": made}

    def paths_stage(self):
        made = []
        for p in self.s.get("paths", []):
            pts = [vec(v) for v in p["points"]]
            self._camera_over([v for v in p["points"]])
            r = ok(call("draw_path", {"name": p["name"], "points": pts}), f"path {p['name']}")
            made.append({"name": p["name"], "length_cm": r.get("length_cm")})
        return {"paths": made}

    def _load_avatar(self, member):
        py("import RLPy\nRLPy.RScene.ClearSelectObjects()")       # loading with an avatar selected REPLACES it
        r = call("load_object", {"path": resolve("avatar", member["avatar"], self.base)})
        if r.get("status") != "ok":
            raise BuildError(f"load {member['avatar']}: {r}")
        name = r["name"]
        if member.get("name") and member["name"] != name:
            ok(call("rename_object", {"name": name, "new_name": member["name"]}), f"rename {name}")
            name = member["name"]
        return name

    def cast_stage(self):
        out = []
        for m in self.s.get("cast", []):
            name = self._load_avatar(m)
            row = {"name": name}
            mo = m.get("motion")
            if mo:
                path = resolve("motion", mo["clip"], self.base)
                start = float(mo.get("start_s", 0))
                ok(call("load_motion_verified", {"avatar": name, "path": path, "frame": int(round(start * self.fps))}), f"motion {name}")
                clips = [{"path": path, "start_s": start}]
                if mo.get("loop_to_end", True):
                    one = ok(call("get_animation_clips", {"avatar_name": name}), "clips")["clips"][0]
                    clen = one["end_s"] - one.get("start_s", start)
                    t = start
                    while t + clen < self.length_s and clen > 0.5:
                        t = round(t + clen + 1.0 / self.fps, 4)     # next clip at previous end + 1 frame
                        clips.append({"path": path, "start_s": t})
                ok(call("motion_track", {"avatar": name, "clips": clips}), f"motion track {name}")
                row["clips"] = len(clips)
            if m.get("place"):
                pl = m["place"]
                ok(call("place_object", {"name": name, "position": vec(pl["at"]),
                                         "rotation_degrees": {"x": 0, "y": 0, "z": float(pl.get("turn", 0))}}), f"place {name}")
            if m.get("sit_on"):
                # CLAUDE-NOTE (2026-10-16): seat the body on the prop from its real posed surface (fit_sitter); a guessed
                # place z left the stock male sunk 4 cm with feet 8 cm up. Advice = the clip wants another seat height
                # (see examples/catalog/sit_clips.json).
                r = ok(call("fit_sitter", {"avatar": name, "seat": m["sit_on"], "mode": m.get("sit_mode", "seat"),
                                           "end_frame": int(self.length_s * self.fps), "samples": 16}), f"fit {name}")
                row["sit"] = {k: r.get(k) for k in ("dz_cm", "authored_seat_height_cm", "sole_z_after", "advice") if r.get(k) is not None}
            out.append(row)
        for m in self.s.get("cast", []):
            if m.get("look_at"):
                ok(call("set_look_at", {"avatar": m["name"], "target": m["look_at"], "frame": 0, "transition_frames": 0,
                                        "head_weight": 0.8, "body_weight": 0.2}), f"look {m['name']}")
        return {"cast": out}

    def walks_stage(self):
        out, md = [], []
        for w in self.s.get("walkers", []):
            name = self._load_avatar(w)
            if w.get("path"):                            # Motion Director on a path (natural, motion-matched)
                if not any(p["name"] == w["path"] for p in self.s.get("paths", [])):
                    raise BuildError(f"walker {name}: path {w['path']!r} is not in the spec's 'paths'")
                md.append({"avatar": name, "path": w["path"], "imd": w.get("imd", "male"),
                           "start_frame": int(round(float(w.get("start_s", 0)) * self.fps))})
            else:                                         # straight walk with chained root-motion clips
                args = {"avatar": name, "from": vec(w["from"]), "to": vec(w["to"]),
                        "start_frame": int(round(float(w.get("start_s", 0)) * self.fps)),
                        "speed_cm_s": float(w.get("pace_cm_s", 100)), "idle_after": bool(w.get("idle_after", False))}
                if w.get("motion"):
                    args["motion"] = resolve("motion", w["motion"], self.base)
                r = ok(call("walk_to", args), f"walk {name}")
                out.append({"name": name, "mode": "walk_to", "end_frame": r.get("end_frame"), "hip_error_cm": r.get("hip_error_cm")})
        if md:
            # CLAUDE-NOTE (2026-10-16): all MD walkers go through ONE md_walk_paths call -> one real-time take per start
            # frame instead of one per walker. The pick camera must see every path at once.
            pts = [pt for p in self.s.get("paths", []) if p["name"] in {m["path"] for m in md} for pt in p["points"]]
            self._camera_over(pts)
            secs = max([float(w["seconds"]) for w in self.s.get("walkers", []) if w.get("seconds")] or [0]) or None
            r = ok(call("md_walk_paths", {"walkers": md, **({"seconds": secs} if secs else {})},
                        timeout=600), "md walkers")
            for v in r["walkers"]:
                out.append({"name": v.get("avatar"), "mode": "md", "slide": v.get("slide_ratio"),
                            "dev_cm": v.get("max_path_deviation_cm"), "ok": v.get("ok")})
        return {"walkers": out}

    def dialog_stage(self):
        out = []
        for i, line in enumerate(self.s.get("dialog", []), 1):
            wav = os.path.expandvars(line["wav"])
            wav = wav if os.path.isabs(wav) else os.path.join(self.base, wav)
            if not os.path.isfile(wav):
                raise BuildError(f"dialog wav not found: {wav}")
            r = call("load_vocal", {"avatar_name": line["who"], "audio_path": wav, "clip_name": f"line_{i:02d}",
                                    "start_frame": int(round(float(line["at_s"]) * self.fps))})
            if r.get("status") != "ok":
                raise BuildError(f"vocal {wav}: {r}")
            out.append(os.path.basename(wav))
        return {"lines": out}

    def sky_stage(self):
        if not self.s.get("sky"):
            return {"sky": None}
        sky = resolve("sky", self.s["sky"], self.base)    # load_object fails on skies; LoadFile replaces the scene sky
        py("import RLPy\nRLPy.RScene.ClearSelectObjects()\nRLPy.RFileIO.LoadFile(r'%s')" % sky, silent=True)
        return {"sky": os.path.basename(sky)}

    def camera_stage(self):
        out = {}
        if self.s.get("camera"):
            c = self.s["camera"]
            ok(call("aim_camera", {"name": c.get("name", "Camera"), "position": vec(c["position"]), "target": vec(c["target"]),
                                   "focal_length_mm": float(c.get("lens_mm", 35)), "make_current": True, "hold": True}), "camera")
            out["camera"] = c.get("name", "Camera")
        if self.s.get("shots"):
            shots = []
            for sh in self.s["shots"]:
                # CLAUDE-NOTE (2026-10-16): a shot may give `frame` (+ optional `end_frame`) = frame_shot args (subjects,
                # size, azimuth_deg, ...) instead of coordinates; solved on the posed bodies at the shot's start/end.
                for key, when in (("frame", sh["start_s"]), ("end_frame", sh["end_s"] - 1.0 / self.fps)):
                    if sh.get(key):
                        fa = dict(sh[key], apply=False, frame=int(round(when * self.fps)))
                        if key == "frame" and not sh.get("end_frame"):          # static shot: keep subjects framed throughout
                            fa["through_frame"] = int(round(sh["end_s"] * self.fps)) - 1
                        r = ok(call("frame_shot", fa), f"frame {sh['id']}")
                        if r.get("fit_error", 0) > 0.3:
                            print(f"  WARN {sh['id']}: no clean over-the-shoulder for this staging (fit_error "
                                  f"{r['fit_error']}); try the other shoulder, another subject or a sized shot", flush=True)
                        pre = "" if key == "frame" else "end_"
                        sh = dict(sh, **{pre + "position": r["position"], pre + "target": r["target"], pre + "lens_mm": r["lens_mm"]})
                d = {"id": sh["id"], "start_s": sh["start_s"], "end_s": sh["end_s"], "position": vec(sh["position"]),
                     "target": vec(sh["target"]), "focal_length_mm": float(sh.get("lens_mm", 35))}
                for k in ("end_position", "end_target"):
                    if sh.get(k):
                        d[k] = vec(sh[k])
                if sh.get("end_lens_mm"):
                    d["end_focal_length_mm"] = float(sh["end_lens_mm"])
                shots.append(d)
            ok(call("build_shot_list", {"shots": shots}), "shots")
            out["shots"] = [s["id"] for s in shots]
        py("import RLPy\nfor c in list(RLPy.RScene.GetCameras()):\n    if c.GetName().startswith('_build_'): RLPy.RScene.RemoveObject(c)")
        ok(call("save_project", {}), "save")
        return out

    def qa_stage(self):
        end = int(self.length_s * self.fps) - 1
        q = ok(call("motion_qa", {"start_frame": 0, "end_frame": end, "step": 2}), "motion_qa")
        frames = [int(end * k / 7) for k in range(8)]
        f = ok(call("filmstrip", {"frames": frames, "cols": 4, "tile_width": 400, "return_image": False,
                                  "output_dir": os.path.join(self.out_dir, "qa")}), "filmstrip")
        slides = {n: r.get("slide_ratio") for n, r in q["avatars"].items() if r.get("slide_ratio") is not None}
        return {"flags": q["flags"], "slide_ratio": slides, "filmstrip": f.get("path")}

    def previz(self):
        out = []
        for sh in self.s.get("shots", []):
            s, e = int(sh["start_s"] * self.fps), int(sh["end_s"] * self.fps) - 1
            r = ok(call("previz_export", {"start_frame": s, "end_frame": e, "camera": sh["id"], "return_image": False,
                                          "output_dir": os.path.join(self.out_dir, "previz", sh["id"])}, timeout=3600), f"previz {sh['id']}")
            out.append({"shot": sh["id"], "frames": r.get("frames_per_pass"), "check_sheet": r.get("check_sheet")})
        return {"previz": out}

    # ------------------------------------------------------------------------------------------------------ helpers
    def _camera_over(self, points):
        """A temporary top-down camera that sees `points` (draw_path and Motion Director picks click in the viewport)."""
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
        extent = max(max(xs) - min(xs), max(ys) - min(ys), 300.0)
        height = extent * 1.6 / (2 * math.tan(math.radians(36)))
        ok(call("aim_camera", {"name": "_build_top", "position": {"x": cx, "y": cy - 1, "z": height}, "target": {"x": cx, "y": cy, "z": 0},
                               "focal_length_mm": 24, "make_current": True, "hold": True}), "build camera")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--stages", help="comma list from " + ",".join(STAGES))
    ap.add_argument("--previz", action="store_true", help="also export per-shot previz packages")
    a = ap.parse_args(argv)
    spec_path = os.path.abspath(a.spec)
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    b = Builder(spec, os.path.dirname(spec_path))
    stages = a.stages.split(",") if a.stages else STAGES
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        ap.error(f"unknown stage(s) {unknown}; choose from {STAGES}")
    for st in stages:
        print(f"== {st}", flush=True)
        try:
            res = getattr(b, st + "_stage")()
        except BuildError as e:
            print(f"FAILED at stage {st!r}: {e}", file=sys.stderr)
            print("Fix the spec (or see the iclone-mcp skill gotchas), then re-run with --stages", st + ",...", file=sys.stderr)
            return 1
        b.report[st] = res
        print(json.dumps(res, ensure_ascii=False)[:1500], flush=True)
    if a.previz:
        print("== previz", flush=True)
        b.report["previz"] = b.previz()
        print(json.dumps(b.report["previz"])[:1500])
    with open(os.path.join(b.out_dir, "build_report.json"), "w", encoding="utf-8") as fh:
        json.dump(b.report, fh, indent=1)
    print("done ->", os.path.join(b.out_dir, "build_report.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
