"""Offline check of a scene spec before building it: every file resolves, every name a field refers to exists, times fit
the scene. No iClone needed (run by `build_scene.py spec.json --check`, or `python scripts/spec_check.py spec.json`).
# CLAUDE-NOTE (2026-10-18, cafe trial): a Sonnet agent wrote `HD Idle_F` (the docs said "_F variants"; the files are
# `HD Idle 01_F` / `02_F`) - the build would have failed minutes in, after loading the set. Catch it up front and say
# what the closest real names are.
"""
import difflib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)
from build_scene import ROOTS, BuildError, resolve  # noqa: E402

TOP = {"name", "project", "description", "fps", "length_s", "set", "paths", "cast", "groups", "interactions", "walkers",
       "wander", "vehicles", "dialog", "face", "sky", "lighting", "camera", "shots", "interior", "render", "style",
       "previz"}
SIZES = {"extreme_wide", "wide", "full", "medium_wide", "medium", "medium_closeup", "closeup", "extreme_closeup", "ots"}
EXTS = {"avatar": (".iavatar",), "prop": (".iprop",), "sky": (".isky",),
        "motion": (".rlmotion", ".imotion", ".imotionplus")}


def _stems(kind):
    out = {}
    for r in ROOTS.get(kind, []):
        for d, _, files in os.walk(r):
            for f in files:
                if f.lower().endswith(EXTS[kind]):
                    out.setdefault(os.path.splitext(f)[0], os.path.relpath(os.path.join(d, f), r).replace("\\", "/"))
    return out


_CACHE = {}


def did_you_mean(kind, name):
    if kind not in _CACHE:
        _CACHE[kind] = _stems(kind)
    stems = _CACHE[kind]
    stem = os.path.splitext(os.path.basename(name))[0]
    close = difflib.get_close_matches(stem, list(stems), n=3, cutoff=0.6)
    return "; did you mean " + ", ".join(repr(stems[c]) for c in close) if close else ""


def _gaits():
    try:
        with open(os.path.join(REPO, "examples", "catalog", "gaits.json"), encoding="utf-8") as fh:
            return {g["imd"] for g in json.load(fh)["gaits"]} | {"male", "female"}
    except (OSError, ValueError, KeyError):
        return None


def _seat_fit():
    try:
        with open(os.path.join(REPO, "examples", "catalog", "avatars.json"), encoding="utf-8") as fh:
            rows = json.load(fh)["avatars"]
    except (OSError, ValueError, KeyError):
        return {}
    return {os.path.splitext(r["spec"])[0].lower(): r.get("seat_fit") for r in rows}


def check(spec, base_dir):
    """-> (errors, warnings): lists of strings, each naming the spec field."""
    err, warn = [], []
    length = float(spec.get("length_s", 20))

    def need(kind, rel, where):
        try:
            resolve(kind, rel, base_dir)
            return True
        except BuildError:
            err.append(f"{where}: {kind} {rel!r} not found{did_you_mean(kind, rel)}")
            return False

    def need_clip(rel, where):
        # actions[].clip and groups clips also accept a bare file stem (acting.resolve_clip searches the library)
        from tools.acting import resolve_clip
        try:
            resolve_clip(rel)
        except FileNotFoundError:
            err.append(f"{where}: clip {rel!r} not found{did_you_mean('motion', rel)}")

    for k in spec:
        if k not in TOP:
            close = difflib.get_close_matches(k, sorted(TOP), n=1)
            warn.append(f"top-level key {k!r} is not used by the builder" + (f" (did you mean {close[0]!r}?)" if close else ""))

    set_names = {s.get("name") for s in spec.get("set", [])}
    path_names = {p.get("name") for p in spec.get("paths", [])}
    people = [m.get("name") for m in spec.get("cast", []) + spec.get("walkers", [])]
    for g in spec.get("groups", []):
        people += [m.get("name") for m in g.get("members", [])]
    for wz in spec.get("wander", []):
        people += [m.get("name") for m in wz.get("people", [])]
    named = set(people) - {None}
    dup = {n for n in people if n and people.count(n) > 1}
    if dup:
        err.append(f"people names used twice: {sorted(dup)}")

    for s in spec.get("set", []):
        w = f"set {s.get('name')!r}"
        if s.get("asset"):
            need("prop", s["asset"], w)
        elif not s.get("room") and not s.get("size"):
            err.append(f"{w}: needs `size` [x,y,z] (primitive), `asset` (a prop) or `room`")

    for p in spec.get("paths", []):
        if len(p.get("points", [])) < 2:
            err.append(f"path {p.get('name')!r}: needs at least 2 points")

    from tools.layering import PRESETS as OVERLAY_BONES

    def check_overlays(member, where):
        for i, o in enumerate(member.get("overlay", [])):
            w = f"{where} overlay[{i}]"
            need_clip(o.get("clip", ""), w)
            b = o.get("bones", "arm_r")
            if isinstance(b, str) and b not in OVERLAY_BONES:
                err.append(f"{w}: bones {b!r} must be one of {sorted(OVERLAY_BONES)} or a list of bone names")
            s0, s1 = float(o.get("at_s", 0)), float(o.get("until_s", length))
            if not 0 <= s0 < s1 <= length + 1e-6:
                err.append(f"{w}: needs 0 <= at_s < until_s <= length_s (got {s0}..{s1})")

    gaits = _gaits()
    fits = _seat_fit()
    for m in spec.get("cast", []):
        w = f"cast {m.get('name')!r}"
        if need("avatar", m.get("avatar", ""), w) and m.get("sit_on"):
            fit = fits.get(os.path.splitext(m["avatar"])[0].lower().replace("\\", "/"))
            if fit and fit != "ok":
                err.append(f"{w}: sit_on needs an avatar whose catalog row says seat_fit ok ({m['avatar']}: {fit})")
        if m.get("motion"):
            need("motion", m["motion"].get("clip", ""), f"{w} motion.clip")
        for i, a in enumerate(m.get("actions", [])):
            need_clip(a.get("clip", ""), f"{w} actions[{i}]")
        if m.get("sit_on") and m["sit_on"] not in set_names:
            err.append(f"{w}: sit_on {m['sit_on']!r} is not a `set` name")
        if m.get("look_at") and m["look_at"] not in named:
            err.append(f"{w}: look_at {m['look_at']!r} is not a person in the spec")
        h = m.get("hold") or {}
        if h.get("prop") and h["prop"] not in set_names:
            err.append(f"{w}: hold.prop {h['prop']!r} is not a `set` name")
        if h.get("preset") and h["preset"] not in ("phone", "cup", "book"):
            err.append(f"{w}: hold.preset must be phone, cup or book")
        check_overlays(m, w)
        for i, rc in enumerate(m.get("reach", [])):
            if rc.get("action", "touch") not in ("touch", "wipe", "pick"):
                err.append(f"{w} reach[{i}]: action must be touch, wipe or pick")
            if not rc.get("point") and not rc.get("object"):
                err.append(f"{w} reach[{i}]: needs `point` [x,y,z] or `object` (a set name)")
            if rc.get("object") and rc["object"] not in set_names:
                err.append(f"{w} reach[{i}]: object {rc['object']!r} is not a `set` name")
            if rc.get("action") == "pick" and not rc.get("object"):
                err.append(f"{w} reach[{i}]: pick needs `object`")
        if m.get("sit_on") and not m.get("motion") and not m.get("actions"):
            warn.append(f"{w}: sit_on without a sit clip - give motion.clip (examples/catalog/sit_clips.json)")

    for g in spec.get("groups", []):
        for i, m in enumerate(g.get("members", [])):
            w = f"groups member {m.get('name')!r}"
            need("avatar", m.get("avatar", ""), w)
            if m.get("clip"):
                need("motion", m["clip"], w + " clip")
    for w_ in spec.get("walkers", []):
        w = f"walker {w_.get('name')!r}"
        need("avatar", w_.get("avatar", ""), w)
        if w_.get("path"):
            if w_["path"] not in path_names:
                err.append(f"{w}: path {w_['path']!r} is not in `paths`")
            imd = w_.get("imd", "male")
            if gaits and imd not in gaits and not os.path.isfile(imd):
                err.append(f"{w}: imd {imd!r} unknown; use one of {sorted(gaits)} (examples/catalog/gaits.json)")
        elif not (w_.get("from") and w_.get("to")):
            err.append(f"{w}: needs `path` (Motion Director) or `from` + `to` (straight walk)")
        if w_.get("arrive_clip"):
            if not w_.get("path"):
                err.append(f"{w}: arrive_clip needs a Motion Director `path` walker")
            need("motion", w_["arrive_clip"], f"{w} arrive_clip")
        check_overlays(w_, w)
        for k in ("actions", "look_at", "sit_on"):
            if k in w_:
                err.append(f"{w}: walkers have no `{k}` (cast[] only) - it would be ignored")
        if float(w_.get("start_s", 0)) >= length:
            err.append(f"{w}: start_s {w_['start_s']} is past length_s {length}")
    for wz in spec.get("wander", []):
        if wz.get("zone") not in set_names:
            err.append(f"wander zone {wz.get('zone')!r} is not a `set` name")
        for m in wz.get("people", []):
            need("avatar", m.get("avatar", ""), f"wander person {m.get('name')!r}")
            if gaits and m.get("imd", "male") not in gaits:
                err.append(f"wander person {m.get('name')!r}: imd {m.get('imd')!r} unknown; use one of {sorted(gaits)}")
    for v in spec.get("vehicles", []):
        if v.get("name") not in set_names:
            err.append(f"vehicle {v.get('name')!r} is not a `set` name (load the car in `set`)")
        if v.get("path") not in path_names:
            err.append(f"vehicle {v.get('name')!r}: path {v.get('path')!r} is not in `paths`")

    for fx in spec.get("face", []):
        if fx.get("who") not in named:
            err.append(f"face: who {fx.get('who')!r} is not a person in the spec")
        try:
            from tools.performance import resolve as face_resolve
            face_resolve(fx.get("clip", ""))
        except (FileNotFoundError, ValueError):
            err.append(f"face {fx.get('who')!r}: expression {fx.get('clip')!r} not found (list_expressions shows the moods)")
    for line in spec.get("dialog", []):
        if line.get("who") not in named:
            err.append(f"dialog: who {line.get('who')!r} is not a person in the spec")
    if spec.get("sky"):
        need("sky", spec["sky"], "sky")

    ids = []
    for sh in spec.get("shots", []):
        w = f"shot {sh.get('id')!r}"
        ids.append(sh.get("id"))
        s, e = float(sh.get("start_s", 0)), float(sh.get("end_s", 0))
        if not 0 <= s < e:
            err.append(f"{w}: needs 0 <= start_s < end_s (got {s}..{e})")
        if e > length + 1e-6:
            err.append(f"{w}: end_s {e} is past length_s {length}")
        fr = sh.get("frame")
        if fr:
            for subj in fr.get("subjects", []):
                if subj not in named:
                    err.append(f"{w}: subject {subj!r} is not a person in the spec")
            if fr.get("size", "medium") not in SIZES:
                err.append(f"{w}: size {fr.get('size')!r} must be one of {sorted(SIZES)}")
            if fr.get("facing", "body") not in ("body", "head"):
                err.append(f"{w}: facing must be body (default) or head")
        elif not (sh.get("position") and sh.get("target")):
            err.append(f"{w}: needs `frame` (solved framing) or `position` + `target`")
        elif spec.get("interior"):
            warn.append(f"{w}: hand-placed position is NOT pulled inside the room (`interior` applies to `frame` shots)")
    if len(ids) != len(set(ids)):
        err.append("shot ids must be unique")
    return err, warn


def main(argv=None):
    path = (argv or sys.argv[1:])[0]
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    err, warn = check(spec, os.path.dirname(os.path.abspath(path)))
    for w in warn:
        print("WARN ", w)
    for e in err:
        print("ERROR", e)
    print(f"{len(err)} error(s), {len(warn)} warning(s)")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
