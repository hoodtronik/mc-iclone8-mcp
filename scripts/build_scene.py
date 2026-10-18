"""Build an iClone scene from a declarative JSON spec, stage by stage, verifying each stage. Made for agents: write a
spec (see examples/scenes/*.json and docs/SCENE_SPEC.md), run this, read the summary. Stdlib only; talks to the running
mc-iclone8-mcp server (scripts/icall.py).

  python scripts/build_scene.py examples/scenes/park_bench.json              # everything (discards the open scene!)
  python scripts/build_scene.py spec.json --stages cast,walks,qa             # selected stages on the open scene
  python scripts/build_scene.py spec.json --previz                           # + per-shot AI-video packages (slow)
  python scripts/build_scene.py spec.json --check                            # offline spec check only (no iClone)

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
               os.path.join(PUBLIC, "Template", "iClone 7 Template", "iClone Template", "MographMotion"),
               PUBLIC],              # catalog form "Reallusion Templates/Animation/..." (sit_clips.json)
    "prop": [os.path.join(PUBLIC, "Reallusion Templates", "Props", "Samples"),
             os.path.join(PUBLIC, "Reallusion Templates", "Props"),
             os.path.join(PUBLIC, "Template", "iClone 7 Template", "iClone Template", "Props")],
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
        exts = {"avatar": [".iAvatar"], "motion": [".rlMotion", ".iMotionPlus", ".iMotion"], "sky": [".iSky"],
                "prop": [".iProp"]}.get(kind, [])
        for c in [cand] + [cand + e for e in exts]:
            if os.path.isfile(c):
                return os.path.normpath(c)
    raise BuildError(f"{kind} file not found: {rel!r} (looked as given, next to the spec, and under {ROOTS.get(kind)})")


def vec(v, z=0.0):
    return {"x": float(v[0]), "y": float(v[1]), "z": float(v[2]) if len(v) > 2 else z}


def room_walls(name, w, d, h, at, doorways, t=10.0):
    """Box walls (each {name, size [x,y,z], at [x,y], bottom_z}) around a w x d interior centred on `at`, floor z 0.
    doorways: [{wall: -X|+X|-Y|+Y, center (cm along the wall from the room centre), width, height}] - that wall is
    split into the pieces left/right of the opening plus a lintel above it."""
    cx, cy = float(at[0]), float(at[1])
    walls = {"-Y": ("x", cy - d / 2.0 - t / 2.0, w + 2 * t), "+Y": ("x", cy + d / 2.0 + t / 2.0, w + 2 * t),
             "-X": ("y", cx - w / 2.0 - t / 2.0, d), "+X": ("y", cx + w / 2.0 + t / 2.0, d)}
    out = []
    for side, (along, fixed, length) in walls.items():
        c0 = cx if along == "x" else cy
        gaps = sorted((float(o.get("center", 0)) + c0, float(o.get("width", 100)), float(o.get("height", 215)))
                      for o in doorways if o.get("wall") == side)
        a, pieces = c0 - length / 2.0, []
        for gc, gw, gh in gaps:
            pieces.append((a, gc - gw / 2.0, 0.0, h))
            pieces.append((gc - gw / 2.0, gc + gw / 2.0, gh, h))          # lintel
            a = gc + gw / 2.0
        pieces.append((a, c0 + length / 2.0, 0.0, h))
        for i, (p0, p1, z0, z1) in enumerate(pieces):
            if p1 - p0 < 1.0 or z1 - z0 < 1.0:
                continue
            mid, ln = (p0 + p1) / 2.0, p1 - p0
            size = [ln, t, z1 - z0] if along == "x" else [t, ln, z1 - z0]
            xy = [mid, fixed] if along == "x" else [fixed, mid]
            out.append({"name": f"{name}_Wall{side}_{i}", "size": size, "at": xy, "bottom_z": z0})
    return out


def swing_keys(hinge, center, deg, steps):
    """[(fraction, (x, y), heading_deg)] for a door leaf whose pivot is at `center` swinging `deg` about a vertical
    hinge line at `hinge` - keyed along the arc (a linear position key between closed and open cuts the corner)."""
    out = []
    for i in range(steps + 1):
        f = i / float(steps)
        a = math.radians(deg * f)
        dx, dy = center[0] - hinge[0], center[1] - hinge[1]
        out.append((f, (hinge[0] + dx * math.cos(a) - dy * math.sin(a), hinge[1] + dx * math.sin(a) + dy * math.cos(a)),
                    deg * f))
    return out


def move_keys(item, fps):
    """set[].moves -> [(frame, x, y, z, turn)] transform keys: the rest pose at frame 0, then for every move a HOLD key at
    start_s (where the previous move left it) and the destination at end_s. Missing fields carry over."""
    x, y = item.get("at", [0, 0])[:2]
    z, turn = float(item.get("bottom_z", 0)), float(item.get("turn", 0))
    keys = [(0, x, y, z, turn)]
    for mv in sorted(item.get("moves", []), key=lambda m: m["start_s"]):
        f0, f1 = int(round(mv["start_s"] * fps)), int(round(mv["end_s"] * fps))
        if f0 > keys[-1][0]:
            keys.append((f0, x, y, z, turn))
        x, y = (mv.get("to") or [x, y])[:2]
        z, turn = float(mv.get("bottom_z", z)), float(mv.get("turn", turn))
        keys.append((f1, x, y, z, turn))
    return keys


def face_turn(x, y, focus):
    """`turn` (deg, CCW from above; 0 = facing -Y) that faces a person at (x, y) toward the point `focus`."""
    return math.degrees(math.atan2(focus[0] - x, -(focus[1] - y)))


def formation_points(kind, n, at, size=None, spacing=90.0, radius=None, arc_deg=180.0, facing_deg=0.0, seed=1):
    """Floor points (x, y) for `n` people. rows: a block of rows centred on `at`, the first row nearest the focus side
    (rows run across `facing_deg`, the direction the crowd looks); arc: on a circle of `radius` around `at` spanning
    `arc_deg` centred opposite `facing_deg` (an audience ring around a performer at `at`); scatter: random inside
    `size` [w, d] with at least `spacing` between people (seeded, so builds repeat)."""
    import random
    if kind == "rows":
        per = max(1, int(round(math.sqrt(n * 2))))              # wider than deep, like an audience
        rows = (n + per - 1) // per
        f = math.radians(facing_deg)
        fwd = (math.sin(f), -math.cos(f))                       # the way they look (turn 0 = -Y)
        side = (-fwd[1], fwd[0])
        pts = []
        for k in range(n):
            r, c = divmod(k, per)
            in_row = min(per, n - r * per)
            u = (c - (in_row - 1) / 2.0) * spacing + (spacing / 2.0 if r % 2 else 0.0)   # staggered rows see past
            v = ((rows - 1) / 2.0 - r) * spacing * 1.1
            pts.append((at[0] + side[0] * u + fwd[0] * v, at[1] + side[1] * u + fwd[1] * v))
        return pts
    if kind == "arc":
        rad = float(radius or max(150.0, n * spacing / math.radians(arc_deg)))
        back = math.radians(facing_deg) + math.pi                # the ring sits on the far side of the look direction
        pts = []
        for k in range(n):
            a = back + math.radians(arc_deg) * ((k + 0.5) / n - 0.5)
            pts.append((at[0] + rad * math.sin(a), at[1] - rad * math.cos(a)))
        return pts
    if kind == "scatter":
        w, d = (size or [600, 400])[:2]
        rnd = random.Random(seed)
        pts = []
        for _ in range(n * 400):
            if len(pts) == n:
                break
            p = (at[0] + (rnd.random() - 0.5) * w, at[1] + (rnd.random() - 0.5) * d)
            if all(math.hypot(p[0] - q[0], p[1] - q[1]) >= spacing for q in pts):
                pts.append(p)
        if len(pts) < n:
            raise BuildError(f"scatter: only {len(pts)} of {n} people fit in {w}x{d} cm at {spacing} cm spacing")
        return pts
    raise BuildError(f"formation {kind!r} unknown (rows, arc, scatter)")


def expand_crowds(spec):
    """Spec `crowds[]` -> ordinary `cast[]` members (a copy of the spec; the input is untouched).
    # CLAUDE-NOTE (2026-10-18): iClone's Crowd Generator (formation, focal points) is a panel driven by posted viewport
    # clicks (generate_crowd) and only scatters LIGHT actors. Audiences, queues and rings around a performer are laid
    # out here instead and built like any cast member, so seating, clips, look_at and hands all apply."""
    import copy
    import random
    if not spec.get("crowds"):
        return spec
    out = copy.deepcopy(spec)
    for ci, c in enumerate(spec["crowds"]):
        n = int(c.get("count", 6))
        at = c.get("at", [0, 0])
        focus = c.get("focus")
        kind = c.get("formation", "rows")
        fdeg = c.get("facing_deg")
        if fdeg is None:
            fdeg = face_turn(at[0], at[1], focus) if focus and kind == "rows" else 0.0
        if kind == "arc" and focus is None:
            focus = at                                      # a ring faces its centre
        pts = formation_points(kind, n, at, c.get("size"), float(c.get("spacing_cm", 90)), c.get("radius_cm"),
                               float(c.get("arc_deg", 180)), fdeg, int(c.get("seed", ci + 1)))
        rnd = random.Random(int(c.get("seed", ci + 1)))
        # `people` [{avatar, clip}] keeps each clip on a matching body (gendered Actor Group clips); else the
        # `avatars` and `clips` pools cycle independently
        pool = c.get("people") or [{"avatar": a} for a in c["avatars"]]
        clips = c.get("clips") or []
        for k, (x, y) in enumerate(pts):
            turn = face_turn(x, y, focus) if focus else float(fdeg)
            turn += (rnd.random() - 0.5) * 2.0 * float(c.get("jitter_deg", 8))
            who = pool[k % len(pool)]
            m = {"name": f"{c.get('name', 'Crowd')}{k + 1:02d}", "avatar": who["avatar"],
                 "place": {"at": [round(x, 1), round(y, 1), 0], "turn": round(turn, 1)}}
            clip = who.get("clip") or (clips[k % len(clips)] if clips else None)
            if clip:
                m["motion"] = {"clip": clip, "loop_to_end": True}
            out.setdefault("cast", []).append(m)
    out.pop("crowds")
    return out


class Builder:
    def __init__(self, spec, base_dir):
        spec = expand_crowds(spec)
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
        if self.s.get("render"):
            # output size/fps for the AI video model (e.g. 832x480 or 1280x720); frame_shot and the passes follow it
            ok(call("set_render_output", {k: self.s["render"][k] for k in ("width", "height", "fps") if k in self.s["render"]}),
               "render output")
        os.makedirs(self.out_dir, exist_ok=True)
        ok(call("save_project", {"path": self.project}), "save")
        return {"project": self.project, "fps": self.fps, "length_s": self.length_s}

    def set_stage(self):
        made = []
        for item in self.s.get("set", []):
            if item.get("room") and item.get("doorways"):
                made += self._doorway_room(item)
                continue
            if item.get("room"):
                # CLAUDE-NOTE (2026-10-17, measured): Create > Surface > Room = an inward-facing 957 cm cube (pivot bottom
                # centre); scale it to room [width, depth, height] cm. Use spec `interior` so shots stay inside.
                r = ok(call("menu_action", {"path": "Create > Surface > Room"}), "room")
                made_name = (r.get("added", {}).get("props") or ["Room"])[0]
                name = item.get("name", made_name)
                if name != made_name:
                    ok(call("rename_object", {"name": made_name, "new_name": name}), f"rename {made_name}")
                w, dpt, h = item["room"]
                at = item.get("at", [0, 0])
                py("import RLPy\no = RLPy.RScene.FindObject(RLPy.EObjectType_Prop, %r)\nc = o.GetControl('Transform')\n"
                   "c.ClearKeys()\nc.SetValue(RLPy.RTime.FromValue(0), RLPy.RTransform(RLPy.RVector3(%f, %f, %f), "
                   "RLPy.RQuaternion(RLPy.RVector4(0, 0, 0, 1)), RLPy.RVector3(%f, %f, 0)))"
                   % (name, w / 957.0, dpt / 957.0, h / 957.0, float(at[0]), float(at[1])))
                made.append(name)
                continue
            if item.get("asset"):
                # CLAUDE-NOTE (2026-10-17): real content props (stock .iProp: benches, buildings, cars...) beside the
                # primitives; placed by `at` (+ optional z), `turn` (deg about Z), uniform `scale`.
                py("import RLPy\nRLPy.RScene.ClearSelectObjects()")
                r = call("load_object", {"path": resolve("prop", item["asset"], self.base)})
                if r.get("status") != "ok":
                    raise BuildError(f"asset {item['asset']}: {r}")
                name = r["name"]
                if item.get("name") and item["name"] != name:
                    ok(call("rename_object", {"name": name, "new_name": item["name"]}), f"rename {name}")
                    name = item["name"]
                at = item.get("at", [0, 0])
                ok(call("place_object", {"name": name, "position": vec(at, float(item.get("bottom_z", 0))),
                                         "rotation_degrees": {"x": 0, "y": 0, "z": float(item.get("turn", 0))}}), f"place {name}")
                if item.get("scale"):
                    k = float(item["scale"])
                    py("import RLPy\no = RLPy.RScene.FindObject(RLPy.EObjectType_Prop, %r)\nc = o.GetControl('Transform')\n"
                       "t = o.LocalTransform()\nc.SetValue(RLPy.RTime.FromValue(0), RLPy.RTransform(RLPy.RVector3(%f, %f, %f), t.R(), t.T()))"
                       % (name, k, k, k))
                made.append(name)
                continue
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
        pivots = {}
        for it in self.s.get("set", []):
            if it.get("pivot") and not it.get("room"):
                # hinge / lid pivot (set_pivot): the object's position BECOMES the pivot point, so its moves start there
                r = ok(call("set_pivot", {"name": it["name"], "at": it["pivot"]}), f"pivot {it['name']}")
                pivots[it["name"]] = r["pivot"]
        moved = {}
        for it in self.s.get("set", []):
            if it.get("moves"):
                if it["name"] in pivots:
                    px, py_, pz = pivots[it["name"]]
                    it = dict(it, at=[px, py_], bottom_z=pz)
                moved[it["name"]] = self._move(it)
        return {"primitives": made, **({"pivots": pivots} if pivots else {}), **({"moves": moved} if moved else {})}

    def _move(self, item):
        """Key a set item's moves (a cart rolled in, a box slid along the counter, a door-less gate swung)."""
        # CLAUDE-NOTE (2026-10-18): keys go through place_object (frame-0 rule, clear_keys only on the first key) and every
        # key gets the move's transition (linear for constant speed, ease_in_out default). Verified by reading the world
        # position half way through each move.
        keys = move_keys(item, self.fps)
        trans = {}
        for mv in item["moves"]:
            trans[int(round(mv["end_s"] * self.fps))] = mv.get("transition", "ease_in_out")
            trans.setdefault(int(round(mv["start_s"] * self.fps)), mv.get("transition", "ease_in_out"))
        for i, (f, x, y, z, turn) in enumerate(keys):
            ok(call("place_object", {"name": item["name"], "frame": f, "clear_keys": i == 0,
                                     "position": {"x": x, "y": y, "z": z},
                                     "rotation_degrees": {"x": 0, "y": 0, "z": turn}}), f"move {item['name']}")
            if f in trans:
                ok(call("set_transform_key_transition", {"name": item["name"], "frame": f, "transition": trans[f]}),
                   f"transition {item['name']}")
        out = []
        for a, b in zip(keys, keys[1:]):
            if a[1:] == b[1:]:
                continue                                  # a hold segment
            mid = (a[0] + b[0]) // 2
            r = py("import RLPy\nfps = RLPy.RGlobal.GetFps()\nRLPy.RGlobal.SetTime(fps.IndexedFrameTime(%d))\n"
                   "RLPy.RGlobal.SetTime(fps.IndexedFrameTime(%d))\n"
                   "o = RLPy.RScene.FindObject(RLPy.EObjectType_Prop, %r)\nW = o.WorldTransform()\nT = W.T()\n"
                   "_result = [T.x, T.y, T.z]" % (mid + 1, mid, item["name"]))
            u = (mid - a[0]) / (b[0] - a[0])              # the integer mid frame, not the exact half way
            want = [a[i] + (b[i] - a[i]) * u for i in (1, 2, 3)]
            got = r or [0, 0, 0]
            out.append({"frames": [a[0], b[0]], "mid_error_cm": round(math.dist(got, want), 1)})
        return out

    def _box(self, name, size, at, bottom_z=0.0, color=None, visible=True):
        r = call("create_primitive", {"type": "box", "name": name, "position": vec(at, float(bottom_z)),
                                      "scale": {"x": size[0] / 100.0, "y": size[1] / 100.0, "z": size[2] / 100.0}})
        if r.get("status") != "ok":
            raise BuildError(f"primitive {name}: {r}")
        if color:
            call("set_timeline", {"frame": 0})
            ok(call("set_material_color", {"name": name, "color": {"r": color[0], "g": color[1], "b": color[2]}}),
               f"colour {name}")
        if not visible:
            self._show([name], False)
        return name

    def _doorway_room(self, item):
        # CLAUDE-NOTE (2026-10-18): iClone's Room surface cannot have openings, so a room with `doorways` is built from
        # boxes: a hidden interior-sized box under the room's name (so `interior` / `inside` framing keep working), a
        # floor slab reaching outside, walls split around each opening, an optional door leaf that swings on cue. No
        # ceiling unless asked (a closed box shades the stock sun). Walls are hidden during Motion Director takes.
        w, dpt, h = (float(v) for v in item["room"])
        at = item.get("at", [0, 0])
        name = item["name"]
        made = [self._box(name, [w, dpt, h], at, 0.0, visible=False)]
        m = float(item.get("outside_cm", 400))
        made.append(self._box(f"{name}_Floor", [w + 2 * m, dpt + 2 * m, 2], at, -2.0,
                              item.get("floor_color", [0.62, 0.6, 0.56])))
        wall_c = item.get("wall_color", [0.86, 0.84, 0.78])
        for wl in room_walls(name, w, dpt, h, at, item["doorways"]):
            made.append(self._box(wl["name"], wl["size"], wl["at"], wl["bottom_z"], wall_c))
        if item.get("ceiling"):
            made.append(self._box(f"{name}_Ceiling", [w + 20, dpt + 20, 6], at, h, wall_c))
        self.room_parts = getattr(self, "room_parts", []) + [n for n in made if n != name and not n.endswith("_Floor")]
        for i, dw in enumerate(item["doorways"]):
            if dw.get("door"):
                made.append(self._door_leaf(name, i, item, dw))
                self.room_parts.append(made[-1])            # a closed leaf blocks MD walkers (detoured 2.9 m)
        return made

    def _door_leaf(self, room, i, item, dw):
        w, dpt, _ = (float(v) for v in item["room"])
        cx, cy = (float(v) for v in item.get("at", [0, 0]))
        side, c = dw["wall"], float(dw.get("center", 0))
        gw, gh = float(dw.get("width", 100)), float(dw.get("height", 215))
        name = dw.get("name") or f"{room}_Door{i}"
        door = dw["door"] if isinstance(dw["door"], dict) else {}
        if side in ("-Y", "+Y"):
            y = cy + (dpt / 2.0 if side == "+Y" else -dpt / 2.0)
            center, hinge, size = (cx + c, y), (cx + c - gw / 2.0, y), [gw - 2, 4, gh - 1]
        else:
            x = cx + (w / 2.0 if side == "+X" else -w / 2.0)
            center, hinge, size = (x, cy + c), (x, cy + c - gw / 2.0), [4, gw - 2, gh - 1]
        far = door.get("hinge") == "far"
        if far:                                             # hinge on the other jamb
            hinge = (2 * center[0] - hinge[0], 2 * center[1] - hinge[1])
        self._box(name, size, list(center), 0.0, door.get("color", [0.42, 0.27, 0.15]))
        if door.get("open_at_s") is not None:
            # opens INTO the room: sign chosen so the leaf's free edge swings toward the interior
            inward = {"-Y": 1, "+Y": -1, "-X": -1, "+X": 1}[side] * (-1 if far else 1)
            t0, secs = float(door["open_at_s"]), float(door.get("seconds", 1.2))
            keys = [(t0 + secs * f, p[0], p[1], a) for f, p, a in swing_keys(hinge, center, inward * float(door.get("deg", 95)), 12)]
            code = ("import RLPy, math\n"
                    "o = RLPy.RScene.FindObject(RLPy.EObjectType_Prop, %r)\n"
                    "c = o.GetControl('Transform')\n"
                    "t = o.LocalTransform()\n"
                    "S = t.S()\n"
                    "for sec, x, y, a in %r:\n"
                    "    q = RLPy.RQuaternion()\n"
                    "    q.FromAxisAngle(RLPy.RVector3(0, 0, 1), math.radians(a))\n"
                    "    c.SetValue(RLPy.RTime.FromValue(int(round(sec * 6000))), RLPy.RTransform(S, q, RLPy.RVector3(x, y, 0)))\n"
                    % (name, keys))
            py(code)
        return name

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
            if m.get("actions"):
                # acting beats (idle -> turn -> step -> talk ...) chained with heading carry-over (perform_sequence)
                r = ok(call("perform_sequence", {"avatar": name, "actions": m["actions"], "trim": m.get("trim", "auto")}),
                       f"actions {name}")
                row["beats"] = len(r.get("placed", []))
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
                seat = next((it for it in self.s.get("set", []) if it.get("name") == m["sit_on"]), {})
                sitters = [c for c in self.s.get("cast", []) if c.get("sit_on") == m["sit_on"]]
                need = r.get("authored_seat_height_cm")
                if seat.get("fit_height") and seat.get("size") and len(sitters) == 1 and need and r.get("advice"):
                    # CLAUDE-NOTE (2026-10-18, CafeTrial): the seat height a clip needs depends on the avatar and
                    # can't be predicted offline (45 cm clip -> 54 cm for a 179 cm woman). A primitive seat marked
                    # `fit_height` takes the measured height, then the sitter is fitted again.
                    sz = [float(v) for v in seat["size"]]
                    sz[2] = need - float(seat.get("bottom_z", 0))
                    py("import RLPy\no = RLPy.RScene.FindObject(RLPy.EObjectType_Prop, %r)\nt = o.LocalTransform()\n"
                       "o.GetControl('Transform').SetValue(RLPy.RTime.FromValue(0), RLPy.RTransform(RLPy.RVector3(%f, %f, "
                       "%f), t.R(), t.T()))\nRLPy.RGlobal.SetTime(RLPy.RTime.FromValue(6000))\n"
                       "RLPy.RGlobal.SetTime(RLPy.RTime.FromValue(0))"
                       % (m["sit_on"], sz[0] / 100.0, sz[1] / 100.0, sz[2] / 100.0))
                    r = ok(call("fit_sitter", {"avatar": name, "seat": m["sit_on"], "mode": m.get("sit_mode", "seat"),
                                               "end_frame": int(self.length_s * self.fps), "samples": 16}), f"refit {name}")
                    r["seat_resized_to_cm"] = round(need, 1)
                row["sit"] = {k: r.get(k) for k in ("dz_cm", "authored_seat_height_cm", "sole_z_after", "advice",
                                                     "seat_resized_to_cm") if r.get(k) is not None}
            if m.get("hold"):
                # a hand prop (preset phone|cup|book stand-in, or an existing prop name) riding with the hand (hold_prop)
                h = m["hold"]
                r = ok(call("hold_prop", {"avatar": name, **{k: h[k] for k in ("prop", "preset", "hand", "offset_cm", "rotation_deg")
                                                               if k in h}}), f"hold {name}")
                row["hold"] = r.get("prop")
            if m.get("overlay"):
                row["overlay"] = self._overlays(m, name)
            for rc in m.get("reach", []):
                # hand contact via reach IK on top of the clip: touch / wipe / pick (hand_reach)
                r = ok(call("hand_reach", dict(rc, avatar=name)), f"reach {name}")
                row.setdefault("reach", []).append({"action": r.get("action"), "hand_to_target_cm": r.get("hand_to_target_cm")})
            if m.get("pose"):
                row["pose"] = self._poses(m, name)
            if m.get("hands"):
                row["hands"] = self._hands(m, name)
            for pn in m.get("pins", []):
                # planted foot/hand held still on top of everything above (pin_effector: reach target on a marker)
                r = ok(call("pin_effector", {"avatar": name, "effector": pn.get("effector", "left_foot"),
                                             "start_s": pn["at_s"], "end_s": pn["until_s"]}), f"pin {name}")
                row.setdefault("pins", []).append({k: r[k] for k in ("effector", "free_drift_cm", "pinned_drift_cm")})
            out.append(row)
        for m in self.s.get("cast", []):
            if m.get("look_at"):
                ok(call("set_look_at", {"avatar": m["name"], "target": m["look_at"], "frame": 0, "transition_frames": 0,
                                        "head_weight": 0.8, "body_weight": 0.2}), f"look {m['name']}")
        groups = []
        for g in self.s.get("groups", []):
            # CLAUDE-NOTE (2026-10-17): standing conversations - members on a ring facing its centre with their
            # (in-place) Actor Group clips (group_conversation); the layout is ours, the clips carry none.
            members = [{"avatar": self._load_avatar(m), **({"clip": resolve("motion", m["clip"], self.base)} if m.get("clip") else {})}
                       for m in g["members"]]
            r = ok(call("group_conversation", {"members": members, "at": g.get("at", [0, 0]),
                                               "until_s": float(g.get("until_s", self.length_s)),
                                               **{k: g[k] for k in ("radius_cm", "start_deg", "start_s") if k in g}}),
                   "group conversation")
            names = [m["avatar"] for m in r["members"]]
            looks = {n: m["look_at"] for n, m in zip(names, g["members"]) if m.get("look_at")}
            if len(names) == 2 and not looks:
                # CLAUDE-NOTE (2026-10-17, DuskStreet trial): Actor Group chat clips aim the gaze at an adult's head - a
                # father talking to a 120 cm girl looked over her head. A pair whose heights differ > 25 cm looks at
                # each other's head. Measured: head/body weight 0.8/0.2 left the girl 37-49 deg off (looking level); 1.0/0.4
                # brought both within ~11 deg of the other's head (dad without look-at: 37-43 deg off).
                h = py("import RLPy\nout = {}\nfor a in RLPy.RScene.GetAvatars():\n    mx, c, mn = RLPy.RVector3(), "
                       "RLPy.RVector3(), RLPy.RVector3()\n    a.GetBounds(mx, c, mn)\n    out[a.GetName()] = mx.z - mn.z\n"
                       "_result = out")
                if abs(h.get(names[0], 0) - h.get(names[1], 0)) > 25.0:
                    looks = {names[0]: names[1], names[1]: names[0]}
            for n, target in looks.items():
                ok(call("set_look_at", {"avatar": n, "target": target, "frame": 0, "transition_frames": 0,
                                        "head_weight": 1.0, "body_weight": 0.4}), f"look {n}")
            groups.append({"members": names, "min_hip_gap_cm": r.get("min_hip_gap_cm"),
                           **({"look_at": looks} if looks else {})})
        inter = []
        for it in self.s.get("interactions", []):
            # contact between two people via reach IK (no stock clips); currently: handshake
            if it.get("type", "handshake") != "handshake":
                raise BuildError(f"unknown interaction type {it.get('type')!r} (supported: handshake)")
            r = ok(call("handshake", {k: it[k] for k in ("a", "b", "at_s", "seconds", "shake") if k in it}),
                   f"handshake {it['a']}/{it['b']}")
            inter.append({"handshake": [it["a"], it["b"]], "hands_gap_cm": r.get("hands_gap_mid_hold_cm")})
        return {"cast": out, **({"groups": groups} if groups else {}), **({"interactions": inter} if inter else {})}

    def walks_stage(self):
        out, md = [], []
        for v in self.s.get("vehicles", []):
            # vehicles (any `set` prop) along a `paths` road at a constant speed (drive_path; stock cars face +Y)
            r = ok(call("drive_path", {"object": v["name"], "path": v["path"], "start_s": float(v.get("start_s", 0)),
                                       "speed_cm_s": float(v.get("speed_cm_s", 800)),
                                       **({"front_axis": v["front_axis"]} if v.get("front_axis") else {})}), f"drive {v['name']}")
            out.append({"name": v["name"], "mode": "drive", "speed_cm_s": r.get("measured_speed_cm_s"), "ok": r.get("ok")})
        for w in self.s.get("walkers", []):
            name = self._load_avatar(w)
            if w.get("follow"):
                # Motion Director FOLLOW OBJECT: walks after a moving person or prop, in the same take as its leader
                md.append({"avatar": name, "follow": w["follow"], "imd": w.get("imd", "male"), "start_frame": 0,
                           **{k: w[k] for k in ("distance_cm", "side_cm", "delay_s") if k in w},
                           **({"look_at": bool(w["look_at_leader"])} if "look_at_leader" in w else {})})
                continue
            if w.get("path"):                            # Motion Director on a path (natural, motion-matched)
                if not any(p["name"] == w["path"] for p in self.s.get("paths", [])):
                    raise BuildError(f"walker {name}: path {w['path']!r} is not in the spec's 'paths'")
                md.append({"avatar": name, "path": w["path"], "imd": w.get("imd", "male"),
                           "start_frame": int(round(float(w.get("start_s", 0)) * self.fps)),
                           **({"stop_at_end": w["stop_at_end"]} if "stop_at_end" in w else {}),
                           **({"arrive_clip": resolve("motion", w["arrive_clip"], self.base)} if w.get("arrive_clip") else {})})
            else:                                         # straight walk with chained root-motion clips
                args = {"avatar": name, "from": vec(w["from"]), "to": vec(w["to"]),
                        "start_frame": int(round(float(w.get("start_s", 0)) * self.fps)),
                        "speed_cm_s": float(w.get("pace_cm_s", 100)), "idle_after": bool(w.get("idle_after", False))}
                if w.get("motion"):
                    args["motion"] = resolve("motion", w["motion"], self.base)
                r = ok(call("walk_to", args), f"walk {name}")
                out.append({"name": name, "mode": "walk_to", "end_frame": r.get("end_frame"), "hip_error_cm": r.get("hip_error_cm")})
        for wc in self.s.get("walkway_crowds", []):
            # background people scattered ALONG a path given a width (Crowd Generator, light actors) with a clip pool
            # CLAUDE-NOTE (2026-10-18, measured): width is per side (250 -> actors up to 248 cm off the line); direction
            # front/reverse/both = who faces along the path. Light actors are only found by name via GetAvatars().
            pts = next(p["points"] for p in self.s["paths"] if p["name"] == wc["path"])
            self._camera_over(pts)
            r = ok(call("generate_crowd", {
                "actors": [resolve("avatar", a, self.base) for a in wc["avatars"]],
                "motions": [resolve("motion", m, self.base) for m in wc.get("clips", [])],
                "amount": int(wc.get("count", 8)), "spacing_cm": int(wc.get("spacing_cm", 120)),
                "region_path": wc["path"], "walkway_width_cm": int(wc.get("width_cm", 150)),
                "direction": wc.get("direction", "both")}, timeout=900), f"walkway crowd {wc['path']}")
            out.append({"name": f"walkway:{wc['path']}", "mode": "walkway_crowd", "deployed": r.get("deployed"),
                        "inside": r.get("inside_region"), "animated": r.get("animated_actors"), "ok": r.get("ok")})
        blocks = []
        for wz in self.s.get("wander", []):
            blocks.append({"zone": wz["zone"], "spacing_cm": float(wz.get("spacing_cm", 150)),
                           "avatars": [{"avatar": self._load_avatar(m), "imd": m.get("imd", "male")} for m in wz["people"]],
                           **({"settings": wz["settings"]} if wz.get("settings") else {})})
        if not (md or blocks):
            return {"walkers": out}
        # CLAUDE-NOTE (2026-10-16, plaza test): every MD character goes into ONE md_crowd take so path walkers and zone
        # wanderers avoid each other (separate takes walked through each other); zones are hidden before Start (a
        # visible zone slab made path walkers detour 2.5 m). MD walkers with different start_s keep their own takes via
        # md_walk_paths. The pick camera must see every path and zone at once.
        md.sort(key=lambda m: bool(m.get("follow")))      # leaders are prepared (placed, picked) before followers
        pts = [pt for p in self.s.get("paths", []) if p["name"] in {m.get("path") for m in md} for pt in p["points"]]
        for b in blocks:
            item = next((s for s in self.s.get("set", []) if s["name"] == b["zone"]), None)
            if item:
                x, y = item["at"]; sx, sy = item["size"][:2]
                pts += [[x - sx / 2, y - sy / 2], [x + sx / 2, y + sy / 2]]
        self._camera_over(pts)
        # CLAUDE-NOTE (2026-10-18, CafeTrial, measured): Motion Director treats visible props as obstacles; a walker
        # inside a `room` box turned in place and never left the door. Hide room surfaces for the takes (shown after).
        rooms = [it["name"] for it in self.s.get("set", []) if it.get("room") and it.get("name")]
        rooms += getattr(self, "room_parts", [])           # box walls of doorway rooms (and any door leaf stays)
        if rooms:
            self._show(rooms, False)
        try:
            res = self._md_takes(out, md, blocks)
        finally:
            if rooms:
                self._show(rooms, True)
        for w in self.s.get("walkers", []):
            if w.get("hold"):
                # a walker's hand prop rides the hand for the whole shot (hold_prop links at frame 0)
                h = w["hold"]
                r = ok(call("hold_prop", {"avatar": w["name"], **{k: h[k] for k in ("prop", "preset", "hand", "offset_cm",
                                                                                      "rotation_deg") if k in h}}),
                       f"hold {w['name']}")
                res.setdefault("holds", {})[w["name"]] = r.get("prop")
        for w in self.s.get("walkers", []):
            if w.get("overlay"):
                res.setdefault("overlays", {})[w["name"]] = self._overlays(w, w["name"])
            if w.get("pose"):
                res.setdefault("poses", {})[w["name"]] = self._poses(w, w["name"])
            if w.get("hands"):
                res.setdefault("hands", {})[w["name"]] = self._hands(w, w["name"])
        return res

    def _poses(self, member, name):
        # FK pose beats (pose_bones): additive yaw/pitch/roll about the body's axes, after overlays, before fingers
        rows = []
        for p in member["pose"]:
            r = ok(call("pose_bones", {"avatar": name, "bones": p["bones"],
                                       "start_frame": int(round(float(p.get("at_s", 0)) * self.fps)),
                                       "end_frame": int(round(float(p.get("until_s", self.length_s)) * self.fps)) - 1,
                                       **({"blend_s": p["blend_s"]} if "blend_s" in p else {})}), f"pose {name}")
            rows.append({k: v["measured_deg"] for k, v in r.get("bones", {}).items()})
        return rows

    def _hands(self, member, name):
        # CLAUDE-NOTE (2026-10-18): finger poses (hand_pose) go last - an arm overlay also keys the finger bones, and
        # one hand_pose call per hand holds all of that hand's poses (a second call would clear the first).
        rows = []
        for side in ("r", "l", "both"):
            segs = [{"pose": h["pose"], "start_frame": int(round(float(h.get("at_s", 0)) * self.fps)),
                     "end_frame": int(round(float(h.get("until_s", self.length_s)) * self.fps)) - 1}
                    for h in member["hands"] if h.get("hand", "r") == side]
            if segs:
                r = ok(call("hand_pose", {"avatar": name, "hand": side, "poses": segs}), f"hands {name}")
                rows.append({"hand": side, "poses": [s["pose"] for s in segs], "error_deg": r.get("max_error_deg")})
        return rows

    def _overlays(self, member, name):
        # CLAUDE-NOTE (2026-10-18): upper-body overlays (overlay_clip: motion-layer keys) run after the body's own
        # clips are final - walk takes, arrival clips, sit fits - since they are offsets from that motion.
        rows = []
        for o in member.get("overlay", []):
            f0 = int(round(float(o.get("at_s", 0)) * self.fps))
            f1 = int(round(float(o.get("until_s", self.length_s)) * self.fps)) - 1
            r = ok(call("overlay_clip", {"avatar": name, "clip": o["clip"], "start_frame": f0, "end_frame": f1,
                                         **{k: o[k] for k in ("bones", "blend_s", "clip_offset_s") if k in o}}),
                   f"overlay {name}")
            rows.append({"clip": r.get("clip"), "bones": r.get("bones"), "error_deg": r.get("max_error_deg")})
        return rows

    def _show(self, props, visible):
        py("import RLPy\nfor n in %r:\n    o = RLPy.RScene.FindObject(RLPy.EObjectType_Prop, n)\n"
           "    if o: o.SetVisible(RLPy.RTime.FromValue(0), %r)" % (list(props), bool(visible)))

    def _md_takes(self, out, md, blocks):
        # CLAUDE-NOTE (2026-10-17, EveningStreet): a take shorter than the scene left Leo snapping back to his start
        # (clips end -> base pose) at 13 s of a 16 s scene. MD takes cover the whole scene unless `seconds` says more.
        secs = max([float(w["seconds"]) for w in self.s.get("walkers", []) if w.get("seconds")] +
                   [float(wz.get("seconds", self.length_s)) for wz in self.s.get("wander", [])] + [self.length_s])
        together = [m for m in md if m["start_frame"] == 0]
        later = [m for m in md if m["start_frame"] != 0]
        if blocks or together:
            r = ok(call("md_crowd", {"walkers": together, "wander": blocks, **({"seconds": secs} if secs else {})},
                        timeout=900), "md crowd")
            for v in r["people"]:
                out.append({"name": v.get("avatar"), "mode": "wander" if "inside_zone" in v else "md",
                            "slide": v.get("slide_ratio"), "dev_cm": v.get("max_path_deviation_cm"),
                            "inside_zone": v.get("inside_zone"), "travel_cm": v.get("travel_cm"), "ok": v.get("ok"),
                            **({"follow_gap_cm": v["gap_cm"]} if v.get("gap_cm") else {})})
        if later:
            r = ok(call("md_walk_paths", {"walkers": later, **({"seconds": secs} if secs else {})}, timeout=900),
                   "md walkers")
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
        faces = []
        for fx in self.s.get("face", []):
            # facial performance (.iTalk expression clips) on the face track; combines with the lip-sync above
            r = ok(call("face_performance", {"avatar": fx["who"], "clips": [{k: fx[k] for k in ("clip", "at_s", "until_s")
                                                                           if k in fx}]}), f"face {fx['who']}")
            faces.append({"who": fx["who"], "clips": len(r.get("placed", []))})
        laughs = []
        for m in self.s.get("cast", []) + self.s.get("walkers", []):
            for lg in m.get("laugh", []):
                # CLAUDE-NOTE (2026-10-18): after face[] - loading expression clips later would replace the laugh keys
                r = ok(call("laugh", {"avatar": m["name"], "start_frame": int(round(float(lg.get("at_s", 0)) * self.fps)),
                                      **{k: lg[k] for k in ("seconds", "intensity", "face") if k in lg}}), f"laugh {m['name']}")
                laughs.append({"who": m["name"], "head_tilt_peak_deg": r.get("head_tilt_peak_deg")})
        return {"lines": out, **({"faces": faces} if faces else {}), **({"laughs": laughs} if laughs else {})}

    def sky_stage(self):
        out = {"sky": None}
        if self.s.get("sky"):
            sky = resolve("sky", self.s["sky"], self.base)    # load_object fails on skies; LoadFile replaces the scene sky
            py("import RLPy\nRLPy.RScene.ClearSelectObjects()\nRLPy.RFileIO.LoadFile(r'%s')" % sky, silent=True)
            out["sky"] = os.path.basename(sky)
        if self.s.get("atmosphere"):
            # a stock .iAtm look (atmosphere_preset): replaces every light, so it comes before `lights` and never
            # together with `lighting` (spec_check refuses that pair)
            at = self.s["atmosphere"]
            at = {"preset": at} if isinstance(at, str) else dict(at)
            r = ok(call("atmosphere_preset", at), "atmosphere")
            out["atmosphere"] = {"preset": at.get("preset"), **{k: r["after"][k] for k in ("fog", "toon", "lights")}}
        if self.s.get("lighting"):
            # time-of-day look on the stock Key/Side/Back/Floor Shadow lights (light_preset)
            lt = self.s["lighting"]
            if isinstance(lt, list):
                # time-lapse: one preset per beat, keyed at its at_s, iClone blends between (first one at frame 0)
                for i, beat in enumerate(sorted(lt, key=lambda b: b.get("at_s", 0))):
                    args = {k: v for k, v in beat.items() if k != "at_s"}
                    args["frame"] = 0 if i == 0 else int(round(float(beat["at_s"]) * self.fps))
                    args["clear_keys"] = i == 0
                    ok(call("light_preset", args), f"lighting {beat.get('preset')}")
                out["lighting"] = [b.get("preset", "day") for b in lt]
            else:
                ok(call("light_preset", dict(lt)), "lighting")
                out["lighting"] = lt.get("preset", "day")
        if self.s.get("environment"):
            # scene-wide IBL / ambient colour (environment_light)
            ok(call("environment_light", dict(self.s["environment"])), "environment")
        for lt in self.s.get("lights", []):
            # practical lights added through Create > Light (add_light): lamp pools, window shafts, streetlights
            r = ok(call("add_light", dict(lt)), f"light {lt.get('name', lt.get('kind'))}")
            out.setdefault("lights", []).append({"name": r.get("name"), "aim_error_deg": r.get("aim_error_deg")})
        for w in self.s.get("weather", []):
            # rain / snow emitters (add_weather); they show in the previz sequences, not in single stills
            r = ok(call("add_weather", dict(w)), f"weather {w.get('kind')}")
            out.setdefault("weather", []).append(r.get("name"))
        return out

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
                        if self.s.get("interior") and "inside" not in fa:
                            fa["inside"] = self.s["interior"]                   # keep interior cameras within the room
                        fa.pop("track", None)                                    # tracking keys come after build_shot_list
                        if key == "frame" and not sh.get("end_frame") and not sh[key].get("track"):
                            # static shot: keep subjects framed throughout
                            fa["through_frame"] = int(round(sh["end_s"] * self.fps)) - 1
                        r = ok(call("frame_shot", fa), f"frame {sh['id']}")
                        if r.get("fit_error", 0) > 0.3:
                            print(f"  WARN {sh['id']}: no clean over-the-shoulder for this staging (fit_error "
                                  f"{r['fit_error']}); try the other shoulder, another subject or a sized shot", flush=True)
                        pre = "" if key == "frame" else "end_"
                        sh = dict(sh, **{pre + "position": r["position"], pre + "target": r["target"], pre + "lens_mm": r["lens_mm"]})
                if sh.get("path") and not sh.get("position"):
                    # placeholder pose for build_shot_list; camera_path re-keys the whole move below
                    pth = sh["path"]
                    if pth.get("orbit"):
                        o = pth["orbit"]
                        a = math.radians(float(o.get("from_deg", 0)))
                        first = [o["center"][0] + o["radius"] * math.sin(a), o["center"][1] - o["radius"] * math.cos(a),
                                 o.get("height", 160)]
                    else:
                        first = pth["points"][0]
                    tgt = pth["target"] if isinstance(pth["target"], list) else [first[0], first[1] + 100, first[2]]
                    sh = dict(sh, position=first, target=tgt)
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
            for sh in self.s["shots"]:
                if (sh.get("frame") or {}).get("track"):
                    # moving camera: re-key the shot's camera every track_step_s (frame_shot track=follow|pan)
                    # CLAUDE-NOTE (2026-10-18, CafeTrial): the tracking re-solve also needs `inside`, else the follow
                    # camera left the room (it framed the walker's back from beside the door).
                    extra = {"inside": self.s["interior"]} if self.s.get("interior") and "inside" not in sh["frame"] else {}
                    r = ok(call("frame_shot", dict(sh["frame"], **extra, camera=sh["id"], make_current=False,
                                                   frame=int(round(sh["start_s"] * self.fps)),
                                                   through_frame=int(round(sh["end_s"] * self.fps)) - 1)), f"track {sh['id']}")
                    out.setdefault("tracking", {})[sh["id"]] = len(r.get("keys", []))
            for sh in self.s["shots"]:
                if sh.get("path"):
                    # curved / orbiting camera move, re-aimed at the target every key (camera_path)
                    pth = sh["path"]
                    r = ok(call("camera_path", {"camera": sh["id"], "target": pth["target"], "start_s": sh["start_s"],
                                                "end_s": sh["end_s"] - 1.0 / self.fps,
                                                **{k: pth[k] for k in ("points", "orbit", "timing", "step_s", "roll_degrees") if k in pth},
                                                **({"lens_mm": float(sh["lens_mm"])} if sh.get("lens_mm") else {})}),
                           f"path {sh['id']}")
                    out.setdefault("paths", {})[sh["id"]] = {"aim_error_deg": r["max_aim_error_deg"],
                                                             "length_cm": r["path_length_cm"]}
            for sh in self.s["shots"]:
                if sh.get("focus"):
                    # depth of field on the shot camera: one target, or rack focus keys [{at_s, target}] (focus_on)
                    fo = sh["focus"]
                    keys = [{"frame": int(round(float(k["at_s"]) * self.fps)), "target": k["target"]}
                            for k in fo.get("keys", [])] or [{"frame": int(round(sh["start_s"] * self.fps)),
                                                              "target": fo.get("target")}]
                    follow = {} if fo.get("keys") else {"through_frame": int(round(sh["end_s"] * self.fps)) - 1}
                    r = ok(call("focus_on", {"camera": sh["id"], "keys": keys, **follow,
                                             **{k: fo[k] for k in ("look", "range", "transition", "blur") if k in fo}}),
                           f"focus {sh['id']}")
                    out.setdefault("focus", {})[sh["id"]] = [k["focus_cm"] for k in r.get("keys", [])]
        looks = self._looks()
        if looks:
            out["looks"] = looks
        py("import RLPy\nfor c in list(RLPy.RScene.GetCameras()):\n    if c.GetName().startswith('_build_'): RLPy.RScene.RemoveObject(c)")
        ok(call("save_project", {}), "save")
        return out

    def _looks(self):
        """cast[].looks: timed glances [{target, at_s, until_s}] at a person (head), a set prop or a shot id (that shot's
        camera = a look into the lens). Keyed here because the shot cameras only exist after build_shot_list."""
        # CLAUDE-NOTE (2026-10-18): live: set_look_at object mode on a camera locks the EYES on the lens (0.5-3.6 deg)
        # while the head turns ~67 deg and stops 24-35 deg short (look-at weights); the render shows eye contact. After
        # until_s the head goes back to the member's static look_at, or is released.
        out = {}
        for m in self.s.get("cast", []):
            for lk in m.get("looks", []):
                r = ok(call("set_look_at", {"avatar": m["name"], "target": lk["target"],
                                            "frame": int(round(float(lk["at_s"]) * self.fps)), "transition_frames": 12,
                                            "head_weight": 0.8, "body_weight": 0.2}), f"look {m['name']}")
                out.setdefault(m["name"], []).append({"target": lk["target"], "head_turn_deg": r.get("head_turn_deg")})
                if lk.get("until_s") is not None:
                    back = {"target": m["look_at"]} if m.get("look_at") else {"release": True}
                    ok(call("set_look_at", {"avatar": m["name"], **back, "transition_frames": 12,
                                            "frame": int(round(float(lk["until_s"]) * self.fps))}), f"look back {m['name']}")
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
            extra = {k: v for k, v in (self.s.get("previz") or {}).items() if k in ("passes", "bFace", "bHand", "gizmo_scale")}
            if self.s.get("render", {}).get("width") and self.s.get("render", {}).get("height"):
                extra.update(width=self.s["render"]["width"], height=self.s["render"]["height"])
            r = ok(call("previz_export", {"start_frame": s, "end_frame": e, "camera": sh["id"], "return_image": False, **extra,
                                          "output_dir": os.path.join(self.out_dir, "previz", sh["id"])}, timeout=3600), f"previz {sh['id']}")
            shot_dir = os.path.join(self.out_dir, "previz", sh["id"])
            if sh.get("prompt") or self.s.get("style"):
                # text for the AI video model next to its conditioning passes (shot prompt + scene-wide style)
                text = " ".join(t for t in (sh.get("prompt", ""), self.s.get("style", "")) if t).strip()
                with open(os.path.join(shot_dir, "prompt.txt"), "w", encoding="utf-8") as fh:
                    fh.write(text + "\n")
                man = os.path.join(shot_dir, "manifest.json")
                if os.path.isfile(man):
                    with open(man, encoding="utf-8") as fh:
                        m = json.load(fh)
                    m.update(prompt=text, shot=sh["id"], start_s=sh["start_s"], end_s=sh["end_s"])
                    with open(man, "w", encoding="utf-8") as fh:
                        json.dump(m, fh, indent=1)
            out.append({"shot": sh["id"], "frames": r.get("frames_per_pass"), "check_sheet": r.get("check_sheet")})
        res = {"previz": out}
        try:
            from reel import build_reel           # watchable videos: one edit + passes side by side (scripts/reel.py)
            res["reel"] = build_reel(self.s, self.out_dir)["index"]
        except (RuntimeError, OSError) as e:
            res["reel_error"] = str(e)[:200]
        return res

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
    ap.add_argument("--check", action="store_true", help="only check the spec offline (files, names, times) and exit")
    a = ap.parse_args(argv)
    spec_path = os.path.abspath(a.spec)
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    # CLAUDE-NOTE (2026-10-18): every build starts with the offline spec check (spec_check.py), so a wrong clip or name
    # fails in a second with suggestions instead of minutes into the build.
    from spec_check import check
    errors, warnings = check(spec, os.path.dirname(spec_path))
    for w in warnings:
        print("WARN ", w, flush=True)
    for e in errors:
        print("ERROR", e, file=sys.stderr, flush=True)
    if a.check or errors:
        print(f"spec check: {len(errors)} error(s), {len(warnings)} warning(s)", flush=True)
        return 1 if errors else 0
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
