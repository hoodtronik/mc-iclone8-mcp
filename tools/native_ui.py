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

# CLAUDE-NOTE (2026-10-07, measured): a private user32 instance — argtypes live on the function objects, and the shared
# ctypes.windll.user32 got its SendMessageW argtypes overwritten by other code, breaking WM_SETTEXT here.
_u = ctypes.WinDLL("user32", use_last_error=True)
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


# CLAUDE-NOTE (2026-10-07, incident): synthetic mouse input once landed in Ilyas's browser because iClone was not on top.
# Nothing here may send keyboard/mouse input that could reach another application: text goes in by WM_SETTEXT to the
# dialog's own Edit control, and the physical click helper refuses unless the window under the cursor is ours.
_WM_SETTEXT, _WM_COMMAND, _IDOK = 0x000C, 0x0111, 1
_u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_wchar_p]
_u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_u.FindWindowExW.restype = wintypes.HWND
_u.WindowFromPoint.argtypes = [wintypes.POINT]
_u.WindowFromPoint.restype = wintypes.HWND


def _owner_pid(hwnd):
    pid = wintypes.DWORD(); _u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)); return pid.value


def _children(hwnd):
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _l):
        buf = ctypes.create_unicode_buffer(64); _u.GetClassNameW(h, buf, 64); out.append((h, buf.value)); return True
    _u.EnumChildWindows(hwnd, cb, 0)
    return out


def type_text(hwnd, text, enter=True):
    """Put `text` into a native file dialog's filename box and press OK, by window messages addressed to that dialog only
    (focus-independent; cannot reach other applications)."""
    if _owner_pid(hwnd) != os.getpid():
        raise RuntimeError("refusing to type into a window that does not belong to iClone")
    edits = [h for h, cls in _children(hwnd) if cls == "Edit" and _u.IsWindowVisible(h)]
    if not edits:
        raise RuntimeError("no visible Edit control in the dialog")
    _u.SendMessageW(edits[0], _WM_SETTEXT, 0, text)
    if enter:
        time.sleep(0.2); _u.PostMessageW(hwnd, _WM_COMMAND, _IDOK, 0)


def click_fraction(hwnd, fx, fy):
    """Left-click at a fraction (0..1) of the window rect — for native dialogs whose buttons are not child windows.
    Moves the real cursor, so it first checks that the window under that point belongs to iClone."""
    r = wintypes.RECT(); _u.GetWindowRect(hwnd, ctypes.byref(r))
    x, y = int(r.left + (r.right - r.left) * fx), int(r.top + (r.bottom - r.top) * fy)
    if _owner_pid(hwnd) != os.getpid():
        raise RuntimeError("refusing to click a window that does not belong to iClone")
    _u.SetForegroundWindow(hwnd); time.sleep(0.3)
    under = _u.WindowFromPoint(wintypes.POINT(x, y))
    if not under or _owner_pid(under) != os.getpid():
        raise RuntimeError(f"refusing to click: the window at ({x}, {y}) is not iClone's (another app is on top)")
    _u.SetCursorPos(x, y); time.sleep(0.15); _u.mouse_event(2, 0, 0, 0, 0); time.sleep(0.05); _u.mouse_event(4, 0, 0, 0, 0)
    return x, y


def close_message_boxes(title):
    """Press the only/first button of message boxes titled `title` that have no Edit control (error popups), by BM_CLICK."""
    closed = 0
    for h, t in windows():
        kids = _children(h)
        if t == title and not [c for c, cls in kids if cls == "Edit"]:
            btns = [c for c, cls in kids if cls == "Button"]
            if btns:
                _u.PostMessageW(btns[0], 0x00F5, 0, 0); closed += 1
    return closed
