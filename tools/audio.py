import os

import RLPy

from tools.common import frame_time, require_success


def _target(name):
    if not name:
        raise ValueError("name is required")
    for object_type in (RLPy.EObjectType_Prop, RLPy.EObjectType_Avatar):
        obj = RLPy.RScene.FindObject(object_type, name)
        if obj is not None:
            return obj
    raise ValueError("Audio can only be attached to a prop or avatar: %s" % name)


def load_audio_to_object(args):
    """Attach a WAV/MP3 file to a prop or avatar sound track."""
    path = os.path.abspath(args["audio_path"])
    if not os.path.isfile(path):
        raise FileNotFoundError("Audio file not found: %s" % path)
    if os.path.splitext(path)[1].lower() not in (".wav", ".mp3"):
        raise ValueError("The official LoadAudioToObject API supports WAV and MP3 files")
    target = _target(args["name"])
    start = frame_time(int(args.get("start_frame", 0)))
    loop_count = int(args.get("loop_count", 1))
    if loop_count < 1:
        raise ValueError("loop_count must be at least 1")
    method = getattr(RLPy.RAudio, "LoadAudioToObject", None)
    if method is None:
        raise RuntimeError("LoadAudioToObject is not exposed by this iClone 8 build")
    optional = any(key in args for key in ("fade_in_seconds", "fade_out_seconds", "cut_length_seconds")) or loop_count != 1
    if optional:
        fade_in = RLPy.RTick.FromSecond(float(args.get("fade_in_seconds", 0)))
        fade_out = RLPy.RTick.FromSecond(float(args.get("fade_out_seconds", 0)))
        cut_length = RLPy.RTick.FromSecond(float(args.get("cut_length_seconds", 0)))
        duration = method(target, path, start, loop_count, fade_in, fade_out, cut_length)
    else:
        duration = method(target, path, start)
    duration = float(duration)
    if duration <= 0:
        raise RuntimeError("iClone could not load audio onto %s" % target.GetName())
    return {"status": "ok", "name": target.GetName(), "audio_path": path, "start_frame": int(args.get("start_frame", 0)), "duration_seconds": duration, "loop_count": loop_count}


def load_audio_source(args):
    """Validate and load an audio source without attaching it to the scene."""
    path = os.path.abspath(args["audio_path"])
    if not os.path.isfile(path):
        raise FileNotFoundError("Audio file not found: %s" % path)
    audio = RLPy.RAudio.CreateAudioObject()
    require_success(audio.Load(path), "iClone could not load the audio source")
    if not audio.HasData():
        raise RuntimeError("The audio source contains no data")
    return {"status": "ok", "audio_path": path, "has_data": True, "note": "The audio source is prepared in iClone; use load_audio_to_object to place it on a prop or avatar."}


def register(registry):
    registry["load_audio_to_object"] = {"handler": load_audio_to_object, "main_thread": True, "description": "Ajoute un fichier WAV/MP3 à la piste audio d’un prop ou avatar via l’API RAudio officielle.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "audio_path": {"type": "string"}, "start_frame": {"type": "integer", "minimum": 0}, "loop_count": {"type": "integer", "minimum": 1}, "fade_in_seconds": {"type": "number", "minimum": 0}, "fade_out_seconds": {"type": "number", "minimum": 0}, "cut_length_seconds": {"type": "number", "minimum": 0}}, "required": ["name", "audio_path"]}}
    registry["load_audio_source"] = {"handler": load_audio_source, "main_thread": True, "description": "Charge et valide une source audio WAV/MP3 sans la placer sur un objet.", "inputSchema": {"type": "object", "properties": {"audio_path": {"type": "string"}}, "required": ["audio_path"]}}
