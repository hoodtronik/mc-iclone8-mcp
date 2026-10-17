"""Lighting presets on the default three-light rig (Key / Side / Back directional lights of a new iClone project).
Tool: light_preset.
# CLAUDE-NOTE (2026-10-17): a new project carries directional lights Key (1.2, white), Side (0.8, cyan-ish), Back
# (1.0, blue) and 'Floor Shadow' (0). Re-aiming + recolouring them gives time-of-day looks for the beauty pass (AI video
# often uses the beauty frame as reference) without creating lights through the menu. Values are keyed at frame 0.
"""
import math

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
    t0 = _t(0)
    for name, (daz, elev, mult, rgb) in PRESETS[preset].items():
        if name == "Key" and args.get("sun_elevation_deg") is not None:
            elev = float(args["sun_elevation_deg"])
        L = lights[name]
        d = sun_direction(sun_az + daz, elev)
        q = _look_quaternion((0.0, 0.0, 0.0), d)                 # lights, like cameras, shine down their local -Z
        ctrl = L.GetControl("Transform")
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
        ctrl.ClearKeys()
        cur = fs.LocalTransform()
        ctrl.SetValue(t0, RLPy.RTransform(cur.S(), q, cur.T()))
        strength = SHADOW.get(preset, 0.4)
        fs.SetDarkenShadowStrength(t0, strength)
        out["Floor Shadow"] = {"azimuth_deg": round(sun_az % 360, 1), "elevation_deg": key_elev, "shadow_strength": strength}
    return {"ok": True, "preset": preset, "lights": out}


def register(registry):
    registry["light_preset"] = {
        "handler": light_preset, "main_thread": True,
        "description": "LIGHTING LOOK on the stock Key/Side/Back directional lights: preset day | golden_hour | overcast | dusk | "
                       "night, sun_azimuth_deg (0 = sun behind the camera on -Y, 90 = from +X, 180 = backlight), "
                       "optional sun_elevation_deg and intensity scale. Keyed at frame 0. Verify with a render.",
        "inputSchema": {"type": "object", "properties": {
            "preset": {"type": "string", "enum": sorted(PRESETS)}, "sun_azimuth_deg": {"type": "number"},
            "sun_elevation_deg": {"type": "number"}, "intensity": {"type": "number"}}}}
