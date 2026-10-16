"""QML panel automation (Tier C UI). Many iClone 8 panels (MD Controls, MotionLIVE, Video Mocap, ...) are QML scenes in
QQuickWindows embedded via IC::CQmlWidget, invisible to QWidget searches.
Tools: qml_inspect (dump a panel's items: class, objectName, text/tooltip/checked/value).
# CLAUDE-NOTE (2026-10-16, measured on MD Controls): QML buttons ignore QMetaObject.invokeMethod(item, "clicked") (returns
# True, nothing happens); a synthetic press/release QMouseEvent sent to the item's QQuickWindow at its scene centre works
# (no real cursor). Icon-only buttons are found by their `tooltip` property. Panels rebuild their item trees after some
# actions, so never keep item/window references across calls - look them up again.
"""
from PySide2 import QtCore, QtGui


def _items(item, out=None, depth=0):
    out = [] if out is None else out
    for c in item.childItems():
        out.append((depth, c))
        _items(c, out, depth + 1)
    return out


def _prop(item, name):
    mo = item.metaObject()
    if mo.indexOfProperty(name) < 0:
        return None
    try:
        return item.property(name)
    except Exception:          # e.g. QQuickIcon has no Python converter
        return None


def quick_windows():
    from PySide2.QtQuick import QQuickWindow
    return [w for w in QtGui.QGuiApplication.allWindows() if isinstance(w, QQuickWindow) and w.contentItem() is not None]


def window_with_text(text):
    """First QQuickWindow containing an item whose text == `text` (pick a label unique to the panel)."""
    for w in quick_windows():
        for _, c in _items(w.contentItem()):
            if str(_prop(c, "text")) == text:
                return w
    return None


def find(window, text=None, tooltip=None, cls_prefix=None):
    for _, c in _items(window.contentItem()):
        if cls_prefix and not c.metaObject().className().startswith(cls_prefix):
            continue
        if text is not None and str(_prop(c, "text")) != text:
            continue
        if tooltip is not None and str(_prop(c, "tooltip")) != tooltip:
            continue
        return c
    return None


def click(item, settle_ms=200):
    """Synthetic left click at the item's centre, delivered to its QQuickWindow."""
    import time
    from PySide2 import QtWidgets
    w = item.window()
    p = item.mapToScene(QtCore.QPointF(item.width() / 2.0, item.height() / 2.0))
    for t, buttons in ((QtCore.QEvent.MouseButtonPress, QtCore.Qt.LeftButton), (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton)):
        QtCore.QCoreApplication.sendEvent(w, QtGui.QMouseEvent(t, p, p, QtCore.Qt.LeftButton, buttons, QtCore.Qt.NoModifier))
        QtWidgets.QApplication.processEvents()
    for _ in range(max(1, settle_ms // 20)):
        QtWidgets.QApplication.processEvents(); time.sleep(0.02)
    return [round(p.x()), round(p.y())]


def dump(window, visible_only=True, limit=400):
    rows = []
    for depth, c in _items(window.contentItem()):
        p = {}
        for k in ("text", "tooltip", "checked", "visible", "enabled", "value", "currentIndex"):
            v = _prop(c, k)
            if v is not None and v != "":
                p[k] = str(v)[:60]
        if visible_only and p.get("visible") == "False":
            continue
        if c.objectName() or p.get("text") or p.get("tooltip"):
            rows.append({"depth": depth, "class": c.metaObject().className()[:40], "name": c.objectName(), **p})
        if len(rows) >= limit:
            break
    return rows


def qml_inspect(args):
    """Dump the QML panel that contains `anchor_text` (or list every QML window's first texts when omitted)."""
    if args.get("anchor_text"):
        w = window_with_text(args["anchor_text"])
        if w is None:
            raise ValueError(f"no QML window shows the text {args['anchor_text']!r} (is the panel open?)")
        rows = dump(w, not args.get("include_hidden", False), int(args.get("limit", 300)))
        if args.get("filter"):
            f = args["filter"].lower()
            rows = [r for r in rows if f in (r.get("text", "") + r.get("tooltip", "") + r["name"]).lower()]
        return {"ok": True, "items": rows}
    out = []
    for w in quick_windows():
        texts = [str(_prop(c, "text")) for _, c in _items(w.contentItem()) if _prop(c, "text")][:6]
        if texts:
            out.append({"class": w.metaObject().className(), "visible": w.isVisible(), "first_texts": texts})
    return {"ok": True, "windows": out}


def register(registry):
    registry["qml_inspect"] = {
        "handler": qml_inspect, "main_thread": True,
        "description": "UI RE helper: dump a QML panel (MD Controls, MotionLIVE, ...) found by a text it shows "
                       "(anchor_text), or list all QML windows. Items: class, objectName, text/tooltip/checked/value. "
                       "Use it to find controls before automating a panel; icon buttons are identified by tooltip.",
        "inputSchema": {"type": "object", "properties": {
            "anchor_text": {"type": "string"}, "filter": {"type": "string"},
            "include_hidden": {"type": "boolean"}, "limit": {"type": "integer"}}, "required": []}}
