"""Headless Blender turnaround of an exported character (FBX/OBJ/GLB): front, 3/4, side, back stills + one sheet.
Works on a LOCKED Windows session (Blender renders offscreen; iClone's viewport does not).

  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b -P scripts/blender_turnaround.py -- <model.fbx> <out_dir> [--samples 48] [--size 900]

# CLAUDE-NOTE (2026-10-23, hoodtronik fork): Ilyas was remote with the PC locked, so iClone could not show the old
# characters. Route: iClone export_fbx (file I/O, works locked) -> this script -> PNGs sent to his phone.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
src, out = argv[0], argv[1]
samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 48
size = int(argv[argv.index("--size") + 1]) if "--size" in argv else 900
os.makedirs(out, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
ext = os.path.splitext(src)[1].lower()
if ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=src)
elif ext == ".obj":
    bpy.ops.wm.obj_import(filepath=src)
else:
    bpy.ops.import_scene.gltf(filepath=src)

meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]


def bbox():
    bpy.context.view_layer.update()
    return [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]


pts = bbox()
# CLAUDE-NOTE: iClone OBJ exports come in lying down (height along Blender Y): -90 deg about X stands it up facing -Y
# (measured on the 2011 i-EL: +90 left it upside down AND facing away). --flip uses +90 for files that come the other way.
ys, zs = [p.y for p in pts], [p.z for p in pts]
if (max(ys) - min(ys)) > 1.4 * (max(zs) - min(zs)):
    for o in bpy.context.scene.objects:
        if o.parent is None:
            o.rotation_euler.rotate_axis("X", math.radians(-90 if "--flip" not in argv else 90))
    pts = bbox()
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, dims = (lo + hi) / 2, hi - lo
print("BBOX", tuple(round(v, 3) for v in lo), tuple(round(v, 3) for v in hi), "meshes", len(meshes))

# alpha cards (feathers/hair/lashes): an "*Opacity*"/"*Transparency*" map or the base image's alpha drives Alpha
for m in bpy.data.materials:
    if m.use_nodes:
        bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        op = next((n for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image and any(
            k in n.image.name.lower() for k in ("opacity", "transparen", "alpha", "_d."))), None)
        if bsdf and not op:
            # CLAUDE-NOTE: iClone's OBJ .mtl omits opacity, but writes <mat>_opacity.<ext> beside <mat>_diffuse.<ext>.
            dif = next((n for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image and "_diffuse." in n.image.filepath.lower()), None)
            if dif:
                base = bpy.path.abspath(dif.image.filepath)
                stem = base[:base.lower().rfind("_diffuse.")]
                cand = [stem + "_opacity" + e for e in (".jpg", ".png", ".bmp", ".tga")]
                hit = next((c for c in cand if os.path.isfile(c)), None)
                if hit:
                    op = m.node_tree.nodes.new("ShaderNodeTexImage")
                    op.image = bpy.data.images.load(hit)
                    op.image.colorspace_settings.name = "Non-Color"
        if bsdf and op and not bsdf.inputs["Alpha"].is_linked:
            m.node_tree.links.new(op.outputs["Color"], bsdf.inputs["Alpha"])
for m in bpy.data.materials:
    if not m.use_nodes:
        continue
    for n in m.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED" and not n.inputs["Alpha"].is_linked:
            for l in m.node_tree.links:
                if l.to_node == n and l.to_socket.name == "Base Color" and l.from_node.type == "TEX_IMAGE" and l.from_node.image \
                        and l.from_node.image.alpha_mode != "NONE" and l.from_node.image.depth == 32:
                    m.node_tree.links.new(l.from_node.outputs["Alpha"], n.inputs["Alpha"])

sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = samples
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    sc.cycles.device = "GPU"
except Exception:
    pass
sc.render.resolution_x, sc.render.resolution_y = int(size * 0.75), size
sc.render.film_transparent = False
world = bpy.data.worlds.new("w")
sc.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.56, 0.58, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
for rot, energy in (((math.radians(50), 0, math.radians(30)), 3.0), ((math.radians(60), 0, math.radians(200)), 1.5)):
    s = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    s.data.energy, s.rotation_euler = energy, rot
    sc.collection.objects.link(s)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.lens = 70
height = max(dims.z, dims.x * 1.33, dims.y * 1.33)
# portrait frame: vertical FOV = 2*atan(18/lens) (sensor fit AUTO -> height); fit height or width*4/3, + half the depth
half = max(dims.z / 2, max(dims.x, dims.y) / 2 * (4 / 3)) * 1.12
dist = half / (18.0 / cam.data.lens) + max(dims.x, dims.y) / 2
target = center
cam.data.clip_start, cam.data.clip_end = dist * 0.01, dist * 10  # CLAUDE-NOTE: exports are in cm (260 units tall): default 100-unit clip_end cut them off
print('CAM dist', round(dist, 1), 'mats', len(bpy.data.materials))
for name, ang in (("front", 0), ("threequarter", 35), ("side", 90), ("back", 180)):
    # FBX from iClone imports Y-up converted to Z-up, character facing -Y
    a = math.radians(ang)
    cam.location = target + Vector((math.sin(a) * dist, -math.cos(a) * dist, 0))
    d = target - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(out, "%s.png" % name)
    bpy.ops.render.render(write_still=True)
    print("WROTE", sc.render.filepath)
