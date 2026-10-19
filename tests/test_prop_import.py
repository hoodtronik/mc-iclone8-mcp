"""Offline tests for tools.prop_import.fit_scale and the spec's set[].file check."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_look_at import _install_fakes  # noqa: E402

_install_fakes([], {})
from tools.prop_import import fit_scale  # noqa: E402


def test_height_fits_the_mesh_height():
    assert fit_scale((-31, -21, 0), (31, 21, 54), height_cm=81) == pytest.approx(1.5)


def test_scale_is_used_without_height_and_defaults_to_one():
    assert fit_scale((0, 0, 0), (1, 1, 1), scale=2) == 2.0
    assert fit_scale((0, 0, 0), (1, 1, 1)) == 1.0


def test_flat_mesh_cannot_be_fitted_by_height():
    with pytest.raises(ValueError):
        fit_scale((0, 0, 5), (10, 10, 5), height_cm=50)


def test_spec_set_file_is_checked(tmp_path):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import spec_check
    (tmp_path / "crate.fbx").write_bytes(b"x")
    spec = {"length_s": 5, "set": [
        {"name": "Crate", "file": "crate.fbx", "at": [0, 0], "height_cm": 80},
        {"name": "Lamp", "file": "missing.obj"},
        {"name": "Tree", "file": "tree.blend"},
        {"file": "crate.fbx"}]}
    errs, _ = spec_check.check(spec, str(tmp_path))
    e = " | ".join(errs)
    assert "'Crate'" not in e
    assert "'Lamp'" in e and "not found" in e
    assert "'Tree'" in e and ".obj or .fbx" in e
    assert "needs a `name`" in e


def test_carry_lifts_travels_level_and_lowers():
    from tools.interactions import carry_keys
    keys = carry_keys((0, 0, 100), (50, 0, 95), 1.0, 3.0, lift_cm=8)
    assert [k[0] for k in keys] == [1.0, 1.4, 2.6, 3.0]
    assert keys[0][1] == (0, 0, 100) and keys[-1][1] == (50, 0, 95)
    assert keys[1][1] == (0, 0, 108) and keys[2][1] == (50, 0, 108)


def test_short_carry_shrinks_the_lift_phase():
    from tools.interactions import carry_keys
    keys = carry_keys((0, 0, 0), (10, 0, 0), 0.0, 0.8)
    assert keys[1][0] == 0.2 and keys[2][0] == 0.6


def test_spec_carry_is_checked():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import spec_check
    spec = {"length_s": 8, "set": [{"name": "Box", "size": [20, 20, 20], "at": [0, 0]}],
            "cast": [{"name": "A", "avatar": "x", "reach": [
                {"action": "carry", "object": "Box", "at_s": 1, "until_s": 3, "point": [0, 0, 90]},
                {"action": "carry", "object": "Box", "at_s": 4, "point": [0, 0, 90]},
                {"action": "carry", "object": "Box", "at_s": 5, "until_s": 6}]}]}
    errs, _ = spec_check.check(spec, ".")
    e = " | ".join(e for e in errs if "reach[" in e)
    assert "reach[0]" not in e
    assert "reach[1]" in e and "until_s" in e
    assert "reach[2]" in e and "`onto`" in e
