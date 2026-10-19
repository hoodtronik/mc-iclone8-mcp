"""Import an external mesh (OBJ / FBX) as a previz prop: answered import dialogs, a name, a size and a floor position."""
import os

import RLPy

_KINDS = (".obj", ".fbx")


def fit_scale(lo, hi, height_cm=None, scale=None):
    """Uniform scale for a mesh with bounds lo..hi (cm, at scale 1): height_cm wins over scale; default 1."""
    if height_cm:
        h = hi[2] - lo[2]
        if h <= 0:
            raise ValueError("the imported mesh has no height to fit")
        return float(height_cm) / h
    return float(scale) if scale else 1.0


def _bounds(obj):
    # CLAUDE-NOTE (2026-10-18, measured): GetBounds(max, center, min) reads stale until time moves; nudge first.
    fps = RLPy.RGlobal.GetFps()
    f = fps.GetFrameIndex(RLPy.RGlobal.GetTime())
    RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f + 1)); RLPy.RGlobal.SetTime(fps.IndexedFrameTime(f))
    mx, c, mn = RLPy.RVector3(), RLPy.RVector3(), RLPy.RVector3()
    obj.GetBounds(mx, c, mn)
    return (mn.x, mn.y, mn.z), (mx.x, mx.y, mx.z)


def _answer_import_modals(log, keep_hierarchy, tries=120):
    """Poll (every 250 ms, ~30 s) for the modal boxes an import raises and answer them, so the call cannot hang.
    # CLAUDE-NOTE (2026-10-18, measured): LoadFile on an .fbx blocks the main thread on 'FBX Import Settings' (fps:
    # Keep Original / Force + Convert All / Cancel) even for a mesh with no animation; QTimer callbacks still run
    # inside that modal loop, so we press Convert All (Keep Original is preselected). The manual's multi-mesh
    # 'keep hierarchy?' Yes/No box is answered from keep_hierarchy (not seen from Python: a 2-object OBJ merged
    # silently). The button-less 'Importing FBX file ...' progress box is
    # also modal and is left alone. Any OTHER modal is recorded and cancelled, so an unknown prompt fails the call instead of freezing."""
    from PySide2 import QtWidgets, QtCore
    left = [tries]

    def press(m, names):
        for want in names:
            for b in m.findChildren(QtWidgets.QAbstractButton):
                if b.isVisible() and b.text().replace("&", "").strip() == want:
                    b.click()
                    return want
        m.close()
        return "closed"

    def answer():
        if left[0] <= 0:                          # the import returned: never touch a later, unrelated dialog
            return
        m = QtWidgets.QApplication.activeModalWidget()
        if m is not None and m.isVisible():
            text = " | ".join(l.text() for l in m.findChildren(QtWidgets.QLabel) if l.text())
            low = text.lower()
            buttons = [b for b in m.findChildren(QtWidgets.QAbstractButton) if b.isVisible()]
            if not buttons or "importing" in low or "please wait" in low:
                pass                              # progress box ('Importing FBX file ...'): let it finish
            elif "fbx import settings" in low:
                log.append({"dialog": "FBX Import Settings", "pressed": press(m, ["Convert All"])})
            elif "hierarchy" in low or "merge" in low:
                log.append({"dialog": text[:160], "pressed": press(m, ["Yes"] if keep_hierarchy else ["No"])})
            else:
                log.append({"dialog": text[:200], "unexpected": True, "pressed": press(m, ["Cancel", "No", "Close", "OK"])})
        left[0] -= 1
        if left[0] > 0:
            QtCore.QTimer.singleShot(250, answer)
    QtCore.QTimer.singleShot(250, answer)
    return left


def import_prop(args):
    path = os.path.abspath(args["path"])
    if not os.path.isfile(path):
        raise FileNotFoundError("mesh file not found: %s" % path)
    if os.path.splitext(path)[1].lower() not in _KINDS:
        raise ValueError("import_prop takes .obj or .fbx (use load_object for .iProp)")
    before_p = {p.GetID() for p in RLPy.RScene.GetProps()}
    before_a = {a.GetID() for a in RLPy.RScene.GetAvatars()}
    log = []
    left = _answer_import_modals(log, bool(args.get("keep_hierarchy", False)))
    status = RLPy.RFileIO.LoadFile(path)
    left[0] = 0                                   # stop polling once LoadFile returns
    props = [p for p in RLPy.RScene.GetProps() if p.GetID() not in before_p and p.GetParent() is None]
    avatars = [a for a in RLPy.RScene.GetAvatars() if a.GetID() not in before_a]
    if any(d.get("unexpected") for d in log):
        raise RuntimeError("import stopped on an unexpected dialog: %s" % log)
    if avatars:
        return {"ok": False, "status": "imported as a character, not a prop (the file has a skeleton)",
                "avatars": [a.GetName() for a in avatars], "dialogs": log}
    if status != RLPy.RStatus.Success or not props:
        raise RuntimeError("iClone did not import %s as a prop (dialogs: %s)" % (path, log))
    obj = props[0]
    if args.get("name"):
        obj.SetName(args["name"])
    lo, hi = _bounds(obj)
    k = fit_scale(lo, hi, args.get("height_cm"), args.get("scale"))
    # CLAUDE-NOTE (2026-10-18, measured): OBJ/FBX import in cm with Z up (a Y-up OBJ and a metre-unit Blender FBX both
    # land at true size, upright, pivot at the file origin). Put the pivot at the base centre so `at`/bottom_z place
    # the mesh the way set[] primitives are placed, whatever origin the file had; then scale and place at frame 0.
    ctrl = obj.GetControl("Transform")
    ctrl.ClearKeys()
    zero = RLPy.RGlobal.GetFps().IndexedFrameTime(0)
    ident = RLPy.RQuaternion(RLPy.RVector4(0, 0, 0, 1))
    ctrl.SetValue(zero, RLPy.RTransform(RLPy.RVector3(k, k, k), ident, RLPy.RVector3(0, 0, 0)))
    lo, hi = _bounds(obj)
    base = RLPy.RVector3((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, lo[2])
    obj.SetPivot(base, RLPy.RVector3(0, 0, 0))
    from tools.common import euler_degrees_to_quaternion
    at = args.get("at", [0, 0])
    z = float(args.get("bottom_z", 0))
    ctrl.ClearKeys()
    ctrl.SetValue(zero, RLPy.RTransform(RLPy.RVector3(k, k, k), euler_degrees_to_quaternion(0, 0, float(args.get("turn_deg", 0))),
                                        RLPy.RVector3(float(at[0]), float(at[1]), z)))
    lo2, hi2 = _bounds(obj)
    size = [round(hi2[i] - lo2[i], 1) for i in range(3)]
    centre = [round((lo2[0] + hi2[0]) / 2.0, 1), round((lo2[1] + hi2[1]) / 2.0, 1)]
    err = max(abs(centre[0] - float(at[0])), abs(centre[1] - float(at[1])), abs(lo2[2] - z))
    out = {"ok": err < 1.0, "name": obj.GetName(), "scale": round(k, 4), "size_cm": size,
           "base_centre": centre + [round(lo2[2], 1)], "placement_error_cm": round(err, 2),
           "meshes": list(obj.GetMeshNames()), "dialogs": log}
    if len(props) > 1:
        out["also_imported"] = [p.GetName() for p in props[1:]]
    return out


def register(registry):
    registry["import_prop"] = {
        "handler": import_prop, "main_thread": True, "timeout": 300,
        "description": "IMPORT YOUR OWN MESH as a prop: path to an .obj or .fbx (from Blender, a kitbash, a download). "
                       "Answers iClone's import dialogs itself (FBX fps box -> Convert All; keep_hierarchy=false merges "
                       "parts), renames it (name), sizes it (height_cm fits the height, or uniform scale), moves its pivot "
                       "to the base centre and places that at at=[x,y] cm on bottom_z, turned turn_deg about Z, keyed at "
                       "frame 0. Reads back size and placement. Files with a skeleton come in as characters (reported, "
                       "not placed). Then hold_prop / link_to_bone / set_pivot / place_object work on it by name.",
        "inputSchema": {"type": "object", "properties": {
            "path": {"type": "string"}, "name": {"type": "string"}, "at": {"type": "array", "items": {"type": "number"}},
            "bottom_z": {"type": "number"}, "turn_deg": {"type": "number"}, "height_cm": {"type": "number"},
            "scale": {"type": "number"}, "keep_hierarchy": {"type": "boolean"}},
            "required": ["path"]}}
