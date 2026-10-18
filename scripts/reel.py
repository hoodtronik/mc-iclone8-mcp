"""Turn a scene's previz export into videos a person can watch: one edit of every shot's beauty pass in shot order,
and per shot the passes side by side (beauty | openpose | depth ...), each with a poster frame, plus an index.html
with inline players. Stdlib + ffmpeg (PATH or iClone's Bin64).

  python scripts/reel.py examples/scenes/cafe_trial.json      # after build_scene.py ... --previz
Output: <project folder>/previz/reel/  (build_scene.py --previz runs this at the end)
# CLAUDE-NOTE (2026-10-18): the user asked to SEE the work on a phone; per-shot PNG folders and 15 separate MP4s are
# not watchable. This was done by hand with ffmpeg concat/hstack first; now every --previz build leaves a reel.
"""
import html
import json
import os
import shutil
import subprocess
import sys

PASS_ORDER = ["beauty", "openpose", "depth", "normal", "canny"]
ICLONE_FFMPEG = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Reallusion", "iClone 8", "Bin64",
                             "ffmpeg.exe")


def ffmpeg_path():
    found = shutil.which("ffmpeg")
    return found or (ICLONE_FFMPEG if os.path.isfile(ICLONE_FFMPEG) else None)


def _run(ff, args):
    subprocess.run([ff, "-y", "-loglevel", "error"] + args, check=True)


def build_reel(spec, out_dir, ff=None):
    """-> {"edit": path, "shots": [{id, passes_video, poster}], "index": path}; skips shots without a beauty.mp4."""
    ff = ff or ffmpeg_path()
    if not ff:
        raise RuntimeError("ffmpeg not found (install it on PATH or keep iClone's Bin64\\ffmpeg.exe)")
    previz = os.path.join(out_dir, "previz")
    reel = os.path.join(previz, "reel")
    os.makedirs(reel, exist_ok=True)
    shots, beauties = [], []
    for sh in spec.get("shots", []):
        d = os.path.join(previz, sh["id"])
        passes = [p for p in PASS_ORDER if os.path.isfile(os.path.join(d, p + ".mp4"))]
        if "beauty" not in passes:
            continue
        beauties.append(os.path.join(d, "beauty.mp4"))
        row = {"id": sh["id"], "start_s": sh.get("start_s"), "end_s": sh.get("end_s"), "prompt": sh.get("prompt", "")}
        if len(passes) > 1:
            out = os.path.join(reel, f"{sh['id']}_passes.mp4")
            ins = sum((["-i", os.path.join(d, p + ".mp4")] for p in passes), [])
            scaled = "".join(f"[{i}:v]scale=640:-2[s{i}];" for i in range(len(passes)))
            stack = "".join(f"[s{i}]" for i in range(len(passes))) + f"hstack={len(passes)},format=yuv420p[v]"
            _run(ff, ins + ["-filter_complex", scaled + stack, "-map", "[v]", "-c:v", "libx264", "-crf", "20",
                            "-movflags", "+faststart", out])
            row.update(passes_video=os.path.basename(out), passes=passes)
        poster = os.path.join(reel, f"{sh['id']}.jpg")
        _run(ff, ["-ss", "0.5", "-i", os.path.join(d, "beauty.mp4"), "-frames:v", "1", "-vf", "scale=960:-2",
                  "-q:v", "4", poster])
        row["poster"] = os.path.basename(poster)
        shots.append(row)
    if not beauties:
        raise RuntimeError(f"no previz beauty.mp4 under {previz} - run build_scene.py with --previz first")
    edit = os.path.join(reel, "edit.mp4")
    ins = sum((["-i", b] for b in beauties), [])
    cat = "".join(f"[{i}:v]" for i in range(len(beauties))) + f"concat=n={len(beauties)}:v=1:a=0,format=yuv420p[v]"
    _run(ff, ins + ["-filter_complex", cat, "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-movflags", "+faststart",
                    edit])
    _run(ff, ["-ss", "0.5", "-i", edit, "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "4",
              os.path.join(reel, "edit.jpg")])
    index = os.path.join(reel, "index.html")
    with open(index, "w", encoding="utf-8") as fh:
        fh.write(_page(spec, shots))
    return {"edit": edit, "shots": shots, "index": index}


def _page(spec, shots):
    """A plain local page with inline players (open it in a browser, or publish the reel folder as an artifact)."""
    name = html.escape(spec.get("name", "Scene"))
    rows = []
    for s in shots:
        if s.get("passes_video"):
            rows.append(f'<figure><video controls playsinline preload="none" poster="{s["poster"]}" '
                        f'src="{s["passes_video"]}"></video><figcaption><b>{html.escape(s["id"])}</b> '
                        f'{s["start_s"]}-{s["end_s"]} s &middot; {" | ".join(s["passes"])}'
                        f'{(" &middot; " + html.escape(s["prompt"])) if s["prompt"] else ""}</figcaption></figure>')
    return ("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{name} reel</title><style>body{{font:15px system-ui,sans-serif;background:#15171c;color:#e6e3dc;"
            "margin:0;padding:24px max(16px,env(safe-area-inset-left))}main{max-width:920px;margin:auto;display:grid;"
            "gap:28px}video{width:100%;background:#000;border-radius:6px}figure{margin:0;display:grid;gap:8px}"
            "figcaption{color:#9a9ca3}b{color:#e6e3dc}</style><main>"
            f"<h1>{name}</h1><figure><video controls playsinline preload='none' poster='edit.jpg' src='edit.mp4'>"
            "</video><figcaption><b>Full edit</b> every shot in order (beauty)</figcaption></figure>"
            + "".join(rows) + "</main>")


def main(argv=None):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_scene import Builder
    path = os.path.abspath((argv or sys.argv[1:])[0])
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    r = build_reel(spec, Builder(spec, os.path.dirname(path)).out_dir)
    print(json.dumps({"edit": r["edit"], "index": r["index"], "shots": [s["id"] for s in r["shots"]]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
