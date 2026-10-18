"""Offline tests for tools.weather.weather_file."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.weather import weather_file  # noqa: E402


def test_kinds_map_to_stock_files(tmp_path):
    (tmp_path / "Rain.iParticle").write_text("x")
    (tmp_path / "Snow Flake01.iParticle").write_text("x")
    (tmp_path / "Blizzard01.iParticle").write_text("x")
    assert weather_file("rain", str(tmp_path)).endswith("Rain.iParticle")
    assert weather_file("Snow", str(tmp_path)).endswith("Blizzard01.iParticle")
    assert weather_file("Snow Flake01", str(tmp_path)).endswith("Snow Flake01.iParticle")
    with pytest.raises(ValueError, match="Rain"):
        weather_file("hail", str(tmp_path))
