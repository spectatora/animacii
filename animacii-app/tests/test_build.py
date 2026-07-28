# -*- coding: utf-8 -*-
"""Тестове за генератора. Базата-фикстура се строи през реалния store слой
на pipeline-а — тестваме същия път, по който минават истинските данни."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from epg_pipeline.parse import Airing
from epg_pipeline.store import save_airings

from build import BuildError, build, load_model, render

PLUS3 = timezone(timedelta(hours=3))

# Фикстурите са с фиксирани дати, затова тестовете подават явен праг —
# "днес" за тях е 24.07.2026.
SINCE = datetime(2026, 7, 24, 0, 0, tzinfo=PLUS3)


def airing(hour, raw, norm, channel="Disney Junior", channel_id="disneyjunior.bg"):
    start = datetime(2026, 7, 24, hour, 0, tzinfo=PLUS3)
    return Airing(
        channel_id=channel_id, channel=channel,
        start=start, stop=start + timedelta(minutes=20),
        raw_title=raw, norm_title=norm, description="",
    )


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "epg.sqlite"
    save_airings(
        [
            airing(6, "Bluey - Bluey S1", "bluey"),
            airing(7, "Блуи - Блуи", "блуи"),
            airing(8, "Тафи - Бентли", "тафи", channel="Disney Channel", channel_id="disneychannel.bg"),
        ],
        path,
    )
    return path


@pytest.fixture
def title_map(tmp_path):
    path = tmp_path / "title_map.csv"
    path.write_text(
        "raw_title,canonical\nBluey - Bluey S1,Блуи\nБлуи - Блуи,Блуи\n",
        encoding="utf-8",
    )
    return path


def test_model_merges_shows_through_title_map(db, title_map):
    model = load_model(db, title_map, since=SINCE)
    names = [s["name"] for s in model["shows"]]
    assert names == ["Блуи", "тафи"]  # 3 ключа -> 2 предавания, сортирани

    bluey = model["shows"][0]
    assert len(bluey["airings"]) == 2
    assert bluey["channels"] == ["Disney Junior"]


def test_model_search_contains_all_name_variants(db, title_map):
    """Търсенето трябва да намира "Блуи" и по "bluey"."""
    bluey = load_model(db, title_map, since=SINCE)["shows"][0]
    assert "bluey" in bluey["search"]
    assert "блуи" in bluey["search"]


def test_model_times_and_channels(db, title_map):
    model = load_model(db, title_map, since=SINCE)
    assert model["channels"] == ["Disney Channel", "Disney Junior"]
    # 06:00 +03:00 -> 03:00 UTC; обхватът е от първото до последното начало
    assert model["range"]["from"] == "2026-07-24T03:00:00+00:00"
    assert model["range"]["to"] == "2026-07-24T05:00:00+00:00"


def test_history_stays_out_of_the_model(db, title_map):
    """Базата трупа история, но страницата носи само от `since` нататък —
    иначе index.html расте с всеки изминал ден."""
    base = airing(6, "Блуи - Блуи", "блуи")
    old = replace(base, start=base.start - timedelta(days=3),
                  stop=base.stop - timedelta(days=3))
    save_airings([old], db)

    model = load_model(db, title_map, since=SINCE)
    bluey = model["shows"][0]
    assert len(bluey["airings"]) == 2                       # старото не влиза
    assert model["range"]["from"] == "2026-07-24T03:00:00+00:00"


def test_stale_db_error_says_run_ingest(db, title_map):
    """Ако всичко в базата е по-старо от прага — ясна инструкция, не празна
    страница."""
    future = datetime(2026, 8, 1, 0, 0, tzinfo=PLUS3)
    with pytest.raises(BuildError, match="ingest"):
        load_model(db, title_map, since=future)


def test_missing_or_empty_db_is_loud(tmp_path, title_map):
    with pytest.raises(BuildError, match="липсва"):
        load_model(tmp_path / "no.sqlite", title_map)
    empty = tmp_path / "empty.sqlite"
    save_airings([], empty)
    with pytest.raises(BuildError, match="празна"):
        load_model(empty, title_map)


def test_build_writes_selfcontained_dist(db, title_map, tmp_path):
    out = tmp_path / "dist"
    index = build(db, title_map, out_dir=out, since=SINCE)

    html = index.read_text(encoding="utf-8")
    assert "/*__DATA_JSON__*/" not in html          # данните са влети
    assert '"Блуи"' not in html                     # ensure_ascii: кирилицата в
    assert "\\u0411\\u043b\\u0443\\u0438" in html   # данните е escape-ната
    assert "<h1>Анимации</h1>" in html

    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    assert [s["name"] for s in data["shows"]] == ["Блуи", "тафи"]


def test_rendered_data_cannot_break_out_of_script_tag(db, tmp_path, title_map):
    """Заглавие със '</script>' в него не бива да затваря script тага."""
    save_airings([airing(9, "Зло </script> шоу", "зло </script> шоу")], db)
    html = render(load_model(db, title_map, since=SINCE))
    assert "</script> шоу" not in html
    assert html.count("</script>") == 1  # само истинският затварящ таг
