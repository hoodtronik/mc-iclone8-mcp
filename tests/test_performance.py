"""Offline tests for tools.performance's expression catalog / name resolution."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import performance as P  # noqa: E402


class TestExpressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        for rel in ("Digital Soul/4.Feel_Like/1.Pleased/Amused.iTalk", "Digital Soul/4.Feel_Like/1.Pleased/Comfortable_F.iTalk",
                    "Digital Soul/5.Feel_Dislike/3.Sad/Crying.iTalk", "_Default.iTalk"):
            path = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").close()
        self.roots = [root]

    def tearDown(self):
        self.tmp.cleanup()

    def test_catalog_groups_by_category(self):
        cat = P.catalog(self.roots)
        self.assertEqual(cat["Digital Soul/4.Feel_Like/1.Pleased"], ["Amused", "Comfortable_F"])
        self.assertIn(".", cat)

    def test_resolve_by_stem_category_and_mood(self):
        self.assertTrue(P.resolve("amused", self.roots).endswith("Amused.iTalk"))
        self.assertTrue(P.resolve("3.Sad/Crying.iTalk", self.roots).endswith("Crying.iTalk"))
        self.assertTrue(P.resolve("Sad", self.roots).endswith("Crying.iTalk"))
        self.assertTrue(P.resolve("Pleased", self.roots).endswith(".iTalk"))
        with self.assertRaises(FileNotFoundError):
            P.resolve("Furious", self.roots)


if __name__ == "__main__":
    unittest.main()
