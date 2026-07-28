# -*- coding: utf-8 -*-
"""Зареждане на конфигурацията на каналите.

Един YAML файл: channel id от емисията -> наше име. Валидацията е строга
и шумна — тих проблем в конфига означава тихо изчезнал канал от данните.
"""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_CHANNELS_PATH = Path(__file__).resolve().parents[2] / "config" / "channels.yaml"


class ConfigError(Exception):
    """Конфигурацията липсва или е счупена."""


def load_channels(path: Path | str = DEFAULT_CHANNELS_PATH) -> dict[str, str]:
    """Връща {channel_id: наше име}. Гърми при празен или крив файл."""
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"липсва конфигурация на каналите: {path}") from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"невалиден YAML в {path}: {exc}") from exc

    channels = (raw or {}).get("channels")
    if not isinstance(channels, dict) or not channels:
        raise ConfigError(f"{path}: очаква се непразен mapping под ключ 'channels'")

    for cid, name in channels.items():
        if not isinstance(cid, str) or not isinstance(name, str) or not cid.strip() or not name.strip():
            raise ConfigError(f"{path}: крив запис {cid!r}: {name!r} — id и име трябва да са непразни низове")

    return {cid.strip(): name.strip() for cid, name in channels.items()}
