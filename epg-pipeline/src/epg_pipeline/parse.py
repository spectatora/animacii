# -*- coding: utf-8 -*-
"""XMLTV -> излъчвания за следените канали.

Чете се стриймово (iterparse) направо през gzip — емисията съдържа 300+
канала, а ни трябват 11; няма смисъл да се строи дърво от 20 хиляди
елемента. Всяко излъчване носи И суровото заглавие, И нормализирания ключ:
`raw_title` никога не се замества (виж normalize.py защо), `norm_title` е
производната стойност, по която се групира.

Времената в XMLTV са "20260723002300 +0300" — parse-ват се до tz-aware
datetime и НЕ се местят в друга зона тук; конверсията е грижа на
хранилището.
"""

from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO, Iterator

from epg_pipeline.normalize import normalize_title

_TIME_FORMAT = "%Y%m%d%H%M%S %z"


class ParseError(Exception):
    """Емисията не може да бъде прочетена."""


@dataclass(frozen=True)
class Airing:
    """Едно излъчване. Ключът за групиране е norm_title, не raw_title."""

    channel_id: str
    channel: str          # нашето име от config/channels.yaml
    start: datetime       # tz-aware
    stop: datetime | None # някои източници не подават край
    raw_title: str
    norm_title: str
    description: str


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), _TIME_FORMAT)
    except ValueError:
        return None


def iter_airings(source: Path | str | IO[bytes], channels: dict[str, str]) -> Iterator[Airing]:
    """Стриймово чете XMLTV (.xml или .xml.gz) и дава излъчванията
    само за каналите от `channels` ({id: наше име}).

    Излъчване без заглавие или без валидно начало се прескача — то е
    неизползваемо и надолу по веригата само би сеело None проверки.
    """
    close_after = False
    if isinstance(source, (str, Path)):
        source = Path(source)
        stream: IO[bytes] = (
            gzip.open(source, "rb") if source.suffix == ".gz" else source.open("rb")
        )
        close_after = True
    else:
        stream = source

    try:
        for _, elem in ET.iterparse(stream, events=("end",)):
            if elem.tag != "programme":
                continue

            channel_id = elem.get("channel") or ""
            if channel_id in channels:
                raw_title = (elem.findtext("title") or "").strip()
                start = _parse_time(elem.get("start"))
                if raw_title and start is not None:
                    yield Airing(
                        channel_id=channel_id,
                        channel=channels[channel_id],
                        start=start,
                        stop=_parse_time(elem.get("stop")),
                        raw_title=raw_title,
                        norm_title=normalize_title(raw_title),
                        description=(elem.findtext("desc") or "").strip(),
                    )

            # iterparse трупа дървото — чистим обходените елементи,
            # иначе стриймовото четене е стрийм само на думи.
            elem.clear()
    except ET.ParseError as exc:
        raise ParseError(f"невалиден XMLTV: {exc}") from exc
    finally:
        if close_after:
            stream.close()


def parse_epg(source: Path | str | IO[bytes], channels: dict[str, str]) -> list[Airing]:
    """Като iter_airings, но материализирано и подредено по (канал, начало)."""
    airings = list(iter_airings(source, channels))
    airings.sort(key=lambda a: (a.channel, a.start))
    return airings
