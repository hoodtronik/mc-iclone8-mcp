"""Weather and atmosphere particles: rain, snow, blizzard, sand storm, aurora (stock .iParticle emitters).
Tool: add_weather.
# CLAUDE-NOTE (2026-10-18, measured on StreetVlog): RFileIO.LoadFile(Rain.iParticle) adds an RIParticle at the origin
# (scale 1). A single RenderImage still shows NO rain (particles simulate from frame 0); a RenderVideo of frames 0-120
# shows the streaks - image-sequence / video renders (previz passes) carry it. RIParticle only has GetEmit/SetEmit
# (keyed on/off); density and size live in the Modify panel. A transform scale key did not apply (read back 1.0).
# Visible at the default (origin) placement: Rain (faint streaks), Blizzard01 (clear flakes). Snow Flake01 showed
# nothing at the origin nor raised to z=350 - only the verified emitters are named kinds; others by file name.
"""
import os

try:
    import RLPy
except ImportError:          # offline tests import the pure helpers only
    RLPy = None

ENV_DIR = os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Documents", "Reallusion", "Template",
                       "iClone 7 Template", "iClone Template", "Particle", "Legacy", "Environment")
KINDS = {"rain": "Rain", "snow": "Blizzard01", "blizzard": "Blizzard01"}


def weather_file(kind, env_dir=ENV_DIR):
    """Stock emitter path for a kind ('rain', 'snow', ...) or an .iParticle file name / path."""
    if os.path.isfile(kind):
        return kind
    stem = KINDS.get(kind.lower(), kind)
    path = os.path.join(env_dir, stem if stem.lower().endswith(".iparticle") else stem + ".iParticle")
    if not os.path.isfile(path):
        have = sorted(os.path.splitext(f)[0] for f in os.listdir(env_dir)) if os.path.isdir(env_dir) else []
        raise ValueError(f"no weather {kind!r}; kinds {sorted(KINDS)} or one of {have}")
    return path


def add_weather(args):
    from tools.icmcp_extra import place_object
    path = weather_file(args.get("kind", "rain"))
    before = {o.GetID() for o in RLPy.RScene.FindObjects(RLPy.EObjectType_Particle)}
    RLPy.RScene.ClearSelectObjects()
    if RLPy.RFileIO.LoadFile(path) != RLPy.RStatus.Success:
        raise RuntimeError(f"iClone could not load {path}")
    new = [o for o in RLPy.RScene.FindObjects(RLPy.EObjectType_Particle) if o.GetID() not in before]
    if not new:
        raise RuntimeError("the particle file loaded but no new particle object appeared")
    p = new[-1]
    if args.get("name"):
        p.SetName(args["name"])
    at = args.get("at", [0, 0, 0])
    place_object({"name": p.GetName(), "frame": 0, "position": {"x": at[0], "y": at[1], "z": at[2] if len(at) > 2 else 0}})
    fps = RLPy.RGlobal.GetFps()
    F = fps.ToFloat() if hasattr(fps, "ToFloat") else 30.0
    keys = []
    if float(args.get("start_s", 0)) > 0:
        p.SetEmit(fps.IndexedFrameTime(0), False)
        keys.append([0, False])
    p.SetEmit(fps.IndexedFrameTime(int(round(float(args.get("start_s", 0)) * F))), True)
    keys.append([float(args.get("start_s", 0)), True])
    if args.get("stop_s") is not None:
        p.SetEmit(fps.IndexedFrameTime(int(round(float(args["stop_s"]) * F))), False)
        keys.append([float(args["stop_s"]), False])
    return {"ok": True, "name": p.GetName(), "file": os.path.basename(path), "at": at, "emit_keys": keys,
            "note": "particles only show in video / image-sequence renders (they simulate from frame 0), not in a single still"}


def register(registry):
    registry["add_weather"] = {
        "handler": add_weather, "main_thread": True,
        "description": "WEATHER particles from the stock emitters: kind rain (faint streaks) | snow / blizzard (clear "
                       "flakes), or another .iParticle name/path from Particle/Legacy/Environment (unverified: check a "
                       "render), at [x,y,z] (default origin = verified placement), start_s / stop_s (emitter keyed on/off), name. Shows in render_video / previz passes only - a single "
                       "render_snapshot still shows none.",
        "inputSchema": {"type": "object", "properties": {
            "kind": {"type": "string"}, "at": {"type": "array", "items": {"type": "number"}},
            "start_s": {"type": "number"}, "stop_s": {"type": "number"}, "name": {"type": "string"}}}}
