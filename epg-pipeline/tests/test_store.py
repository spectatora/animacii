# -*- coding: utf-8 -*-
"""Тестове за хранилището. Ключовото свойство: идемпотентно вливане на
застъпващи се 3-дневни прозорци, без да се губи история."""

from datetime import datetime, timedelta, timezone

from epg_pipeline.parse import Airing
from epg_pipeline.store import connect, save_airings

PLUS3 = timezone(timedelta(hours=3))


def airing(start_hour=6, raw="Блуи - Бабомобилът", norm="блуи", desc="", channel_id="disneychannel.bg"):
    start = datetime(2026, 7, 23, start_hour, 0, tzinfo=PLUS3)
    return Airing(
        channel_id=channel_id,
        channel="Disney Channel",
        start=start,
        stop=start + timedelta(minutes=15),
        raw_title=raw,
        norm_title=norm,
        description=desc,
    )


def rows(db):
    with connect(db) as conn:
        return conn.execute("SELECT * FROM airings ORDER BY start_utc").fetchall()


def test_save_and_read_back(tmp_path):
    db = tmp_path / "epg.sqlite"
    assert save_airings([airing()], db) == 1

    (row,) = rows(db)
    assert row["raw_title"] == "Блуи - Бабомобилът"   # raw оцелява дословно
    assert row["norm_title"] == "блуи"
    # 06:00 +03:00 -> 03:00 UTC
    assert row["start_utc"] == "2026-07-23T03:00:00+00:00"
    assert row["stop_utc"] == "2026-07-23T03:15:00+00:00"


def test_reingest_is_idempotent(tmp_path):
    db = tmp_path / "epg.sqlite"
    save_airings([airing(), airing(start_hour=7)], db)
    save_airings([airing(), airing(start_hour=7)], db)  # същият прозорец втори път
    assert len(rows(db)) == 2


def test_overlapping_window_updates_and_preserves_history(tmp_path):
    """Ден 1 влива A и B; ден 2 влива поправен B и нов C.
    A (вече извън прозореца на емисията) трябва да оцелее."""
    db = tmp_path / "epg.sqlite"
    save_airings([airing(6), airing(7, desc="")], db)
    save_airings([airing(7, desc="Поправено описание."), airing(8)], db)

    all_rows = rows(db)
    assert len(all_rows) == 3                                # A + B + C
    assert all_rows[1]["description"] == "Поправено описание."  # B е опреснен


def test_same_start_on_different_channels_is_not_a_conflict(tmp_path):
    db = tmp_path / "epg.sqlite"
    save_airings([airing(), airing(channel_id="nick.tv")], db)
    assert len(rows(db)) == 2


def test_norm_title_is_queryable(tmp_path):
    """Заявката, около която ще се върти приложението: кога дават X?"""
    db = tmp_path / "epg.sqlite"
    save_airings(
        [airing(6, raw="Блуи - Бабомобилът"), airing(7, raw="Блуи - Блуи"), airing(8, raw="Тафи - Вълшебната лампа", norm="тафи")],
        db,
    )
    with connect(db) as conn:
        hits = conn.execute(
            "SELECT raw_title FROM airings WHERE norm_title = ? ORDER BY start_utc", ("блуи",)
        ).fetchall()
    assert [h["raw_title"] for h in hits] == ["Блуи - Бабомобилът", "Блуи - Блуи"]
