"""Offline tests for tools.texture_doctor with a fake RLPy (logic only; live proof: learning-log 2026-10-23)."""
import importlib
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _install_fake(images):
    """images: {(mesh, mat, channel_enum_name): (w, h)}; LoadImageToTexture adds to it."""
    rl = types.ModuleType("RLPy")
    names = ["Diffuse", "Normal", "Opacity", "Roughness", "Metallic", "Specular"]
    for n in names:
        setattr(rl, "EMaterialTextureChannel_" + n, "EMaterialTextureChannel_" + n)

    class RStatus:
        Success, Failure = 0, 1
    rl.RStatus = RStatus
    rl.EObjectType_Avatar, rl.EObjectType_Prop = "avatar", "prop"

    class Img:
        def __init__(self, w, h):
            self.w, self.h = w, h

        def GetWidth(self):
            return self.w

        def GetHeight(self):
            return self.h

        def SaveFile(self, path):
            open(path, "wb").write(b"png")
            return RStatus.Success

    class Color:
        def R(self):
            return 0.5
        G = B = R

    class Comp:
        def GetMaterialNames(self, mesh):
            return ["Skin_Body", "Shirt"]

        def GetShader(self, mesh, mat):
            return "PBR"

        def GetTextureWeights(self, mesh, mat):
            return (1.0,) * 12

        def HasImage(self, mesh, mat, ch):
            return (mesh, mat, ch) in images

        def GetImage(self, mesh, mat, ch):
            return Img(*images[(mesh, mat, ch)])

        def GetDiffuseColor(self, mesh, mat):
            return Color()

        def LoadImageToTexture(self, mesh, mat, ch, path):
            images[(mesh, mat, ch)] = (512, 512)
            return RStatus.Success

    class Obj:
        def GetName(self):
            return "Hero"

        def GetMeshNames(self):
            return ["Body"]

        def GetMaterialComponent(self):
            return Comp()

    class RScene:
        @staticmethod
        def FindObject(t, name):
            return Obj() if name == "Hero" and t == "avatar" else None

        @staticmethod
        def GetAvatars():
            return [Obj()]

        @staticmethod
        def GetProps():
            return []
    rl.RScene = RScene
    sys.modules["RLPy"] = rl
    import tools.texture_doctor as td
    return importlib.reload(td)


class TextureDoctorTest(unittest.TestCase):
    def test_report_flags_missing_diffuse_and_dumps(self):
        images = {("Body", "Skin_Body", "EMaterialTextureChannel_Diffuse"): (2048, 2048),
                  ("Body", "Shirt", "EMaterialTextureChannel_Normal"): (4, 4)}
        td = _install_fake(images)
        with tempfile.TemporaryDirectory() as d:
            r = td.texture_report({"dump_dir": d})
            mats = {m["material"]: m for m in r["objects"][0]["materials"]}
            self.assertEqual(mats["Skin_Body"]["flags"], [])
            self.assertIn("no_diffuse_texture", mats["Shirt"]["flags"])
            self.assertIn("tiny_normal", mats["Shirt"]["flags"])
            self.assertTrue(os.path.isfile(mats["Skin_Body"]["channels"]["diffuse"]["file"]))
            self.assertTrue(os.path.isfile(os.path.join(d, "texture_report.json")))
            self.assertEqual(r["suspect_materials"], 1)

    def test_relink_matches_by_material_name_dry_run_then_apply(self):
        images = {("Body", "Skin_Body", "EMaterialTextureChannel_Diffuse"): (2048, 2048)}
        td = _install_fake(images)
        with tempfile.TemporaryDirectory() as d:
            for f in ("Shirt_BaseColor.png", "Shirt_Normal.jpg", "Skin_Body_Diffuse.png", "Unrelated.png"):
                open(os.path.join(d, f), "wb").write(b"x")
            dry = td.relink_textures({"search_roots": [d]})
            got = sorted((p["material"], p["channel"]) for p in dry["plan"])
            self.assertEqual(got, [("Shirt", "diffuse"), ("Shirt", "normal")])  # Skin_Body diffuse already loaded
            self.assertFalse(dry["applied"])
            done = td.relink_textures({"search_roots": [d], "apply": True})
            self.assertEqual(done["loaded"], 2)

    def test_channel_suffixes(self):
        td = _install_fake({})
        self.assertEqual(td._channel_of("shirtbasecolor", "shirt"), "diffuse")
        self.assertEqual(td._channel_of("shirt", "shirt"), "diffuse")
        self.assertEqual(td._channel_of("shirtnrm", "shirt"), "normal")
        self.assertEqual(td._channel_of("shirtao", "shirt"), "ambient_occlusion")
        self.assertIsNone(td._channel_of("pants", "shirt"))


if __name__ == "__main__":
    unittest.main()
