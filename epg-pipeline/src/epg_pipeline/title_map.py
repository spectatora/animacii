# -*- coding: utf-8 -*-
"""Title map: слива ключове, които са едно и също предаване.

Нормализацията прави детерминираната текстообработка; тя нарочно НЕ решава
редакционни въпроси като "Bluey и Блуи едно предаване ли са". Това е работа
на ръчно поддържан CSV (config/title_map.csv): сурово заглавие -> канонично
име.

Договорът от normalize.py: CSV файлът пази СУРОВИ заглавия и се нормализира
тук, при зареждане. Никъде не влиза вече нормализиран ключ.

Резолюцията е едностъпкова и тотална: mapped ключ -> каноничното име,
всичко останало -> самият norm_title. Така картата поправя изключенията,
без да е длъжна да изброява света.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from epg_pipeline.normalize import normalize_title

DEFAULT_TITLE_MAP_PATH = Path(__file__).resolve().parents[2] / "config" / "title_map.csv"

_HEADER = ["raw_title", "canonical"]


class TitleMapError(Exception):
    """Картата липсва или е счупена. Гърми се шумно — тих проблем тук
    значи тихо раздвоено предаване."""


@dataclass(frozen=True)
class TitleMap:
    aliases: Mapping[str, str]  # norm ключ -> канонично име

    def resolve(self, norm_title: str) -> str:
        """Каноничното име за ключа; непознат ключ се връща непроменен."""
        return self.aliases.get(norm_title, norm_title)

    def __len__(self) -> int:
        return len(self.aliases)


def load_title_map(path: Path | str = DEFAULT_TITLE_MAP_PATH) -> TitleMap:
    """Чете CSV-то, нормализира суровите заглавия и връща картата.

    Редове, започващи с '#', и празни редове се прескачат. Конфликт
    (един ключ -> две различни канонични имена) е грешка, не избор.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise TitleMapError(f"липсва title map: {path}") from None

    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise TitleMapError(f"{path}: празен файл")

    reader = csv.reader(lines)
    header = next(reader)
    if [h.strip() for h in header] != _HEADER:
        raise TitleMapError(f"{path}: очаква се хедър {','.join(_HEADER)!r}, а е {header!r}")

    aliases: dict[str, str] = {}
    for lineno, row in enumerate(reader, start=2):
        if len(row) != 2:
            raise TitleMapError(f"{path}: ред {lineno}: очакват се 2 колони, а са {len(row)}")
        raw, canonical = (cell.strip() for cell in row)
        if not raw or not canonical:
            raise TitleMapError(f"{path}: ред {lineno}: празна колона")

        key = normalize_title(raw)
        if not key:
            raise TitleMapError(f"{path}: ред {lineno}: {raw!r} се нормализира до празен ключ")
        if key in aliases and aliases[key] != canonical:
            raise TitleMapError(
                f"{path}: ключ {key!r} сочи и към {aliases[key]!r}, и към {canonical!r}"
            )
        aliases[key] = canonical

    return TitleMap(aliases=MappingProxyType(aliases))
