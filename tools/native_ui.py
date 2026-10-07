"""Win32 helpers for iClone's NATIVE modal dialogs (Windows "Open" file picker, "Import Settings"), which block the Qt main
thread so python_exec / dialog_watch cannot see or touch them. These run on the MCP HTTP thread (ctypes only, no Qt).
# CLAUDE-NOTE (2026-10-07, measured): the Qt dialogs ("Motion Import Settings", "Project" dock) keep servicing the bridge
# through their nested event loop; the native ones do not. Enter did not close "Import Settings"; a DPI-aware click at a
# fraction of the window rect did. Typing a path + Enter into the native "Open" dialog (SendInput unicode) works.
"""
import ctypes
import os
import time
from ctypes import wintypes

_u = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


def windows(pid=None):
    """Visible top-level windows [(hwnd, title)] of a process (default: this process)."""
    pid = pid or os.getpid()
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        if _u.IsWindowVisible(h):
            owner = wintypes.DWORD()
            _u.GetWindowThreadProcessId(h, ctypes.byref(owner))
            if owner.value == pid:
                n = _u.GetWindowTextLengthW(h)
                buf = ctypes.create_unicode_buffer(n + 1)
                _u.GetWindowTextW(h, buf, n + 1)
                out.append((h, buf.value))
        return True
    _u.EnumWindows(cb, 0)
    return out


def wait_window(title, timeout_s=15.0, pid=None):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        for h, t in windows(pid):
            if t == title:
                return h
        time.sleep(0.25)
    return None


class _KI(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KI), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _key(vk=0, scan=0, flags=0):
    i = _INPUT(); i.type = 1; i.ki = _KI(vk, scan, flags, 0, None)
    _u.SendInput(1, ctypes.byref(i), ctypes.sizeof(_INPUT))


def type_text(hwnd, text, enter=True):
    """Foreground the window and type `text` as unicode key events (then Enter)."""
    _u.SetForegroundWindow(hwnd); time.sleep(0.4)
    for ch in text:
        _key(0, ord(ch), 4); _key(0, ord(ch), 4 | 2)
        time.sleep(0.004)
    if enter:
        time.sleep(0.2); _key(0x0D, 0, 0); _key(0x0D, 0, 2)


def click_fraction(hwnd, fx, fy):
    """Left-click at a fraction (0..1) of the window rect — for native dialogs whose buttons are not child windows."""
    r = wintypes.RECT(); _u.GetWindowRect(hwnd, ctypes.byref(r))
    x, y = int(r.left + (r.right - r.left) * fx), int(r.top + (r.bottom - r.top) * fy)
    _u.SetForegroundWindow(hwnd); time.sleep(0.3)
    _u.SetCursorPos(x, y); time.sleep(0.15); _u.mouse_event(2, 0, 0, 0, 0); time.sleep(0.05); _u.mouse_event(4, 0, 0, 0, 0)
    return x, y
