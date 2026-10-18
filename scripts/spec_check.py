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
from build_scene import ROOTS, BuildError, expand_crowds, resolve  # noqa: E402

TOP = {"name", "project", "description", "fps", "length_s", "set", "paths", "cast", "groups", "interactions", "walkers",
       "wander", "crowds", "vehicles", "dialog", "face", "sky", "atmosphere", "lighting", "environment", "lights", "weather", "walkway_crowds", "camera", "shots",
       "interior", "render", "style", "previz"}
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
    for i, c in enumerate(spec.get("crowds", [])):
        w = f"crowds[{i}] {c.get('name')!r}"
        if not c.get("avatars") and not c.get("people"):
            err.append(f"{w}: needs `people` [{{avatar, clip}}] or `avatars` (a pool, cycled)")
        if c.get("formation", "rows") not in ("rows", "arc", "scatter"):
            err.append(f"{w}: formation must be rows, arc or scatter")
        if c.get("formation") == "scatter" and not c.get("size"):
            err.append(f"{w}: scatter needs `size` [w, d] cm")
    try:
        spec = expand_crowds(spec)            # crowd members are checked below as ordinary cast
    except (BuildError, KeyError) as e:
        err.append(f"crowds: {e}")

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
        if s.get("moves") and (s.get("room") or s.get("doorways")):
            err.append(f"{w}: rooms cannot have `moves`")
        pv = s.get("pivot")
        if pv is not None:
            from tools.pivots import PIVOT_SIDES
            if s.get("room"):
                err.append(f"{w}: rooms cannot take a `pivot`")
            elif isinstance(pv, str) and pv not in PIVOT_SIDES:
                err.append(f"{w}: pivot must be [x,y,z] or one of {sorted(PIVOT_SIDES)}")
            elif not isinstance(pv, str) and (not isinstance(pv, list) or len(pv) != 3):
                err.append(f"{w}: pivot must be [x,y,z] or one of {sorted(PIVOT_SIDES)}")
            elif any("to" in mv for mv in s.get("moves", [])):
                warn.append(f"{w}: with a pivot, moves[].to is where the PIVOT goes (not the item centre)")
        last = 0.0
        for i, mv in enumerate(sorted(s.get("moves", []), key=lambda m: m.get("start_s", 0))):
            a, b = mv.get("start_s"), mv.get("end_s")
            if a is None or b is None or not 0 <= float(a) < float(b) <= length + 1e-6:
                err.append(f"{w} moves[{i}]: needs 0 <= start_s < end_s <= length_s (got {a}, {b})")
                continue
            if float(a) < last - 1e-6:
                err.append(f"{w} moves[{i}]: starts before the previous move ends ({last} s)")
            last = float(b)
            if mv.get("to") is not None and len(mv["to"]) < 2:
                err.append(f"{w} moves[{i}]: `to` is [x, y]")
            if not any(k in mv for k in ("to", "turn", "bottom_z")):
                err.append(f"{w} moves[{i}]: give at least one of `to`, `turn`, `bottom_z`")
            if mv.get("transition", "ease_in_out") not in ("linear", "ease_in_out", "ease_in", "ease_out", "step"):
                err.append(f"{w} moves[{i}]: transition must be linear, ease_in_out, ease_in, ease_out or step")

    for p in spec.get("paths", []):
        if len(p.get("points", [])) < 2:
            err.append(f"path {p.get('name')!r}: needs at least 2 points")

    from tools.lighting import PRESETS as LIGHT_PRESETS, find_atmosphere
    atm = spec.get("atmosphere")
    if atm:
        name = atm if isinstance(atm, str) else atm.get("preset")
        if name:
            try:
                find_atmosphere(name)
            except ValueError as ex:
                err.append(f"atmosphere: {ex}")
        if spec.get("lighting"):
            err.append("atmosphere replaces every light (incl. Key/Side/Back), so `lighting` cannot follow it - "
                       "use one or the other; `lights` (added practicals) still work")
        fog = {} if isinstance(atm, str) else (atm.get("fog") or {})
        if fog and "start" in fog and "end" in fog and float(fog["end"]) <= float(fog["start"]):
            err.append("atmosphere.fog: end must be beyond start")
    from tools.weather import weather_file
    for i, wz in enumerate(spec.get("weather", [])):
        try:
            weather_file(wz.get("kind", "rain"))
        except ValueError as ex:
            err.append(f"weather[{i}]: {ex}")
        a, b = float(wz.get("start_s", 0)), wz.get("stop_s")
        if not 0 <= a <= length or (b is not None and not a < float(b) <= length + 1e-6):
            err.append(f"weather[{i}]: needs 0 <= start_s < stop_s <= length_s")
    lt = spec.get("lighting")
    beats = lt if isinstance(lt, list) else ([lt] if lt else [])
    seen = set()
    for i, b in enumerate(beats):
        w = f"lighting[{i}]" if isinstance(lt, list) else "lighting"
        if b.get("preset", "day") not in LIGHT_PRESETS:
            err.append(f"{w}: preset {b.get('preset')!r} must be one of {sorted(LIGHT_PRESETS)}")
        if isinstance(lt, list):
            a = b.get("at_s")
            if a is None or not 0 <= float(a) <= length:
                err.append(f"{w}: a time-lapse beat needs at_s within 0..length_s")
            elif float(a) in seen:
                err.append(f"{w}: two lighting beats at {a} s")
            else:
                seen.add(float(a))
    if isinstance(lt, list) and lt and min(float(b.get("at_s", 0) or 0) for b in lt) > 0:
        warn.append("lighting: the first beat is keyed at frame 0 whatever its at_s (the look holds until the next beat)")

    from tools.layering import BONE_ALIASES, HAND_POSES, LAUGH_BONES, PRESETS as OVERLAY_BONES

    def check_laughs(member, where):
        for i, lg in enumerate(member.get("laugh", [])):
            a, d = float(lg.get("at_s", 0)), float(lg.get("seconds", 2.0))
            if not 0 <= a < a + d <= length + 1e-6:
                err.append(f"{where} laugh[{i}]: at_s + seconds must end by length_s (got {a}+{d})")

    def check_hands(member, where):
        spans = {}
        for i, h in enumerate(member.get("hands", [])):
            w = f"{where} hands[{i}]"
            if h.get("pose") not in HAND_POSES:
                err.append(f"{w}: pose {h.get('pose')!r} must be one of {sorted(HAND_POSES)}")
            if h.get("hand", "r") not in ("r", "l", "both"):
                err.append(f"{w}: hand must be r, l or both")
            s0, s1 = float(h.get("at_s", 0)), float(h.get("until_s", length))
            if not 0 <= s0 < s1 <= length + 1e-6:
                err.append(f"{w}: needs 0 <= at_s < until_s <= length_s (got {s0}..{s1})")
            for j, (a, b) in spans.get(h.get("hand", "r"), []):
                if s0 < b and a < s1:
                    err.append(f"{w}: overlaps hands[{j}] on the same hand")
            spans.setdefault(h.get("hand", "r"), []).append((i, (s0, s1)))

    def check_poses(member, where):
        posed = set()
        for i, p in enumerate(member.get("pose", [])):
            w = f"{where} pose[{i}]"
            if not p.get("bones"):
                err.append(f"{w}: needs bones {{name: {{yaw, pitch, roll}}}}")
            for k, v in (p.get("bones") or {}).items():
                if not k.startswith("CC_Base_") and k not in BONE_ALIASES:
                    err.append(f"{w}: bone {k!r} must be a CC_Base_ name or one of {sorted(BONE_ALIASES)}")
                if not isinstance(v, dict) or set(v) - {"yaw", "pitch", "roll"}:
                    err.append(f"{w}: bone {k!r} takes {{yaw, pitch, roll}} degrees")
                posed.add(BONE_ALIASES.get(k, k))
            s0, s1 = float(p.get("at_s", 0)), float(p.get("until_s", length))
            if not 0 <= s0 < s1 <= length + 1e-6:
                err.append(f"{w}: needs 0 <= at_s < until_s <= length_s (got {s0}..{s1})")
        if len(member.get("pose", [])) > 1:
            names = [set(BONE_ALIASES.get(k, k) for k in (p.get("bones") or {})) for p in member["pose"]]
            if any(a & b for i, a in enumerate(names) for b in names[i + 1:]):
                err.append(f"{where}: two pose[] entries move the same bone - each call clears that bone's earlier keys; "
                           f"merge them or use different bones")
        if posed & set(LAUGH_BONES) and member.get("laugh"):
            err.append(f"{where}: pose and laugh share bones {sorted(posed & set(LAUGH_BONES))} - the laugh would wipe the pose")

    def check_pins(member, where):
        spans = {}
        for i, pn in enumerate(member.get("pins", [])):
            w = f"{where} pins[{i}]"
            eff = pn.get("effector", "left_foot")
            if eff not in ("left_foot", "right_foot", "left_hand", "right_hand"):
                err.append(f"{w}: effector must be left_foot, right_foot, left_hand or right_hand (head cannot be pinned)")
            a, b = pn.get("at_s"), pn.get("until_s")
            if a is None or b is None or not 0 <= float(a) < float(b) <= length + 1e-6:
                err.append(f"{w}: needs 0 <= at_s < until_s <= length_s (got {a}, {b})")
                continue
            for (pa, pb) in spans.get(eff, []):
                if float(a) < pb and pa < float(b):
                    err.append(f"{w}: overlaps another pin on {eff}")
            spans.setdefault(eff, []).append((float(a), float(b)))

    def check_overlays(member, where):
        check_laughs(member, where)
        check_pins(member, where)
        check_hands(member, where)
        check_poses(member, where)
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
        shot_ids = {sh.get("id") for sh in spec.get("shots", [])}
        prev_end = None
        for i, lk in enumerate(m.get("looks", [])):
            t = lk.get("target")
            if t not in named and t not in set_names and t not in shot_ids:
                err.append(f"{w} looks[{i}]: target {t!r} is not a person, a `set` name or a shot id")
            if t == m.get("name"):
                err.append(f"{w} looks[{i}]: a character cannot look at itself")
            if "at_s" not in lk:
                err.append(f"{w} looks[{i}]: needs at_s")
                continue
            if lk.get("until_s") is not None and float(lk["until_s"]) <= float(lk["at_s"]):
                err.append(f"{w} looks[{i}]: until_s must be after at_s")
            if prev_end is not None and float(lk["at_s"]) < prev_end:
                err.append(f"{w} looks[{i}]: overlaps the previous look (sort by at_s; end one before the next)")
            prev_end = float(lk.get("until_s", lk["at_s"]))
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
        if w_.get("follow"):
            lead = w_["follow"]
            if lead == w_.get("name") or (lead not in named and lead not in set_names):
                err.append(f"{w}: follow {lead!r} must be another person or a `set` prop")
            if w_.get("path") or w_.get("from"):
                err.append(f"{w}: a follower has no `path`/`from` - it goes where its leader goes")
            if float(w_.get("start_s", 0)) != 0:
                err.append(f"{w}: followers record in the scene's first take - use delay_s instead of start_s")
            leader = next((x for x in spec.get("walkers", []) if x.get("name") == lead), None)
            if leader and float(leader.get("start_s", 0)) != 0:
                err.append(f"{w}: its leader {lead!r} starts late (start_s) - a follower needs a leader in the first take")
            imd = w_.get("imd", "male")
            if gaits and imd not in gaits and not os.path.isfile(imd):
                err.append(f"{w}: imd {imd!r} unknown; use one of {sorted(gaits)} (examples/catalog/gaits.json)")
        elif w_.get("path"):
            if w_["path"] not in path_names:
                err.append(f"{w}: path {w_['path']!r} is not in `paths`")
            imd = w_.get("imd", "male")
            if gaits and imd not in gaits and not os.path.isfile(imd):
                err.append(f"{w}: imd {imd!r} unknown; use one of {sorted(gaits)} (examples/catalog/gaits.json)")
        elif not (w_.get("from") and w_.get("to")):
            err.append(f"{w}: needs `path` (Motion Director), `follow` (walks after someone) or `from` + `to` (straight walk)")
        if w_.get("arrive_clip"):
            if not w_.get("path"):
                err.append(f"{w}: arrive_clip needs a Motion Director `path` walker")
            need("motion", w_["arrive_clip"], f"{w} arrive_clip")
        check_overlays(w_, w)
        for k in ("actions", "look_at", "sit_on", "looks", "pins"):
            if k in w_:
                err.append(f"{w}: walkers have no `{k}` (cast[] only) - it would be ignored")
        if float(w_.get("start_s", 0)) >= length:
            err.append(f"{w}: start_s {w_['start_s']} is past length_s {length}")
    for i, wc in enumerate(spec.get("walkway_crowds", [])):
        w = f"walkway_crowds[{i}]"
        if wc.get("path") not in path_names:
            err.append(f"{w}: path {wc.get('path')!r} is not in `paths`")
        if not wc.get("avatars"):
            err.append(f"{w}: needs `avatars` (a pool, e.g. 'ActorCore Crowd/Casual_F_E0001')")
        for a in wc.get("avatars", []):
            need("avatar", a, f"{w} avatar")
        for c in wc.get("clips", []):
            need("motion", c, f"{w} clip")
        if wc.get("direction", "both") not in ("front", "mostly_front", "both", "mostly_reverse", "reverse"):
            err.append(f"{w}: direction must be front, mostly_front, both, mostly_reverse or reverse")
        if not 0 < int(wc.get("width_cm", 150)) <= 1000:
            err.append(f"{w}: width_cm (per side of the path) must be 1-1000")
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
    for i, lt in enumerate(spec.get("lights", [])):
        w = f"lights[{i}] {lt.get('name')!r}"
        if lt.get("kind", "spot") not in ("spot", "point", "directional"):
            err.append(f"{w}: kind must be spot, point or directional")
        if lt.get("kind", "spot") != "directional" and not lt.get("position"):
            err.append(f"{w}: needs `position` [x,y,z] cm")
        if lt.get("kind", "spot") == "spot" and not (lt.get("aim_at") or lt.get("direction")):
            warn.append(f"{w}: a spot without aim_at/direction points straight down")
    env = spec.get("environment") or {}
    if env.get("ibl_image") and not os.path.isfile(os.path.expandvars(env["ibl_image"])):
        err.append(f"environment.ibl_image {env['ibl_image']!r} not found")

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
        pth = sh.get("path")
        if pth:
            if fr:
                err.append(f"{w}: give `frame` OR `path`, not both (the path re-keys the whole camera)")
            if bool(pth.get("points")) == bool(pth.get("orbit")):
                err.append(f"{w}: path needs `points` [[x,y,z], ...] (2+) OR `orbit` {{center, radius, from_deg, to_deg, height}}")
            elif pth.get("points") and (len(pth["points"]) < 2 or any(len(p) != 3 for p in pth["points"])):
                err.append(f"{w}: path.points needs 2+ [x, y, z] points")
            elif pth.get("orbit") and not ({"center", "radius"} <= set(pth["orbit"])):
                err.append(f"{w}: path.orbit needs center [x, y] and radius")
            t = pth.get("target")
            if t is None:
                err.append(f"{w}: path needs a `target` (person, set name or [x, y, z])")
            elif isinstance(t, str) and t not in named and t not in set_names:
                err.append(f"{w}: path target {t!r} is not a person or `set` name")
            if pth.get("timing", "ease") not in ("ease", "linear"):
                err.append(f"{w}: path.timing must be ease or linear")
        elif fr:
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
        fo = sh.get("focus")
        if fo:
            if fo.get("look", "shallow") not in ("shallow", "medium", "deep", "off"):
                err.append(f"{w}: focus.look must be shallow, medium, deep or off")
            for t in [fo.get("target")] + [k.get("target") for k in fo.get("keys", [])]:
                if isinstance(t, str) and t not in named and t not in set_names:
                    err.append(f"{w}: focus target {t!r} is not a person or `set` name")
            for k in fo.get("keys", []):
                if not s <= float(k.get("at_s", -1)) <= e:
                    err.append(f"{w}: focus key at_s {k.get('at_s')} is outside the shot {s}..{e}")
            if not fo.get("target") and not fo.get("keys") and fo.get("look") != "off":
                err.append(f"{w}: focus needs `target` or `keys` [{{at_s, target}}]")
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
