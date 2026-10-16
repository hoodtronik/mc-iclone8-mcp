"""One-command health check for agents: is iClone + the MCP ready, and if not, exactly what to do.

  python scripts/doctor.py          # prints PASS / WARN / FAIL lines with a FIX for each problem; exit 1 on any FAIL

Checks: MCP server up, popups blocking iClone (read from OUTSIDE iClone, so it works while iClone is frozen), open
project (scratch vs saved), stock content library, Motion Director packs + Reallusion login, render/viewport aspect,
ffmpeg for previz MP4s. Stdlib only.
# CLAUDE-NOTE (2026-10-16): written so a weaker agent starts every session from a known-good state instead of
# discovering each trap (frozen modal, missing content, scratch scene with no path) the hard way.
"""
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BASE = os.environ.get("MC_ICLONE8_MCP_URL", "http://127.0.0.1:8766/mcp").rsplit("/mcp", 1)[0]
PUBLIC = os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Documents", "Reallusion")
results = []


def report(level, what, detail="", fix=""):
    results.append(level)
    print(f"[{level}] {what}" + (f" - {detail}" if detail else ""))
    if fix:
        print(f"       FIX: {fix}")


def server_up():
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=5) as r:
            return json.load(r)
    except Exception as e:
        return {"error": str(e)}


def main():
    h = server_up()
    if "error" in h:
        report("FAIL", "MCP server not reachable", h["error"],
               "start iClone with the plugin: python scripts/launch_iclone.py (then re-run doctor)")
    else:
        report("PASS", "MCP server up", f"{h.get('server')} / {h.get('api')}")

    # popups, read from outside iClone
    try:
        out = subprocess.run([sys.executable, os.path.join(HERE, "iclone_eyes.py"), "popups"], capture_output=True,
                             text=True, timeout=120)
        pops = json.loads(out.stdout or "[]")
        panels = {"MD Controls", "Render", "Modify", "Content", "Scene"}
        blocking = [p for p in pops if p["title"] not in panels]
        if blocking:
            for p in blocking:
                report("WARN", f"iClone window open: {p['title']!r} (hwnd {p['hwnd']})",
                       " | ".join(p.get("texts", [])[:2])[:160],
                       f"read it, then: python scripts/iclone_eyes.py press {p['hwnd']} \"<button>\" "
                       f"(buttons: {p.get('buttons', [])[:6]}); never answer save/discard prompts without the user")
        else:
            report("PASS", "no popups blocking iClone", f"{len(pops)} tool panel(s) floating")
    except Exception as e:
        report("WARN", "could not list iClone windows", str(e)[:120], "run python scripts/iclone_eyes.py list")

    if "error" in h:
        return finish()
    from icall import call
    code = r'''
import RLPy, os
r = {"project": RLPy.RApplication.GetCurrentProjectPath(), "default": RLPy.RApplication.GetDefaultProjectPath(),
     "avatars": len(RLPy.RScene.GetAvatars()), "fps": RLPy.RGlobal.GetFps().ToFloat()}
import sys
r["bin"] = os.path.dirname(sys.executable)
try:
    import RLPy2
    r["logged_in"] = RLPy2.ContentManager.GetInterface().IsMemberLogIn()
except Exception as e:
    r["logged_in"] = None
try:
    from tools.icmcp_extra import _viewport, _render_size
    vp = _viewport(); r["viewport"] = [vp.width(), vp.height()]; r["render"] = list(_render_size())
except Exception as e:
    r["viewport_err"] = str(e)
_result = r
'''
    r = call("python_exec", {"code": code}, timeout=60)
    if not isinstance(r, dict) or not r.get("ok"):
        report("FAIL", "python_exec failed (iClone main thread busy or blocked?)", str(r)[:200],
               "check popups above; if none, wait for long operations or restart: python scripts/launch_iclone.py --restart")
        return finish()
    info = r["result"]
    proj, default = info.get("project") or "", info.get("default") or ""
    if not proj or os.path.normcase(proj) == os.path.normcase(default):
        report("WARN", "open scene is an unsaved scratch scene", f"{info['avatars']} avatar(s)",
               "save it to its own path before work: icall save_project {\"path\": \"...\\\\_scratch\\\\name.iProject\"} "
               "(checkpoint tools need a path and never write to another project)")
    else:
        report("PASS", "project", f"{proj} ({info['avatars']} avatars, {info['fps']} fps)")
    for label, rel in (("stock avatars", r"Reallusion Templates\Actor\Character"),
                       ("stock motions", r"Reallusion Templates\Animation\Motion"),
                       ("iClone 7 template motions (walks)", r"Template\iClone 7 Template\iClone Template\Motion")):
        p = os.path.join(PUBLIC, rel)
        report("PASS" if os.path.isdir(p) else "WARN", label, p,
               "" if os.path.isdir(p) else "install the iClone content (Reallusion Hub) or set ICMCP_CONTENT_ROOT")
    md = os.path.join(PUBLIC, "Reallusion Templates", "Animation", "Motion Director")
    have_md = os.path.isdir(md) and any(f.lower().endswith(".imd") for _, _, fs in os.walk(md) for f in fs)
    if have_md:
        report("PASS", "Motion Director packs installed", md)
    else:
        report("WARN", "Motion Director packs missing (md_walk_path won't work)", md,
               "ask the USER to sign in to their Reallusion account in iClone; the first MD Start installs the packs")
    if info.get("logged_in") is False:
        report("WARN", "not signed in to Reallusion", "content downloads need it", "ask the user to sign in (never use their account yourself)")
    if info.get("viewport") and info.get("render"):
        vw, vh = info["viewport"]; rw, rh = info["render"]
        report("PASS", "render vs viewport", f"render {rw}x{rh}, viewport {vw}x{vh} (sequence renders auto-match aspect)")
    ff = os.path.join(info.get("bin") or "", "ffmpeg.exe")     # iClone ships ffmpeg next to iClone.exe
    report("PASS" if os.path.isfile(ff) else "WARN", "ffmpeg for previz MP4s", ff if os.path.isfile(ff) else "not found",
           "" if os.path.isfile(ff) else "install ffmpeg on PATH (previz_export still writes PNG frames)")
    return finish()


def finish():
    fails, warns = results.count("FAIL"), results.count("WARN")
    print(f"\n{fails} FAIL, {warns} WARN, {results.count('PASS')} PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
