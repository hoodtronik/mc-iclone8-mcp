"""See old characters without a screen: for each .iAvatar / .iProject (via iClone: load -> export_obj per avatar) or
.fbx/.obj/.glb (straight to Blender), render a front / 3-4 / side / back sheet with scripts/blender_turnaround.py.

  python scripts/turnaround_batch.py <out_dir> <file> [<file> ...]

# CLAUDE-NOTE (2026-10-23, hoodtronik fork): Ilyas remote + PC locked -> iClone can't draw. OBJ (current pose) is used,
# not FBX: FBX exploded the 2011 i-EL's iClone-4 wing accessory. Sheets land as <out_dir>/<name>_turnaround.png.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from icall import call  # noqa: E402

BLENDER = os.environ.get("BLENDER_EXE", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def render(model, out_dir, name):
    turn = os.path.join(out_dir, "turn_" + name)
    subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(HERE, "blender_turnaround.py"), "--", model, turn,
                    "--samples", "64", "--size", "1100"], capture_output=True, text=True, timeout=1800)
    views = [os.path.join(turn, v + ".png") for v in ("front", "threequarter", "side", "back")]
    if not all(os.path.isfile(v) for v in views):
        return None
    sheet = os.path.join(out_dir, name + "_turnaround.png")
    code = ("from PIL import Image\nims=[Image.open(f).convert('RGB') for f in %r]\nw,h=ims[0].size\n"
            "s=Image.new('RGB',(w*4,h))\n[s.paste(im,(i*w,0)) for i,im in enumerate(ims)]\ns.thumbnail((2400,2400))\ns.save(%r)" % (views, sheet))
    subprocess.run([sys.executable, "-c", code], check=True)
    return sheet


def from_iclone(path, out_dir):
    stem = os.path.splitext(os.path.basename(path))[0].replace(" ", "_").replace("(", "").replace(")", "")
    if path.lower().endswith(".iproject"):
        r = call("load_project", {"path": path, "save_current": False}, timeout=1800)
        avatars = r.get("avatars") or []
    else:
        call("new_project", {"save_current": False})
        code = ("import RLPy\nbefore={a.GetName() for a in RLPy.RScene.GetAvatars()}\nRLPy.RScene.ClearSelectObjects()\n"
                "RLPy.RFileIO.LoadFile(%r)\n_result=[a.GetName() for a in RLPy.RScene.GetAvatars() if a.GetName() not in before]" % path)
        avatars = call("python_exec", {"code": code}, timeout=1800).get("result") or []
    out = []
    for av in avatars:
        name = "%s__%s" % (stem, av.replace(" ", "_"))
        d = os.path.join(out_dir, "obj", name)
        os.makedirs(d, exist_ok=True)
        obj = os.path.join(d, name + ".obj")
        r = call("export_obj", {"name": av, "path": obj}, timeout=1800)
        out.append({"file": path, "avatar": av, "export": r.get("status"), "sheet": render(obj, out_dir, name) if os.path.isfile(obj) else None})
    return out


def main():
    out_dir, files = sys.argv[1], sys.argv[2:]
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for f in files:
        try:
            if f.lower().endswith((".iavatar", ".iproject")):
                results += from_iclone(f, out_dir)
            else:
                name = os.path.splitext(os.path.basename(f))[0]
                results.append({"file": f, "sheet": render(f, out_dir, name)})
        except Exception as e:
            results.append({"file": f, "error": str(e)[:300]})
        print(json.dumps(results[-1]), flush=True)


if __name__ == "__main__":
    main()
