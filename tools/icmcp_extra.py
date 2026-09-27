"""hoodtronik fork additions to gorbabor/mc-iclone8-mcp (registered at the end of main._tool_registry).
Tools: python_exec (probe/iterate RLPy live) · render_control_pass (OpenPose / Depth / Normal / Canny image sequences).
# CLAUDE-NOTE (2026-09-26): separate module (one registration line in main.py) so upstream merges stay trivial.
# render signatures: OpenPose = (RTime start, RTime end, ROpenPoseKeyPointParam, str path) — proven 2026-08-29 via TypeError.
# Depth/Normal/Canny are ASSUMED to take (start, end, path); on TypeError we return the prototype text instead of guessing.
"""
import contextlib, io, os, traceback

import RLPy

_NS = {"RLPy": RLPy, "__name__": "icmcp_exec"}


def python_exec(args):
    """Run Python inside iClone (main thread). Set _result to return a value; stdout is captured."""
    out = io.StringIO()
    _NS.pop("_result", None)
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(args.get("code", ""), "<icmcp>", "exec"), _NS)
    except Exception:
        return {"ok": False, "stdout": out.getvalue(), "error": traceback.format_exc()}
    res = _NS.get("_result")
    try:
        import json
        json.dumps(res)
    except Exception:
        res = repr(res)
    return {"ok": True, "stdout": out.getvalue(), "result": res}


_PASSES = {"openpose": "RenderImageSequenceOpenPoseKeyPoint", "depth": "RenderImageSequenceDepth",
           "normal": "RenderImageSequenceNormal", "canny": "RenderImageSequenceCanny"}


def render_control_pass(args):
    kind = args["pass"].lower()
    fn = getattr(RLPy.RGlobal, _PASSES[kind])
    fps = RLPy.RGlobal.GetFps()
    t0, t1 = fps.IndexedFrameTime(int(args["start_frame"])), fps.IndexedFrameTime(int(args["end_frame"]))
    path = args["output_path"]
    os.makedirs(os.path.dirname(path) if os.path.splitext(path)[1] else path, exist_ok=True)
    before = set(os.listdir(os.path.dirname(path) if os.path.splitext(path)[1] else path))
    try:
        if kind == "openpose":
            p = RLPy.ROpenPoseKeyPointParam()
            for k in ("bFace", "bHand"):
                if k in args:
                    setattr(p, k, bool(args[k]))
            status = fn(t0, t1, p, path)
        else:
            status = fn(t0, t1, path)
    except TypeError as e:
        return {"ok": False, "error": "signature mismatch — prototype from iClone: " + str(e)}
    folder = os.path.dirname(path) if os.path.splitext(path)[1] else path
    new = sorted(set(os.listdir(folder)) - before)
    return {"ok": bool(new), "status": repr(status), "files_written": len(new), "first": new[:3], "folder": folder}


def register(registry):
    registry["python_exec"] = {"handler": python_exec, "main_thread": True,
                               "description": "Run Python inside iClone 8 (RLPy imported; persistent namespace). Set _result to return a value.",
                               "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}
    registry["render_control_pass"] = {"handler": render_control_pass, "main_thread": True,
                                       "description": "Render an OpenPose / Depth / Normal / Canny image sequence for a frame range (render size = project settings). Verifies files were written.",
                                       "inputSchema": {"type": "object", "properties": {
                                           "pass": {"type": "string", "enum": list(_PASSES)},
                                           "start_frame": {"type": "integer"}, "end_frame": {"type": "integer"},
                                           "output_path": {"type": "string", "description": "folder or file path prefix"},
                                           "bFace": {"type": "boolean"}, "bHand": {"type": "boolean"}},
                                           "required": ["pass", "start_frame", "end_frame", "output_path"]}}
