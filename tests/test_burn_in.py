"""Offline test for set_burn_in field validation and the field->widget map (UI driving measured on 8.75.5630.1)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes  # noqa: E402


class TestBurnIn(unittest.TestCase):
    def setUp(self):
        _install_fakes([], {})
        from tools import icmcp_extra
        self.x = icmcp_extra

    def test_every_text_field_has_a_checkbox(self):
        self.assertTrue(set(self.x._BURN_TEXT) <= set(self.x._BURN_FIELDS))

    def test_widget_names_are_the_measured_object_names(self):
        self.assertEqual(self.x._BURN_FIELDS["supervisor"], "qtHostnameCheckBox")
        self.assertEqual(self.x._BURN_FIELDS["lens"], "qtLensCheckBox")
        self.assertEqual(self.x._BURN_TEXT["note"], "qtNoteLineEdit")


if __name__ == "__main__":
    unittest.main()
