"""iClone EYES that work while iClone is frozen: list iClone's windows, read a popup's text and buttons, press a button
by name, capture a window to PNG, or close it. Runs OUTSIDE iClone (any Python 3.8+, stdlib only), so it keeps working
when a modal dialog blocks iClone's main thread - exactly when the in-process MCP tools (list_dialogs, viewport_capture)
hang.

  python scripts/iclone_eyes.py popups                 # every iClone window except the main one: title, text, buttons, png
  python scripts/iclone_eyes.py read <hwnd>            # text + button names of one window (UI Automation)
  python scripts/iclone_eyes.py press <hwnd> "<button>" # click a button by its exact name (e.g. "OK", "No", "Cancel")
  python scripts/iclone_eyes.py capture <hwnd> [out.png]
  python scripts/iclone_eyes.py close <hwnd>           # WM_CLOSE (usually = Cancel/OK on info boxes)
  python scripts/iclone_eyes.py list                   # all visible iClone windows

Rules: READ before pressing. Never press "Yes"/"Save"/"Don't Save" on a save/discard prompt without the user's say-so.
# CLAUDE-NOTE (2026-10-16): ported from ReverseEngineerMCP src/retk/windows.py (ctypes + zlib PNG, live-proven) so this
# repo needs nothing else. Text/buttons come from Windows UI Automation via PowerShell (Qt exposes widgets AND QML items
# through UIA, measured on MD Controls); pressing by name uses UIA InvokePattern, which worked where posted Enter/Space
# did not reach a Qt modal ("Found N files that will be overwritten").
"""
from __future__ import annotations

import ctypes
import json
import os
import struct
import subprocess
import sys
import tempfile
import zlib
from ctypes import wintypes

if sys.platform != "win32":  # pragma: no cover
    raise SystemExit("iclone_eyes is Windows-only")

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.SetStretchBltMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.StretchBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                            ctypes.c_void_p, wintypes.UINT]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]

GW_OWNER = 4
PW_RENDERFULLCONTENT = 2  # captures DirectX/GL content too (Win 8.1+)
SRCCOPY = 0x00CC0020
HALFTONE = 4
WM_CLOSE, WM_KEYDOWN, WM_KEYUP = 0x0010, 0x0100, 0x0101
KEYS = {"enter": 0x0D, "escape": 0x1B, "tab": 0x09, "space": 0x20, "left": 0x25, "right": 0x27}


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def _process_name(pid: int) -> str:
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
        return ""
    finally:
        kernel32.CloseHandle(h)


def _info(hwnd: int, pid: int, name: str) -> dict:
    title = ctypes.create_unicode_buffer(512)
    cls = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, title, 512)
    user32.GetClassNameW(hwnd, cls, 256)
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    owner = user32.GetWindow(hwnd, GW_OWNER) or 0
    return {"hwnd": int(hwnd), "pid": pid, "process": name, "title": title.value, "class": cls.value,
            "rect": [r.left, r.top, r.right - r.left, r.bottom - r.top], "owned": bool(owner),
            "foreground": int(user32.GetForegroundWindow() or 0) == int(hwnd)}


def list_windows(process: str | None = None, pid: int | None = None, include_hidden: bool = False) -> list[dict]:
    """Top-level windows, optionally filtered by process exe name (case-insensitive, e.g. 'iClone.exe') or pid.
    Owned windows ('owned': true) are typically dialogs/popups of the main window."""
    out: list[dict] = []
    names: dict[int, str] = {}
    want = process.lower() if process else None

    def cb(hwnd, _):
        if not include_hidden and not user32.IsWindowVisible(hwnd):
            return True
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if pid is not None and p.value != pid:
            return True
        if p.value not in names:
            names[p.value] = _process_name(p.value)
        if want and names[p.value].lower() != want:
            return True
        out.append(_info(hwnd, p.value, names[p.value]))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def _png(width: int, height: int, bgra: bytes) -> bytes:
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
    stride = width * 3
    raw = b"".join(b"\x00" + bytes(rgb[y * stride:(y + 1) * stride]) for y in range(height))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def capture(hwnd: int, max_width: int = 1280) -> tuple[bytes, dict]:
    """PNG of one window via PrintWindow (works when covered by other windows or while the app is modal-blocked)."""
    if not user32.IsWindow(hwnd):
        raise ValueError(f"no such window: {hwnd}")
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        raise ValueError(f"window {hwnd} has no area (minimized?)")
    scale = min(1.0, max_width / w)
    ow, oh = max(1, int(w * scale)), max(1, int(h * scale))
    wdc = user32.GetWindowDC(hwnd)
    full_dc, small_dc = gdi32.CreateCompatibleDC(wdc), gdi32.CreateCompatibleDC(wdc)
    full_bmp, small_bmp = gdi32.CreateCompatibleBitmap(wdc, w, h), gdi32.CreateCompatibleBitmap(wdc, ow, oh)
    old_full, old_small = gdi32.SelectObject(full_dc, full_bmp), gdi32.SelectObject(small_dc, small_bmp)
    try:
        ok = user32.PrintWindow(hwnd, full_dc, PW_RENDERFULLCONTENT)
        gdi32.SetStretchBltMode(small_dc, HALFTONE)
        gdi32.StretchBlt(small_dc, 0, 0, ow, oh, full_dc, 0, 0, w, h, SRCCOPY)
        bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), ow, -oh, 1, 32, 0, 0, 0, 0, 0, 0)  # top-down BGRA
        buf = ctypes.create_string_buffer(ow * oh * 4)
        gdi32.SelectObject(small_dc, old_small)  # GetDIBits needs the bitmap deselected
        gdi32.GetDIBits(small_dc, small_bmp, 0, oh, buf, ctypes.byref(bih), 0)
        return _png(ow, oh, buf.raw), {"hwnd": hwnd, "size": [ow, oh], "source_size": [w, h], "printwindow_ok": bool(ok)}
    finally:
        gdi32.SelectObject(full_dc, old_full)
        for b in (full_bmp, small_bmp):
            gdi32.DeleteObject(b)
        gdi32.DeleteDC(full_dc)
        gdi32.DeleteDC(small_dc)
        user32.ReleaseDC(hwnd, wdc)



PROCESS = "iClone.exe"

_UIA_PS = r"""
Add-Type -AssemblyName UIAutomationClient; Add-Type -AssemblyName UIAutomationTypes
$e = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]__HWND__)
$all = $e.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$texts = @(); $buttons = @(); $n = 0
foreach ($x in $all) {
  $n++; if ($n -gt 4000) { break }
  $ct = $x.Current.ControlType.ProgrammaticName; $nm = $x.Current.Name
  if (-not $nm) { continue }
  if ($ct -eq 'ControlType.Button' -or $ct -eq 'ControlType.RadioButton' -or $ct -eq 'ControlType.CheckBox') { $buttons += $nm }
  elseif ($ct -eq 'ControlType.Text' -or $ct -eq 'ControlType.Edit' -or $ct -eq 'ControlType.Document') { $texts += $nm }
}
$press = '__PRESS__'
$pressed = $false
if ($press) {
  foreach ($x in $all) {
    if ($x.Current.Name -eq $press -and $x.Current.ControlType.ProgrammaticName -eq 'ControlType.Button') {
      $p = $null
      if ($x.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$p)) { $p.Invoke(); $pressed = $true; break }
    }
  }
}
@{ title = $e.Current.Name; texts = $texts; buttons = $buttons; pressed = $pressed } | ConvertTo-Json -Compress
"""


def uia(hwnd: int, press: str = "") -> dict:
    """Text + button names of a window via UI Automation; with press=<name>, invoke that button."""
    if not user32.IsWindow(hwnd):
        raise ValueError(f"no such window: {hwnd}")
    script = _UIA_PS.replace("__HWND__", str(int(hwnd))).replace("__PRESS__", press.replace("'", "''"))
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                       text=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        out = json.loads(r.stdout.strip() or "{}")
    except ValueError:
        out = {"error": (r.stderr or r.stdout)[-400:]}
    for k in ("texts", "buttons"):          # PowerShell collapses 1-item arrays
        if isinstance(out.get(k), str):
            out[k] = [out[k]]
    out["hwnd"] = int(hwnd)
    return out


def main_window(wins):
    tops = [w for w in wins if not w["owned"]]
    return max(tops, key=lambda w: w["rect"][2] * w["rect"][3]) if tops else None


def popups(save_png=True) -> list:
    wins = list_windows(PROCESS)
    main = main_window(wins)
    out = []
    for w in wins:
        if main and w["hwnd"] == main["hwnd"]:
            continue
        info = {"hwnd": w["hwnd"], "title": w["title"], "size": w["rect"][2:]}
        info.update({k: v for k, v in uia(w["hwnd"]).items() if k in ("texts", "buttons", "error")})
        info["texts"] = list(dict.fromkeys(info.get("texts") or []))[:20]      # QML repeats items; keep order, drop dups
        info["buttons"] = list(dict.fromkeys(info.get("buttons") or []))[:20]
        if save_png:
            png, _ = capture(w["hwnd"], 900)
            p = os.path.join(tempfile.gettempdir(), f"iclone_popup_{w['hwnd']}.png")
            with open(p, "wb") as fh:
                fh.write(png)
            info["png"] = p
        out.append(info)
    return out


def close(hwnd: int) -> dict:
    if not user32.IsWindow(hwnd):
        raise ValueError(f"no such window: {hwnd}")
    return {"hwnd": hwnd, "posted": bool(user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))}


def _cli(argv):
    if not argv:
        print(__doc__); return 2
    cmd = argv[0]
    if cmd == "list":
        res = list_windows(PROCESS)
    elif cmd == "popups":
        res = popups()
    elif cmd == "read":
        res = uia(int(argv[1]))
    elif cmd == "press":
        res = uia(int(argv[1]), argv[2])
    elif cmd == "capture":
        png, meta = capture(int(argv[1]))
        path = argv[2] if len(argv) > 2 else os.path.join(tempfile.gettempdir(), f"iclone_window_{argv[1]}.png")
        with open(path, "wb") as fh:
            fh.write(png)
        res = dict(meta, saved=path)
    elif cmd == "close":
        res = close(int(argv[1]))
    else:
        print(__doc__); return 2
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
