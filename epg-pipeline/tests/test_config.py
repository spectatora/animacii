# -*- coding: utf-8 -*-
"""Тестове за конфигурацията на каналите."""

import pytest

from epg_pipeline.config import ConfigError, load_channels


def test_real_config_loads_the_eleven_channels():
    channels = load_channels()  # истинският config/channels.yaml
    assert len(channels) == 11
    # Закачането е по id — точките в id-тата са от емисията.
    assert channels["nickelodeon.tv"] == "Nickelodeon"
    assert channels["disneyjunior.bg"] == "Disney Junior"
    assert all("." in cid for cid in channels)


def test_missing_file_is_loud(tmp_path):
    with pytest.raises(ConfigError, match="липсва"):
        load_channels(tmp_path / "no-such.yaml")


@pytest.mark.parametrize(
    "content",
    [
        "",                          # празен файл
        "channels: {}",              # празен mapping
        "channels: [a, b]",          # list вместо mapping
        "channels:\n  '': Име",      # празно id
        "channels:\n  x.tv: ''",     # празно име
        "channels:\n  x.tv: 42",     # име, което не е низ
    ],
)
def test_broken_config_is_loud(tmp_path, content):
    path = tmp_path / "channels.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_channels(path)


def test_whitespace_is_stripped(tmp_path):
    path = tmp_path / "channels.yaml"
    path.write_text("channels:\n  ' x.tv ': ' Име '\n", encoding="utf-8")
    assert load_channels(path) == {"x.tv": "Име"}
