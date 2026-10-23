"""Texture doctor: find materials whose textures did not load (the usual reason an old project or import "looks weird"),
dump the textures that DID load to PNG, and relink missing ones from disk by name.

# CLAUDE-NOTE (2026-10-23, hoodtronik fork): Ilyas: "figure out why [old files] look weird. usually its because the
# textures cant be found." RLPy has NO texture-path getter (RIMaterialComponent exposes HasImage / GetImage only), so
# a missing texture can only be seen as an EMPTY channel. Measured on iClone 8.74: HasImage(mesh, mat, eChannel) and
# GetImage(mesh, mat, eChannel) -> RIImage (GetWidth/GetHeight/SaveFile(path)). GetImage+SaveFile works with the Windows
# screen LOCKED (no viewport needed), so texture_report(dump_dir=...) is how an agent SEES materials when it can't render.
# Relinking is by NAME only (material name + channel suffix, e.g. "Skin_Body" -> Skin_Body_Diffuse.png), because the old
# file path is not readable from RLPy; offline path forensics live in scripts/rl_file_refs.py + scripts/fbx_texture_doctor.py.
"""
import os
import re
import json

import RLPy

_CH = {  # report name -> RLPy enum name (all channels this build exposes)
    "diffuse": "EMaterialTextureChannel_Diffuse", "diffuse_blend": "EMaterialTextureChannel_DiffuseBlend",
    "normal": "EMaterialTextureChannel_Normal", "bump": "EMaterialTextureChannel_Bump",
    "opacity": "EMaterialTextureChannel_Opacity", "specular": "EMaterialTextureChannel_Specular",
    "shininess": "EMaterialTextureChannel_Shininess", "glow": "EMaterialTextureChannel_Glow",
    "metallic": "EMaterialTextureChannel_Metallic", "roughness": "EMaterialTextureChannel_Roughness",
    "ambient_occlusion": "EMaterialTextureChannel_AmbientOcclusion", "reflection": "EMaterialTextureChannel_Reflection",
    "refraction": "EMaterialTextureChannel_Refraction", "displacement": "EMaterialTextureChannel_Displacement",
    "cube": "EMaterialTextureChannel_Cube",
}
# filename suffix -> channel (lower-case, alnum only). Order matters: longest first.
_SUFFIX = [("basecolor", "diffuse"), ("albedo", "diffuse"), ("diffuse", "diffuse"), ("color", "diffuse"), ("diff", "diffuse"),
           ("col", "diffuse"), ("normal", "normal"), ("nrm", "normal"), ("nor", "normal"), ("bump", "bump"), ("height", "bump"),
           ("opacity", "opacity"), ("alpha", "opacity"), ("transparency", "opacity"), ("specular", "specular"), ("spec", "specular"),
           ("roughness", "roughness"), ("rough", "roughness"), ("metallic", "metallic"), ("metalness", "metallic"),
           ("metal", "metallic"), ("ao", "ambient_occlusion"), ("occlusion", "ambient_occlusion"), ("emissive", "glow"),
           ("emission", "glow"), ("glow", "glow"), ("displacement", "displacement"), ("disp", "displacement")]
_IMG = (".png", ".jpg", ".jpeg", ".tga", ".bmp", ".dds", ".tif", ".tiff")


def _objects(name=None):
    if name:
        for t in (RLPy.EObjectType_Avatar, RLPy.EObjectType_Prop):
            o = RLPy.RScene.FindObject(t, name)
            if o is not None:
                return [o]
        raise ValueError("Object not found: %s" % name)
    out = []
    for o in list(RLPy.RScene.GetAvatars()) + list(RLPy.RScene.GetProps()):
        if o is not None and hasattr(o, "GetMaterialComponent"):
            out.append(o)
    return out


def _safe(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)[:80]


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def texture_report(args):
    dump = args.get("dump_dir")
    if dump:
        os.makedirs(dump, exist_ok=True)
    chans = {k: getattr(RLPy, v) for k, v in _CH.items() if hasattr(RLPy, v)}
    objects, n_mat, n_suspect = [], 0, 0
    for obj in _objects(args.get("name")):
        comp = obj.GetMaterialComponent()
        if comp is None:
            continue
        mats = []
        for mesh in obj.GetMeshNames():
            for mat in comp.GetMaterialNames(mesh):
                n_mat += 1
                item = {"mesh": mesh, "material": mat, "channels": {}, "flags": []}
                try:
                    item["shader"] = comp.GetShader(mesh, mat)
                except Exception:
                    pass
                try:
                    weights = list(comp.GetTextureWeights(mesh, mat))
                except Exception:
                    weights = []
                for cname, ch in chans.items():
                    try:
                        has = bool(comp.HasImage(mesh, mat, ch))
                    except Exception:
                        continue
                    if not has:
                        continue
                    info = {}
                    try:
                        img = comp.GetImage(mesh, mat, ch)
                        info["size"] = [img.GetWidth(), img.GetHeight()]
                        if info["size"][0] <= 8 or info["size"][1] <= 8:
                            item["flags"].append("tiny_%s" % cname)
                        if dump:
                            path = os.path.join(dump, "%s__%s__%s__%s.png" % (_safe(obj.GetName()), _safe(mesh), _safe(mat), cname))
                            if img.SaveFile(path) == RLPy.RStatus.Success and os.path.isfile(path):
                                info["file"] = path
                    except Exception as e:
                        info["error"] = str(e)[:120]
                    item["channels"][cname] = info
                if "diffuse" not in item["channels"]:
                    item["flags"].append("no_diffuse_texture")  # renders as a flat colour: the classic 'missing texture' look
                if weights and "diffuse" in item["channels"] and weights[0] == 0:
                    item["flags"].append("diffuse_weight_0")
                # CLAUDE-NOTE (2026-10-23): old iClone 4/5 alpha cards (feathers, hair strips, leaves) were one-sided; in
                # iClone 8 they vanish from behind/below -> patchy wings/hair. Measured on the 2011 i-EL: all 20 cards one-sided.
                try:
                    item["two_sided"] = bool(comp.IsTwoSidedMaterial(mesh, mat))
                    if "opacity" in item["channels"] and not item["two_sided"]:
                        item["flags"].append("one_sided_alpha_card")
                except Exception:
                    pass
                try:
                    c = comp.GetDiffuseColor(mesh, mat)
                    item["diffuse_color"] = [round(c.R(), 3), round(c.G(), 3), round(c.B(), 3)]
                except Exception:
                    pass
                n_suspect += bool(item["flags"])
                mats.append(item)
        objects.append({"name": obj.GetName(), "materials": mats})
    result = {"objects": objects, "materials": n_mat, "suspect_materials": n_suspect,
              "note": "no_diffuse_texture = no image in the diffuse channel (old path not found on import, or a colour-only "
                      "material). RLPy cannot read the old file path; use relink_textures (by name) or scripts/rl_file_refs.py."}
    if dump:
        with open(os.path.join(dump, "texture_report.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
        result["dump_dir"] = dump
    if args.get("only_suspect"):
        for o in objects:
            o["materials"] = [m for m in o["materials"] if m["flags"]]
    return result


def _index(roots, limit=300000):
    idx = {}
    n = 0
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if f.lower().endswith(_IMG):
                    idx.setdefault(_norm(os.path.splitext(f)[0]), []).append(os.path.join(dirpath, f))
                    n += 1
                    if n >= limit:
                        return idx, n, True
    return idx, n, False


def _channel_of(stem_norm, mat_norm):
    if stem_norm == mat_norm:
        return "diffuse"
    if not stem_norm.startswith(mat_norm):
        return None
    rest = stem_norm[len(mat_norm):]
    for suf, ch in _SUFFIX:
        if rest == suf or rest.endswith(suf):
            return ch
    return None


def relink_textures(args):
    """For every material channel WITHOUT an image, look for <material><suffix>.<img> under search_roots and load it."""
    roots = [r for r in args.get("search_roots", []) if os.path.isdir(r)]
    if not roots:
        raise ValueError("search_roots: give at least one existing folder")
    apply = bool(args.get("apply", False))
    want = set(args.get("channels") or ["diffuse", "normal", "opacity", "specular", "metallic", "roughness", "ambient_occlusion", "glow", "bump"])
    idx, n_files, truncated = _index(roots)
    plan, done = [], 0
    for obj in _objects(args.get("name")):
        comp = obj.GetMaterialComponent()
        for mesh in obj.GetMeshNames():
            for mat in comp.GetMaterialNames(mesh):
                mn = _norm(mat)
                if len(mn) < 3:
                    continue
                for stem, paths in idx.items():
                    ch = _channel_of(stem, mn)
                    if ch is None or ch not in want or ch not in _CH or not hasattr(RLPy, _CH[ch]):
                        continue
                    e = getattr(RLPy, _CH[ch])
                    if comp.HasImage(mesh, mat, e):
                        continue
                    row = {"object": obj.GetName(), "mesh": mesh, "material": mat, "channel": ch, "file": paths[0],
                           "alternatives": len(paths) - 1}
                    if apply:
                        st = comp.LoadImageToTexture(mesh, mat, e, paths[0])
                        row["loaded"] = (st == RLPy.RStatus.Success) and bool(comp.HasImage(mesh, mat, e))  # read-back
                        done += row["loaded"]
                    plan.append(row)
    return {"applied": apply, "matches": len(plan), "loaded": done, "indexed_images": n_files, "index_truncated": truncated,
            "plan": plan[:400], "note": "Name matching only (RLPy can't read the original path). Dry run unless apply=true; "
                                        "check a dump (texture_report dump_dir) before saving the project."}


def fix_alpha_cards(args):
    """Make one-sided materials that carry an opacity map two-sided (old iClone 4/5 cards). Dry run unless apply=true."""
    apply = bool(args.get("apply", False))
    skip = re.compile(args.get("skip_regex") or r"(?i)eye|teeth|tongue|cornea|lash|occlusion|tear")
    op = getattr(RLPy, _CH["opacity"])
    rows = []
    for obj in _objects(args.get("name")):
        comp = obj.GetMaterialComponent()
        for mesh in obj.GetMeshNames():
            for mat in comp.GetMaterialNames(mesh):
                if skip.search(mesh + " " + mat) or not comp.HasImage(mesh, mat, op) or comp.IsTwoSidedMaterial(mesh, mat):
                    continue
                row = {"object": obj.GetName(), "mesh": mesh, "material": mat}
                if apply:
                    row["set_ok"] = comp.SetTwoSidedMaterial(mesh, mat, True) == RLPy.RStatus.Success
                    row["two_sided"] = bool(comp.IsTwoSidedMaterial(mesh, mat))  # read-back
                rows.append(row)
    # CLAUDE-NOTE (2026-10-23): measured with the Windows screen LOCKED: SetTwoSidedMaterial returned Success on all 24
    # i-EL cards (and on a prop) but IsTwoSidedMaterial still read False. UNVERIFIED which side is wrong: confirm visually
    # (viewport from behind the wings) with the screen unlocked before trusting either value.
    return {"applied": apply, "count": len(rows), "materials": rows,
            "verified": apply and all(r.get("two_sided") for r in rows),
            "note": "Only changes the open scene; save to a NEW path (never over an archive original). If set_ok is true but "
                    "two_sided reads false, check the viewport: the getter/setter pair is UNVERIFIED (2026-10-23)."}


def register(registry):
    registry["fix_alpha_cards"] = {"handler": fix_alpha_cards, "main_thread": True, "timeout": 600,
        "description": "Old-file fix: set two-sided on one-sided materials that have an opacity map (iClone 4/5 feather/hair/leaf "
                       "cards that vanish from behind in iClone 8). Skips eyes/teeth/lashes. Dry run unless apply=true; reads back.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "apply": {"type": "boolean"},
                                                         "skip_regex": {"type": "string"}}}}
    registry["texture_report"] = {"handler": texture_report, "main_thread": True, "timeout": 900,
        "description": "Diagnose 'looks weird' materials: per object/mesh/material, which texture channels hold an image (size), "
                       "flags no_diffuse_texture (flat-colour = texture not found) / tiny / weight 0. dump_dir saves every loaded "
                       "texture as PNG + texture_report.json (works with the screen locked). name = one object, else all.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "dump_dir": {"type": "string"},
                                                         "only_suspect": {"type": "boolean"}}}}
    registry["relink_textures"] = {"handler": relink_textures, "main_thread": True, "timeout": 1800,
        "description": "Relink missing textures BY NAME: for channels with no image, find <material><suffix>.png/jpg/tga/dds "
                       "(Diffuse/BaseColor/Normal/Opacity/Roughness/Metallic/AO/Emissive...) under search_roots and load them. "
                       "Dry run unless apply=true; reads back HasImage after loading.",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"},
                                                         "search_roots": {"type": "array", "items": {"type": "string"}},
                                                         "channels": {"type": "array", "items": {"type": "string"}},
                                                         "apply": {"type": "boolean"}}, "required": ["search_roots"]}}
