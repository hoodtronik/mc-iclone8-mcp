"""Watch iClone for popup dialogs (modal QMessageBox/QDialog), log them, auto-dismiss only whitelisted harmless ones.
Log: ~/Desktop/icmcp_dialogs.log · MCP: list_dialogs / dismiss_dialog (registered from icmcp_extra).
# CLAUDE-NOTE (2026-09-26, hoodtronik fork): unattended sessions die on modals (AccuPOSE "serial number is invalid" at
# startup, "Start time and end time are equal"). NEVER widen AUTO_OK to prompts that change or discard data.
"""
import datetime, os

AUTO_OK = [
    "The serial number is invalid",               # AccuPOSE licence nag (built into ICMotion.dll; cannot be uninstalled)
    "Start time and end time are equal",          # render reminder
]
LOG = os.path.join(os.path.expanduser("~"), "Desktop", "icmcp_dialogs.log")
_timer = None
_seen = set()


def _log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def _dialogs():
    from PySide2 import QtWidgets
    out = []
    for w in QtWidgets.QApplication.topLevelWidgets():
        if not w.isVisible() or not isinstance(w, QtWidgets.QDialog):
            continue
        texts = [l.text() for l in w.findChildren(QtWidgets.QLabel) if l.text().strip()]
        buttons = [b.text().replace("&", "") for b in w.findChildren(QtWidgets.QAbstractButton) if b.isVisible() and b.text()]
        out.append({"widget": w, "title": w.windowTitle(), "text": " | ".join(texts)[:500], "buttons": buttons,
                    "modal": w.isModal()})
    return out


def _press(w, label):
    from PySide2 import QtWidgets
    for b in w.findChildren(QtWidgets.QAbstractButton):
        if b.isVisible() and b.text().replace("&", "").strip().lower() == label.lower():
            b.click()
            return True
    return False


def scan():
    try:
        for d in _dialogs():
            key = (d["title"], d["text"])
            if key not in _seen:
                _seen.add(key)
                _log(f"DIALOG title={d['title']!r} text={d['text']!r} buttons={d['buttons']}")
            if any(p in d["text"] for p in AUTO_OK) and _press(d["widget"], "OK"):
                _log(f"AUTO-OK {d['title']!r}")
    except Exception as e:
        _log(f"scan error {e!r}")


def start(interval_ms=2000):
    global _timer
    if _timer is not None:
        return
    from PySide2 import QtCore
    _timer = QtCore.QTimer()
    _timer.setInterval(interval_ms)
    _timer.timeout.connect(scan)
    _timer.start()
    _log("dialog watcher started")


def list_dialogs(_args=None):
    return {"dialogs": [{k: v for k, v in d.items() if k != "widget"} for d in _dialogs()]}


def dismiss_dialog(args):
    """Press a named button on a visible dialog whose title or text contains `match`."""
    for d in _dialogs():
        if args["match"] in d["title"] or args["match"] in d["text"]:
            ok = _press(d["widget"], args.get("button", "OK"))
            _log(f"DISMISS via tool match={args['match']!r} button={args.get('button', 'OK')!r} ok={ok}")
            return {"ok": ok, "title": d["title"], "text": d["text"], "buttons": d["buttons"]}
    return {"ok": False, "error": "no visible dialog matches", "visible": list_dialogs()["dialogs"]}
