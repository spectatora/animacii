# -*- coding: utf-8 -*-
"""Хранилище: SQLite, нулева инфраструктура.

Обемът е ~2000 излъчвания на ден за 11 канала — SQLite го носи с
десетилетия запас, а файлът в data/ се шери и архивира тривиално.

Емисията е подвижен прозорец от 3 дни, а ingest-ът върви всеки ден, така
че прозорците се застъпват. Ключът (channel_id, start_utc) + UPSERT прави
повторното вливане идемпотентно: застъпеното се опреснява (източникът
понякога поправя заглавия/описания), новото се добавя, а излъчвания от
СТАРИ прозорци не се пипат — така базата натрупва история, по-дълга от
трите дни на емисията.

Времената се пишат като UTC ISO 8601 ("2026-07-22T21:23:00+00:00"):
еднаква дължина, лексикографската и хронологичната подредба съвпадат.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from epg_pipeline.parse import Airing

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "epg.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS airings (
    channel_id  TEXT NOT NULL,
    channel     TEXT NOT NULL,
    start_utc   TEXT NOT NULL,
    stop_utc    TEXT,
    raw_title   TEXT NOT NULL,
    norm_title  TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (channel_id, start_utc)
);
CREATE INDEX IF NOT EXISTS idx_airings_norm_title ON airings (norm_title);
CREATE INDEX IF NOT EXISTS idx_airings_start ON airings (start_utc);
"""


def _utc_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Отваря базата и подсигурява схемата. Пътят се създава при нужда."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def save_airings(airings: Iterable[Airing], db_path: Path | str = DEFAULT_DB_PATH) -> int:
    """Влива излъчванията с UPSERT и връща броя им. Идемпотентно."""
    rows = [
        (
            a.channel_id,
            a.channel,
            _utc_iso(a.start),
            _utc_iso(a.stop),
            a.raw_title,
            a.norm_title,
            a.description,
        )
        for a in airings
    ]
    with connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO airings
                (channel_id, channel, start_utc, stop_utc, raw_title, norm_title, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (channel_id, start_utc) DO UPDATE SET
                channel     = excluded.channel,
                stop_utc    = excluded.stop_utc,
                raw_title   = excluded.raw_title,
                norm_title  = excluded.norm_title,
                description = excluded.description
            """,
            rows,
        )
    return len(rows)
