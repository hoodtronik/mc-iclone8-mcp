"""Lighting presets on the default three-light rig (Key / Side / Back directional lights of a new iClone project).
Tool: light_preset.
# CLAUDE-NOTE (2026-10-17): a new project carries directional lights Key (1.2, white), Side (0.8, cyan-ish), Back
# (1.0, blue) and 'Floor Shadow' (0). Re-aiming + recolouring them gives time-of-day looks for the beauty pass (AI video
# often uses the beauty frame as reference) without creating lights through the menu. Values are keyed at frame 0.
"""
import math
import os

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

# per light: (azimuth offset from the sun deg, elevation deg, multiplier, rgb). Key elevation = the preset's sun height.
PRESETS = {
    "day":         {"Key": (0, 50, 1.3, (1.0, 0.97, 0.92)), "Side": (130, 30, 0.45, (0.75, 0.85, 1.0)),
                    "Back": (180, 25, 0.6, (1.0, 1.0, 1.0))},
    "golden_hour": {"Key": (0, 12, 1.4, (1.0, 0.72, 0.42)), "Side": (130, 25, 0.3, (0.45, 0.55, 0.9)),
                    "Back": (180, 15, 0.9, (1.0, 0.65, 0.35))},
    "overcast":    {"Key": (0, 70, 0.7, (0.92, 0.95, 1.0)), "Side": (120, 45, 0.7, (0.9, 0.92, 0.95)),
                    "Back": (180, 40, 0.35, (0.9, 0.92, 0.95))},
    # CLAUDE-NOTE (2026-10-17): between golden_hour and night - sun at the horizon, warm low key, cool blue fill
    # (asked for by a weaker-agent trial; "dusk street" is a common previz beat).
    "dusk":        {"Key": (0, 8, 0.65, (1.0, 0.55, 0.38)), "Side": (130, 30, 0.35, (0.4, 0.45, 0.85)),
                    "Back": (180, 12, 0.6, (0.65, 0.5, 0.8))},
    "night":       {"Key": (0, 35, 0.35, (0.45, 0.55, 0.95)), "Side": (130, 30, 0.12, (0.3, 0.35, 0.6)),
                    "Back": (180, 25, 0.55, (0.55, 0.65, 1.0))},
}


SHADOW = {"day": 0.55, "golden_hour": 0.65, "overcast": 0.15, "dusk": 0.45, "night": 0.35}   # Floor Shadow darken strength


def sun_direction(azimuth_deg, elevation_deg):
    """Direction the light TRAVELS for a sun at azimuth (0 = sun on the -Y/camera side, 90 = on +X) and elevation."""
    a, e = math.radians(azimuth_deg), math.radians(elevation_deg)
    toward_sun = (math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))
    return tuple(-v for v in toward_sun)


def light_preset(args):
    from tools.icmcp_extra import _look_quaternion, _t
    preset = args.get("preset", "day")
    if preset not in PRESETS:
        raise ValueError(f"preset must be one of {sorted(PRESETS)}")
    sun_az = float(args.get("sun_azimuth_deg", 45.0))
    lights = {l.GetName(): l for l in RLPy.RScene.FindObjects(RLPy.EObjectType_Light)}
    missing = [n for n in PRESETS[preset] if n not in lights]
    if missing:
        raise ValueError(f"default rig lights {missing} not found (have {sorted(lights)}); this tool re-aims the stock "
                         f"Key/Side/Back lights of a new project")
    out = {}
    # CLAUDE-NOTE (2026-10-18): frame/clear_keys make a TIME-LAPSE: the first preset keys frame 0 (and clears), later
    # presets add keys at their frame and iClone interpolates direction, colour and strength between them. Stands in
    # for the Dynamic Sky (its Sky Prop Tool is a Content Manager download, not installed here; RISky has no API).
    frame = int(args.get("frame", 0))
    clear = bool(args.get("clear_keys", frame == 0))
    t0 = _t(frame)
    for name, (daz, elev, mult, rgb) in PRESETS[preset].items():
        if name == "Key" and args.get("sun_elevation_deg") is not None:
            elev = float(args["sun_elevation_deg"])
        L = lights[name]
        d = sun_direction(sun_az + daz, elev)
        q = _look_quaternion((0.0, 0.0, 0.0), d)                 # lights, like cameras, shine down their local -Z
        ctrl = L.GetControl("Transform")
        if clear:
            ctrl.ClearKeys()
        cur = L.LocalTransform()
        ctrl.SetValue(t0, RLPy.RTransform(cur.S(), q, cur.T()))
        k = float(args.get("intensity", 1.0))
        L.SetMultiplier(t0, mult * k)
        L.SetColor(t0, RLPy.RRgb(*rgb))
        out[name] = {"azimuth_deg": round((sun_az + daz) % 360, 1), "elevation_deg": elev, "multiplier": round(mult * k, 2),
                     "color": rgb}
    # CLAUDE-NOTE (2026-10-17, measured): the visible ground shadow comes from 'Floor Shadow' (multiplier 0, darken
    # strength 0.3) - Key casts with darken strength 0. Aim it along the sun and set its strength per look.
    fs = lights.get("Floor Shadow")
    if fs is not None:
        key_elev = out["Key"]["elevation_deg"]
        q = _look_quaternion((0.0, 0.0, 0.0), sun_direction(sun_az, key_elev))
        ctrl = fs.GetControl("Transform")
        if clear:
            ctrl.ClearKeys()
        cur = fs.LocalTransform()
        ctrl.SetValue(t0, RLPy.RTransform(cur.S(), q, cur.T()))
        strength = SHADOW.get(preset, 0.4)
        fs.SetDarkenShadowStrength(t0, strength)
        out["Floor Shadow"] = {"azimuth_deg": round(sun_az % 360, 1), "elevation_deg": key_elev, "shadow_strength": strength}
    return {"ok": True, "preset": preset, "frame": frame, "lights": out}


LIGHT_MENU = {"spot": "Create > Light > Spot Light", "point": "Create > Light > Point Light",
              "directional": "Create > Light > Directional Light"}


def quat_forward(x, y, z, w):
    """Local -Z rotated by the quaternion (x, y, z, w): where a light or camera points."""
    return (-2 * (x * z + w * y), -2 * (y * z - w * x), -(1 - 2 * (x * x + y * y)))


def _all_lights():
    seen = {}
    for t in (RLPy.EObjectType_Light, RLPy.EObjectType_SpotLight, RLPy.EObjectType_PointLight,
              RLPy.EObjectType_DirectionalLight):
        for o in RLPy.RScene.FindObjects(t):
            seen[o.GetID()] = o
    return seen


def add_light(args):
    """Create a NEW spot / point / directional light, place it, aim it and set colour, power, range and beam.
    # CLAUDE-NOTE (2026-10-18, measured): RLPy has no light constructor. RFileIO.LoadObject(Program/Default/
    # Def*Light.ilight) REPLACES every light in the scene (the stock Key/Side/Back rig vanished), so never use it to add
    # a light. iClone's own Create > Light > ... menu items add one light without touching the others.
    """
    from tools.icmcp_extra import _look_quaternion, _menu_action_for, _t
    kind = args.get("kind", "spot")
    if kind not in LIGHT_MENU:
        raise ValueError(f"kind must be one of {sorted(LIGHT_MENU)}")
    before = set(_all_lights())
    _menu_action_for(LIGHT_MENU[kind]).trigger()
    new = [o for i, o in _all_lights().items() if i not in before]
    if len(new) != 1:
        raise RuntimeError(f"expected one new light from {LIGHT_MENU[kind]!r}, got {len(new)}")
    L = new[0]
    if args.get("name"):
        L.SetName(args["name"])
    t0 = _t(0)
    pos = [float(v) for v in args.get("position", (0, 0, 300))]
    if args.get("aim_at") is not None:
        d = [float(a) - p for a, p in zip(args["aim_at"], pos)]
    else:
        d = [float(v) for v in args.get("direction", (0, 0, -1))]
    if math.sqrt(sum(v * v for v in d)) < 1e-6:
        raise ValueError("aim_at must differ from position")
    q = _look_quaternion((0.0, 0.0, 0.0), tuple(d))      # lights shine down their local -Z, like cameras
    ctrl = L.GetControl("Transform")
    ctrl.ClearKeys()
    ctrl.SetValue(t0, RLPy.RTransform(RLPy.RVector3(1, 1, 1), q, RLPy.RVector3(*pos)))
    rgb = args.get("color", (1.0, 1.0, 1.0))
    L.SetColor(t0, RLPy.RRgb(*[float(c) for c in rgb]))
    L.SetMultiplier(t0, float(args.get("multiplier", 1.0)))
    if kind != "directional" and args.get("range") is not None:
        L.SetRange(t0, float(args["range"]))
    if kind == "spot":
        L.SetSpotLightBeam(t0, float(args.get("spot_angle", 45)), float(args.get("spot_falloff", 20)),
                           float(args.get("spot_attenuation", 0)))
    if args.get("cast_shadow") is not None:
        L.SetCastShadow(bool(args["cast_shadow"]))
    # verify: world -Z of the light vs the wanted direction
    r = L.WorldTransform().R()
    fwd = quat_forward(r.x, r.y, r.z, r.w)
    n = math.sqrt(sum(v * v for v in d))
    err = math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b / n for a, b in zip(fwd, d))))))
    t = L.WorldTransform().T()
    return {"ok": err < 2.0, "name": L.GetName(), "kind": kind, "position": [round(t.x, 1), round(t.y, 1), round(t.z, 1)],
            "aim_error_deg": round(err, 2), "multiplier": L.GetMultiplier(), "lights_now": len(_all_lights())}


def environment_light(args):
    """Scene-wide light: IBL (image based lighting) and ambient colour via RIVisualSettingComponent.
    # CLAUDE-NOTE (2026-10-18, measured on the cafe, mean RGB of the lower frame): IBL off 164->136, ambient
    # (0.6,0.1,0.1) raised red 164->192, restoring the values restored the render exactly. LoadIBLImage replaces the
    # current IBL with no way back unless it was saved first, so `save_current_to` runs before any load.
    """
    v = RLPy.RGlobal.GetVisualSettingComponent()
    if args.get("save_current_to"):
        v.SaveIBLImage(os.path.abspath(args["save_current_to"]))
    if args.get("ibl_image"):
        p = os.path.abspath(args["ibl_image"])
        if not os.path.isfile(p):
            raise FileNotFoundError(f"IBL image not found: {p}")
        if v.LoadIBLImage(p) != RLPy.RStatus.Success:
            raise RuntimeError(f"iClone could not load IBL image {p}")
    if args.get("ibl_enable") is not None:
        v.SetIBLEnable(bool(args["ibl_enable"]))
    if args.get("sync_sky_image") is not None:
        v.SetIBLSyncSkyImage(bool(args["sync_sky_image"]))
    if args.get("sync_sky_orientation") is not None:
        v.SetIBLSyncSkyOrientation(bool(args["sync_sky_orientation"]))
    if args.get("ambient_color") is not None:
        v.SetAmbientColor(RLPy.RRgb(*[float(c) for c in args["ambient_color"]]))
    a = v.GetAmbientColor()
    return {"ok": True, "ibl_enable": v.IsIBLEnable(), "sync_sky_image": v.IsIBLSyncSkyImage(),
            "sync_sky_orientation": v.IsIBLSyncSkyOrientation(),
            "ambient_color": [round(a.R(), 3), round(a.G(), 3), round(a.B(), 3)]}


ATM_ROOTS = [os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Documents", "Reallusion", *p) for p in (
    ("Template", "iClone 7 Template", "iClone Template", "Atmosphere"), ("Reallusion Templates", "Stage", "Atmosphere"))]


def find_atmosphere(name, roots=None):
    """Path of an .iAtm look by file name (case-insensitive, with or without extension) or a full path."""
    if os.path.isfile(name):
        return name
    want = os.path.splitext(os.path.basename(name))[0].lower()
    hits, names = [], []
    for root in roots or ATM_ROOTS:
        for dp, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".iatm"):
                    names.append(os.path.splitext(f)[0])
                    if os.path.splitext(f)[0].lower() == want:
                        hits.append(os.path.join(dp, f))
    if not hits:
        import difflib
        close = difflib.get_close_matches(os.path.basename(name), names, n=5, cutoff=0.4)
        raise ValueError(f"no atmosphere {name!r}; close: {close or sorted(names)[:12]}")
    return hits[0]


def _visual_dock():
    from PySide2 import QtWidgets
    return next(w for w in QtWidgets.QApplication.instance().allWidgets()
                if isinstance(w, QtWidgets.QDockWidget) and w.windowTitle() == "Visual")


def _visual_state():
    from PySide2 import QtWidgets
    d = _visual_dock()
    spin = lambda n: d.findChild(QtWidgets.QWidget, n).findChild(QtWidgets.QSpinBox).value()
    box = lambda n: d.findChild(QtWidgets.QCheckBox, n).isChecked()
    return {"fog": box("qtFogOnCheckBox"), "fog_start": spin("qtDistanceStartCombospinbox"),
            "fog_end": spin("qtDistanceEndCombospinbox"), "toon": box("qtToonShaderCheckBox"), "gi": box("qtActivateGICheckBox"),
            "ambient_occlusion": box("qtAmbientOcclusionCheckBox"),
            "lights": sorted(L.GetName() for L in RLPy.RScene.FindObjects(RLPy.EObjectType_Light))}


def atmosphere_preset(args):
    """Load a whole-scene LOOK (.iAtm: lights + IBL + fog + post settings), then optional fog edits.
    # CLAUDE-NOTE (2026-10-18, measured on StreetVlog): RFileIO.LoadFile(IBL Mist.iAtm) REPLACED the 4 rig lights with
    # one 'Light01', changed the sky/IBL tone and set fog on 50-5500 - light_preset (needs Key/Side/Back) no longer
    # applies afterwards; add_light still adds. Fog/toon/GI/AO have no RLPy API; they are the Visual dock's widgets.
    # Unticking 'Fog on' after the load changed the render; on the stock atmosphere ticking it with start 0-300 / end
    # 400-2500 changed NOTHING (pixel-identical) - so fog is only trusted on top of a loaded atmosphere, and every
    # change must be checked with a render."""
    from PySide2 import QtWidgets
    out = {"before": _visual_state()}
    if args.get("preset"):
        path = find_atmosphere(args["preset"])
        if RLPy.RFileIO.LoadFile(path) != RLPy.RStatus.Success:
            raise RuntimeError(f"iClone could not load {path}")
        QtWidgets.QApplication.processEvents()
        out["loaded"] = path
    fog = args.get("fog")
    if fog is not None:
        d = _visual_dock()
        cb = d.findChild(QtWidgets.QCheckBox, "qtFogOnCheckBox")
        if "on" in fog and cb.isChecked() != bool(fog["on"]):
            cb.click()
        for key, wname in (("start", "qtDistanceStartCombospinbox"), ("end", "qtDistanceEndCombospinbox")):
            if key in fog:
                sp = d.findChild(QtWidgets.QWidget, wname).findChild(QtWidgets.QSpinBox)
                sp.setValue(int(fog[key])); sp.editingFinished.emit()
        QtWidgets.QApplication.processEvents()
    out["after"] = _visual_state()
    out["ok"] = True
    if out["before"]["lights"] != out["after"]["lights"]:
        out["note"] = "the atmosphere REPLACED the scene lights; light_preset needs Key/Side/Back and will not work now"
    return out


def register(registry):
    registry["atmosphere_preset"] = {
        "handler": atmosphere_preset, "main_thread": True,
        "description": "WHOLE-SCENE LOOK from a stock .iAtm (lights + IBL + fog + post): preset = file name, e.g. 'IBL Mist', "
                       "'Horror', 'Heaven', 'Sunset', 'Midday', 'IBL Blizzard', 'Charcoal' / 'Line Art' (toon), 'Ambient Soft', "
                       "'Sunrise Warm' (CC5 HD set), or a path. REPLACES every light in the scene (add_light after it; "
                       "light_preset no longer applies). Optional fog {on, start, end} via the Visual panel - check with a "
                       "render. Returns the Visual state before/after.",
        "inputSchema": {"type": "object", "properties": {
            "preset": {"type": "string"},
            "fog": {"type": "object", "properties": {"on": {"type": "boolean"}, "start": {"type": "integer"},
                                                     "end": {"type": "integer"}}}}}}
    registry["environment_light"] = {
        "handler": environment_light, "main_thread": True,
        "description": "SCENE-WIDE light: ibl_enable, ibl_image (.hdr; the stock one is Program Files/Reallusion/"
                       "iClone 8/Image/Default_IBL.hdr), sync_sky_image, sync_sky_orientation, ambient_color [r,g,b] "
                       "0-1 (fills shadows; a colour tints the whole frame). Pass save_current_to=<path.hdr> before "
                       "loading a new image - a load cannot be undone. No args = read the current state.",
        "inputSchema": {"type": "object", "properties": {
            "ibl_enable": {"type": "boolean"}, "ibl_image": {"type": "string"}, "save_current_to": {"type": "string"},
            "sync_sky_image": {"type": "boolean"}, "sync_sky_orientation": {"type": "boolean"},
            "ambient_color": {"type": "array", "items": {"type": "number"}}}}}
    registry["add_light"] = {
        "handler": add_light, "main_thread": True,
        "description": "CREATE a new light (kind spot | point | directional) through iClone's Create > Light menu (adds; "
                       "never replaces the rig) and set it up: name, position [x,y,z] cm, aim_at [x,y,z] or direction, "
                       "color [r,g,b] 0-1, multiplier, range cm (spot/point), spot_angle / spot_falloff / "
                       "spot_attenuation, cast_shadow. Keyed at frame 0. Returns aim_error_deg (ok < 2). Use for "
                       "practicals: a lamp pool, a window shaft, a streetlight.",
        "inputSchema": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": sorted(LIGHT_MENU)}, "name": {"type": "string"},
            "position": {"type": "array", "items": {"type": "number"}},
            "aim_at": {"type": "array", "items": {"type": "number"}},
            "direction": {"type": "array", "items": {"type": "number"}},
            "color": {"type": "array", "items": {"type": "number"}}, "multiplier": {"type": "number"},
            "range": {"type": "number"}, "spot_angle": {"type": "number"}, "spot_falloff": {"type": "number"},
            "spot_attenuation": {"type": "number"}, "cast_shadow": {"type": "boolean"}}}}
    registry["light_preset"] = {
        "handler": light_preset, "main_thread": True,
        "description": "LIGHTING LOOK on the stock Key/Side/Back directional lights: preset day | golden_hour | overcast | dusk | "
                       "night, sun_azimuth_deg (0 = sun behind the camera on -Y, 90 = from +X, 180 = backlight), "
                       "optional sun_elevation_deg and intensity scale. Keyed at frame 0 (clears old keys); for a TIME-LAPSE call again with "
                       "frame=N (keeps earlier keys) - iClone blends sun direction, colour and strength between. Verify with a render.",
        "inputSchema": {"type": "object", "properties": {
            "preset": {"type": "string", "enum": sorted(PRESETS)}, "sun_azimuth_deg": {"type": "number"},
            "sun_elevation_deg": {"type": "number"}, "intensity": {"type": "number"}, "frame": {"type": "integer"},
            "clear_keys": {"type": "boolean"}}}}
