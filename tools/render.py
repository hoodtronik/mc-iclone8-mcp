import RLPy


def get_render_settings(_args):
    """Return the output dimensions from iClone's current render settings."""
    result = RLPy.RGlobal.GetScreenSize(0, 0)
    if not isinstance(result, (tuple, list)) or len(result) < 3:
        raise RuntimeError("Unexpected response from iClone render settings")
    if result[0] != RLPy.RStatus.Success:
        raise RuntimeError("iClone could not read the render size")
    return {"width": int(result[1]), "height": int(result[2]), "note": "Other render options use the current iClone project settings."}


def render_video(args):
    """Native video render (iClone's own encoder). With output_path: renders [start_frame, end_frame] to that file at
    width x height (optional) and verifies it. Without: the old whole-project render with the current settings."""
    import os
    if not args.get("output_path"):
        if args.get("confirm") != "RENDER_VIDEO_WITH_CURRENT_SETTINGS":
            raise ValueError("Give output_path (+ start_frame/end_frame), or set confirm to RENDER_VIDEO_WITH_CURRENT_SETTINGS")
        # CLAUDE-NOTE (2026-10-16): sequence renders project with the viewport aspect (see icmcp_extra.
        # _viewport_matching_render_aspect). INFERRED for RenderVideo (not yet measured; it may use the video output size).
        from tools.icmcp_extra import _viewport_matching_render_aspect
        with _viewport_matching_render_aspect():
            result = RLPy.RGlobal.RenderVideo()
        if result != RLPy.RStatus.Success:
            raise RuntimeError("iClone could not start video rendering")
        return {"status": "started", "message": "iClone started rendering with the current project render settings."}
    # CLAUDE-NOTE (2026-10-18, measured): RenderVideo(RTime start, RTime end, path) is synchronous and honours
    # RExportVideoParameter.kCommon width/height set through SetRenderExportParameter: 832x480 mp4, 16 fps (the
    # parameter's kFps), 33 frames for project frames 300-360 at 30 fps, + an audio stream, in 3 s. Frames looked
    # unstretched. bAlphaOnly read back True but gave a solid white matte even with every prop hidden (an iSky is opaque).
    path = os.path.abspath(args["output_path"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fps = RLPy.RGlobal.GetFps()
    end_default = fps.GetFrameIndex(RLPy.RGlobal.GetProjectLength())
    start, end = int(args.get("start_frame", 0)), int(args.get("end_frame", end_default))
    if end <= start:
        raise ValueError("end_frame must be after start_frame")
    p = RLPy.RGlobal.GetRenderExportVideoParameter()
    p = p[0] if isinstance(p, (list, tuple)) else p
    c = p.kCommon
    if args.get("width"):
        c.nOutputSizeWidth = int(args["width"])
    if args.get("height"):
        c.nOutputSizeHeight = int(args["height"])
    if args.get("fps"):
        c.kFps = str(int(args["fps"]))
    p.kCommon = c
    if args.get("quality") is not None:
        p.nVideoQuality = int(args["quality"])
    RLPy.RGlobal.SetRenderExportParameter(p)     # returns Failure even when applied -> trust the read-back
    q = RLPy.RGlobal.GetRenderExportVideoParameter()
    q = q[0] if isinstance(q, (list, tuple)) else q
    if os.path.exists(path):
        os.remove(path)
    status = RLPy.RGlobal.RenderVideo(fps.IndexedFrameTime(start), fps.IndexedFrameTime(end), path)
    ok = status == RLPy.RStatus.Success and os.path.exists(path) and os.path.getsize(path) > 0
    return {"ok": ok, "path": path, "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
            "frames": [start, end], "format": q.strFormat, "fps": q.kCommon.kFps,
            "size": [q.kCommon.nOutputSizeWidth, q.kCommon.nOutputSizeHeight]}


def register(registry):
    registry["get_render_settings"] = {"handler": get_render_settings, "main_thread": True, "description": "Lit les dimensions des paramètres de rendu actuels d'iClone.", "inputSchema": {"type": "object", "properties": {}}}
    registry["render_video"] = {"handler": render_video, "main_thread": True, "timeout": 1800, "description": "Native VIDEO render (iClone encoder, mp4 by default) of the current camera / switch-camera cuts: output_path + start_frame/end_frame (project frames) + optional width/height/fps/quality; verifies the file. Fast (2 s of 832x480 in ~3 s). Without output_path it renders the whole project with current settings and needs confirm=RENDER_VIDEO_WITH_CURRENT_SETTINGS.", "inputSchema": {"type": "object", "properties": {"output_path": {"type": "string"}, "start_frame": {"type": "integer"}, "end_frame": {"type": "integer"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "fps": {"type": "integer"}, "quality": {"type": "integer"}, "confirm": {"type": "string", "description": "Only without output_path: RENDER_VIDEO_WITH_CURRENT_SETTINGS"}}}}
