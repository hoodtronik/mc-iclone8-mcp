"""REAL-TIME iClone eyes: a live view of the iClone window + an event stream, running OUTSIDE iClone (keeps working when
iClone's main thread is frozen or a modal popup blocks it). Stdlib only.

  python scripts/iclone_live_eyes.py                    # watch: live page http://127.0.0.1:8767 + events on stdout
  python scripts/iclone_live_eyes.py --fps 4 --width 1600 --port 8767 --out <dir>
  python scripts/iclone_live_eyes.py clip 10 out.mp4    # last 10 s of the ring buffer -> mp4 (needs ffmpeg)
  python scripts/iclone_live_eyes.py state              # one JSON status line from a running watcher

Agents: run the watcher under a stream monitor (Claude Code: Monitor tool) - each stdout line is one event:
  EVENT started / iclone_running / iclone_exited / hung / responsive / popup_opened {title, texts, buttons, png} /
  popup_closed / view_changed {score} / view_still {seconds} / view_blank {hint}
Humans: open the page (live picture refreshed every frame + state). Files: <out>/latest.png, <out>/ring/*.png, <out>/state.json.

# CLAUDE-NOTE (2026-10-23, hoodtronik fork): Ilyas asked for "real time eyes". The existing eyes were snapshot-only
# (viewport_capture runs in-process and freezes with iClone; iclone_eyes.py grabs one window on demand). This adds a
# continuous out-of-process loop: PrintWindow (PW_RENDERFULLCONTENT) on the iClone main window, a ring of recent frames,
# change/still/blank detection on a 64-px thumbnail, popup + hang (IsHungAppWindow) + exit events, and a localhost page.
# view_blank fires on a near-uniform frame: measured 2026-10-23 that a LOCKED Windows session gives iClone a blank
# white viewport (LockApp.exe running) - the hint says so.
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iclone_eyes as eyes  # noqa: E402  (ctypes setup, list_windows, uia, PNG encoder)

user32, gdi32 = eyes.user32, eyes.gdi32
user32.IsHungAppWindow.argtypes = [wintypes.HWND]
STATE: dict = {"running": False}
LOCK = threading.Lock()
FFMPEG_CANDIDATES = [os.environ.get("ICLONE_EYES_FFMPEG", ""), r"D:\pinokio\api\wan.git\app\ffmpeg_bins\ffmpeg.exe", "ffmpeg"]


def grab(hwnd: int, max_width: int):
    """(w, h, BGRA bytes) of a window, scaled to max_width. Same PrintWindow path as iclone_eyes.capture."""
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    scale = min(1.0, max_width / w)
    ow, oh = max(1, int(w * scale)), max(1, int(h * scale))
    wdc = user32.GetWindowDC(hwnd)
    fdc, sdc = gdi32.CreateCompatibleDC(wdc), gdi32.CreateCompatibleDC(wdc)
    fbmp, sbmp = gdi32.CreateCompatibleBitmap(wdc, w, h), gdi32.CreateCompatibleBitmap(wdc, ow, oh)
    of, os_ = gdi32.SelectObject(fdc, fbmp), gdi32.SelectObject(sdc, sbmp)
    try:
        user32.PrintWindow(hwnd, fdc, eyes.PW_RENDERFULLCONTENT)
        gdi32.SetStretchBltMode(sdc, eyes.HALFTONE)
        gdi32.StretchBlt(sdc, 0, 0, ow, oh, fdc, 0, 0, w, h, eyes.SRCCOPY)
        bih = eyes.BITMAPINFOHEADER(ctypes.sizeof(eyes.BITMAPINFOHEADER), ow, -oh, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(ow * oh * 4)
        gdi32.SelectObject(sdc, os_)
        gdi32.GetDIBits(sdc, sbmp, 0, oh, buf, ctypes.byref(bih), 0)
        return ow, oh, buf.raw
    finally:
        gdi32.SelectObject(fdc, of)
        for b in (fbmp, sbmp):
            gdi32.DeleteObject(b)
        gdi32.DeleteDC(fdc)
        gdi32.DeleteDC(sdc)
        user32.ReleaseDC(hwnd, wdc)


def thumb_stats(bgra: bytes, prev: bytes | None):
    """(change 0-255, spread 0-255, white fraction) on the grey channel of a small grab."""
    g = bgra[1::4]
    spread = max(g) - min(g) if g else 0
    white = sum(1 for v in g if v > 245) / max(1, len(g))
    change = sum(abs(a - b) for a, b in zip(g, prev[1::4])) / max(1, len(g)) if prev and len(prev) == len(bgra) else 0.0
    return change, spread, white


def emit(kind: str, **data):
    data.update(event=kind, t=time.strftime("%H:%M:%S"))
    print("EVENT " + json.dumps(data, ensure_ascii=False), flush=True)
    with LOCK:
        STATE.setdefault("events", []).append(data)
        STATE["events"] = STATE["events"][-50:]


def locked_session() -> bool:
    try:
        out = subprocess.run(["tasklist", "/NH"], capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return "LockApp.exe" in out or "LogonUI.exe" in out
    except Exception:
        return False


def watch(a):
    out, ring = a.out, os.path.join(a.out, "ring")
    os.makedirs(ring, exist_ok=True)
    period, keep = 1.0 / a.fps, int(a.keep_s * a.fps)
    prev_small, last_change, still_sent, blank_sent = None, time.time(), False, False
    known_pops, hung, running, n = {}, False, None, 0
    progress = set()
    emit("started", page="http://127.0.0.1:%d" % a.port, out=out, fps=a.fps)
    while True:
        t0 = time.time()
        wins = eyes.list_windows(eyes.PROCESS)
        main = eyes.main_window(wins)
        if not main:
            if running is not False:
                emit("iclone_exited" if running else "iclone_not_running")
                running = False
            with LOCK:
                STATE.update(running=False, hung=None)
            time.sleep(1.0)
            continue
        if running is not True:
            emit("iclone_running", hwnd=main["hwnd"], title=main["title"])
            running = True
        hwnd = main["hwnd"]
        h = bool(user32.IsHungAppWindow(hwnd))
        if h != hung:
            emit("hung" if h else "responsive", hint="main thread blocked: check popups / long load" if h else "")
            hung = h
        pops = {w["hwnd"]: w for w in wins if w["hwnd"] != hwnd}
        for p in set(pops) - set(known_pops):
            info = {k: v for k, v in eyes.uia(p).items() if k in ("texts", "buttons")}
            png, _ = eyes.capture(p, 900)
            path = os.path.join(out, "popup_%d.png" % p)
            open(path, "wb").write(png)
            texts = list(dict.fromkeys(info.get("texts") or []))[:8]
            buttons = list(dict.fromkeys(info.get("buttons") or []))[:10]
            # CLAUDE-NOTE (2026-10-23): load/save progress boxes ("Saving undo/redo data.", "Updating Scene ...", "Please
            # wait ...", "Process to Render...") have at most a Cancel button and flooded the stream; report them as
            # 'progress' (stdout only with --verbose-progress) and keep popup_opened for windows that need an answer.
            if set(buttons) <= {"Cancel"} and (not texts or any("..." in t or t.rstrip().endswith(".") or "wait" in t.lower() for t in texts)):
                progress.add(p)
                if a.verbose_progress:
                    emit("progress", hwnd=p, texts=texts)
                continue
            emit("popup_opened", hwnd=p, title=pops[p]["title"], texts=texts, buttons=buttons, png=path)
        for p in set(known_pops) - set(pops):
            if p in progress:
                progress.discard(p)
                continue
            emit("popup_closed", hwnd=p, title=known_pops[p]["title"])
        known_pops = pops
        small = grab(hwnd, 64)
        big = grab(hwnd, a.width)
        if small and big:
            change, spread, white = thumb_stats(small[2], prev_small)
            prev_small = small[2]
            now = time.time()
            if change >= a.change_threshold:
                if still_sent or now - last_change > 2.0:
                    emit("view_changed", score=round(change, 2))
                last_change, still_sent = now, False
            elif not still_sent and now - last_change >= a.still_s:
                emit("view_still", seconds=round(now - last_change, 1))
                still_sent = True
            # CLAUDE-NOTE: locked session = dark UI panels around a pure-white viewport (~40%+ of the window is white).
            blank = spread < 6 or white > 0.35
            if blank and not blank_sent:
                emit("view_blank", hint="Windows session locked: iClone draws nothing until unlocked" if locked_session()
                     else "window renders uniform (minimized, loading, or GPU not drawing)")
            blank_sent = blank
            png = eyes._png(big[0], big[1], big[2])
            tmp = os.path.join(out, "latest.tmp")
            open(tmp, "wb").write(png)
            os.replace(tmp, os.path.join(out, "latest.png"))
            open(os.path.join(ring, "f%08d.png" % n), "wb").write(png)
            old = os.path.join(ring, "f%08d.png" % (n - keep))
            if os.path.exists(old):
                os.remove(old)
            n += 1
            with LOCK:
                STATE.update(running=True, hung=hung, frame=n, size=[big[0], big[1]], change=round(change, 2),
                             blank=blank, popups=[{"hwnd": k, "title": v["title"]} for k, v in pops.items()],
                             updated=time.strftime("%H:%M:%S"))
                json.dump(STATE, open(os.path.join(out, "state.json"), "w"), indent=1)
        time.sleep(max(0.0, period - (time.time() - t0)))


PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>iClone live eyes</title><style>body{margin:0;background:#111;color:#ddd;font:13px system-ui}img{width:100%%;display:block}
#s{padding:6px 10px;white-space:pre-wrap}</style><img id=v src=/latest.png><div id=s>...</div><script>
setInterval(()=>{document.getElementById('v').src='/latest.png?'+Date.now()},%d);
setInterval(async()=>{try{const s=await (await fetch('/state')).json();const e=(s.events||[]).slice(-6).map(x=>x.t+' '+x.event+
(x.title?' '+x.title:'')+(x.texts?' '+x.texts.join(' | '):'')).join('\\n');document.getElementById('s').textContent=
'running '+s.running+'  hung '+s.hung+'  frame '+s.frame+'  change '+s.change+'  blank '+s.blank+'  popups '+(s.popups||[]).length+'\\n'+e}catch(_){}} ,1000)
</script>"""


def serve(a):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *x):
            pass

        def _send(self, body, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            p = self.path.split("?")[0]
            if p == "/":
                return self._send((PAGE % max(100, int(1000 / a.fps))).encode(), "text/html; charset=utf-8")
            if p == "/latest.png":
                f = os.path.join(a.out, "latest.png")
                return self._send(open(f, "rb").read() if os.path.exists(f) else b"", "image/png")
            if p == "/state":
                with LOCK:
                    return self._send(json.dumps(STATE).encode(), "application/json")
            self.send_error(404)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()  # localhost only


def clip(a, seconds: float, dst: str):
    ring = os.path.join(a.out, "ring")
    frames = sorted(f for f in os.listdir(ring) if f.endswith(".png"))[-max(1, int(seconds * a.fps)):]
    ff = next((c for c in FFMPEG_CANDIDATES if c and (os.path.isfile(c) or shutil.which(c))), None)
    if not ff:
        raise SystemExit("ffmpeg not found (set ICLONE_EYES_FFMPEG)")
    with tempfile.TemporaryDirectory() as d:
        lst = os.path.join(d, "list.txt")
        with open(lst, "w") as fh:
            for f in frames:
                fh.write("file '%s'\nduration %f\n" % (os.path.join(ring, f).replace("\\", "/"), 1.0 / a.fps))
        subprocess.run([ff, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=24",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", dst], check=True)
    print(json.dumps({"clip": dst, "frames": len(frames)}))


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="*", help="(empty)=watch | clip <seconds> <out.mp4> | state")
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--keep-s", type=float, default=120.0, help="seconds of frames kept in the ring")
    ap.add_argument("--still-s", type=float, default=20.0, help="emit view_still after this long without change")
    ap.add_argument("--change-threshold", type=float, default=2.0)
    ap.add_argument("--verbose-progress", action="store_true", help="also emit load/save progress boxes")
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "iclone_live_eyes"))
    a = ap.parse_args()
    if a.cmd[:1] == ["clip"]:
        return clip(a, float(a.cmd[1]), a.cmd[2])
    if a.cmd[:1] == ["state"]:
        import urllib.request
        return print(urllib.request.urlopen("http://127.0.0.1:%d/state" % a.port, timeout=5).read().decode())
    os.makedirs(a.out, exist_ok=True)
    threading.Thread(target=serve, args=(a,), daemon=True).start()
    try:
        watch(a)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
