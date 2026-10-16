"""Previz export for AI video: one call renders the conditioning package for a shot.
Tools: previz_export (beauty + OpenPose + depth [+ normal, canny] per-pass folders, MP4s, manifest, check sheet).
# CLAUDE-NOTE (2026-10-16): the MCP's primary purpose (user) is previz that DRIVES AI video, so the deliverable is an
# aligned, same-length set of passes an AI pipeline (ControlNet / video models) can consume without hand fixing.
# Built on render_control_pass, which carries the measured fixes (OpenPose viewport aspect, overwrite modal, prefixes).
"""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

import RLPy

from tools.icmcp_extra import _render_size, _win, render_control_pass

DEFAULT_PASSES = ["beauty", "openpose", "depth"]


def _ffmpeg():
    """iClone ships ffmpeg.exe next to iClone.exe (Bin64); fall back to PATH."""
    here = os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe")
    return here if os.path.isfile(here) else shutil.which("ffmpeg")


def _frames(folder, prefix):
    pat = re.compile(r"^%s_(\d+)\.png$" % re.escape(prefix), re.I)
    out = []
    for f in os.listdir(folder):
        m = pat.match(f)
        if m:
            out.append((int(m.group(1)), f))
    return sorted(out)


def _encode(ffmpeg, folder, prefix, first, fps, mp4):
    # OpenPose frames are RGBA with a transparent background; flatten onto black (what pose ControlNets expect).
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps), "-start_number", str(first),
           "-i", os.path.join(folder, prefix + "_%05d.png"),
           "-vf", "format=rgba,premultiply=inplace=1,format=yuv420p", "-c:v", "libx264", "-crf", "16", mp4]
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode == 0 and os.path.isfile(mp4), (r.stderr or "")[-300:]


def _check_sheet(out_dir, passes, mid_files):
    """Middle frame of every pass side by side + an OpenPose-over-beauty overlay (alignment check)."""
    from PIL import Image
    tiles, labels = [], []
    for p in passes:
        if p in mid_files:
            im = Image.open(mid_files[p]).convert("RGBA")
            bg = Image.new("RGBA", im.size, (0, 0, 0, 255)); bg.alpha_composite(im)
            tiles.append(bg.convert("RGB")); labels.append(p)
    if "beauty" in mid_files and "openpose" in mid_files:
        b = Image.open(mid_files["beauty"]).convert("RGBA")
        o = Image.open(mid_files["openpose"]).convert("RGBA").resize(b.size)
        b.alpha_composite(o); tiles.append(b.convert("RGB")); labels.append("openpose over beauty")
    from tools.scene_qa import contact_sheet
    sheet = contact_sheet(tiles, labels, cols=2, tile_width=640)
    path = os.path.join(out_dir, "check_sheet.png")
    sheet.save(path)
    buf = io.BytesIO(); sheet.save(buf, "PNG")
    return path, base64.b64encode(buf.getvalue()).decode("ascii")


def previz_export(args):
    s, e = int(args["start_frame"]), int(args["end_frame"])
    if e <= s:
        raise ValueError("end_frame must be > start_frame")
    passes = [p.lower() for p in (args.get("passes") or DEFAULT_PASSES)]
    out_dir = _win(args["output_dir"])
    os.makedirs(out_dir, exist_ok=True)
    cam_name = args.get("camera") or RLPy.RScene.GetCurrentCamera().GetName()
    t0 = time.time()
    results, counts, mid_files = {}, {}, {}
    for p in passes:
        folder = os.path.join(out_dir, p)
        call = {"pass": p, "start_frame": s, "end_frame": e, "output_path": folder, "camera": cam_name}
        if p == "openpose":
            call["gizmo_scale"] = float(args.get("gizmo_scale", 12.0))
            for k in ("bFace", "bHand", "bWholeHand", "bWholeFace"):
                if k in args:
                    call[k] = args[k]
        r = render_control_pass(call)
        frames = _frames(folder, p)
        counts[p] = len(frames)
        results[p] = {"ok": bool(r.get("ok")), "frames": len(frames), "seconds": r.get("seconds"), "folder": folder,
                      "first": frames[0][0] if frames else None, "last": frames[-1][0] if frames else None}
        if frames:
            mid_files[p] = os.path.join(folder, frames[len(frames) // 2][1])
        if r.get("note"):
            results[p]["note"] = r["note"]
    W, H = _render_size()
    q = RLPy.RGlobal.GetRenderExportImageSequenceParameter()
    q = q[0] if isinstance(q, (list, tuple)) else q
    fps = int(float(q.kCommon.kFps or 30))
    if args.get("video", True):
        ff = _ffmpeg()
        for p, r in results.items():
            if not ff:
                r["mp4"] = None; r["mp4_error"] = "no ffmpeg (iClone Bin64 or PATH)"
            elif r["frames"]:
                ok, err = _encode(ff, r["folder"], p, r["first"], fps, os.path.join(out_dir, p + ".mp4"))
                r["mp4"] = os.path.join(out_dir, p + ".mp4") if ok else None
                if not ok:
                    r["mp4_error"] = err
    cam = next((c for c in RLPy.RScene.GetCameras() if c.GetName() == cam_name), RLPy.RScene.GetCurrentCamera())
    t = RLPy.RGlobal.GetFps().IndexedFrameTime(s)
    W_ = cam.WorldTransform(); P = W_.T()
    manifest = {"project": RLPy.RApplication.GetCurrentProjectPath(), "frames": [s, e], "fps": fps, "size": [W, H],
                "camera": {"name": cam.GetName(), "focal_length_mm": round(cam.GetFocalLength(t), 2),
                           "position_at_start_cm": [round(P.x, 1), round(P.y, 1), round(P.z, 1)]},
                "passes": results, "exported": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    same_length = len(set(counts.values())) == 1
    out = {"ok": all(r["ok"] for r in results.values()) and same_length, "output_dir": out_dir,
           "frames_per_pass": counts, "same_length": same_length, "passes": results,
           "seconds": round(time.time() - t0, 1)}
    if mid_files:
        out["check_sheet"], img = _check_sheet(out_dir, passes, mid_files)
        if args.get("return_image", True):
            out["_image_png_b64"] = img
    return out


def register(registry):
    registry["previz_export"] = {
        "handler": previz_export, "main_thread": True, "checkpoint": True,
        "description": "AI-VIDEO PREVIZ PACKAGE for a frame range through one camera: beauty + OpenPose + depth (+ normal, "
                       "canny) in per-pass folders with matching frame numbers, one MP4 per pass, manifest.json, and a "
                       "check sheet (mid frame of each pass + OpenPose over beauty for alignment). Output size/fps = "
                       "Render panel (set_render_output).",
        "inputSchema": {"type": "object", "properties": {
            "start_frame": {"type": "integer"}, "end_frame": {"type": "integer"},
            "output_dir": {"type": "string", "description": "folder for the package (created)"},
            "passes": {"type": "array", "items": {"type": "string", "enum": ["beauty", "openpose", "depth", "normal", "canny"]}},
            "camera": {"type": "string"}, "gizmo_scale": {"type": "number", "description": "OpenPose line/dot size (default 12)"},
            "bFace": {"type": "boolean"}, "bHand": {"type": "boolean"}, "bWholeHand": {"type": "boolean"},
            "bWholeFace": {"type": "boolean"}, "video": {"type": "boolean"}, "return_image": {"type": "boolean"}},
            "required": ["start_frame", "end_frame", "output_dir"]}}
