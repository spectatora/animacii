# -*- coding: utf-8 -*-
"""Тестове за title map. Реалният файл се тества с реалните сливания,
снети от емисията на 23.07.2026; счупените файлове — с временни."""

import pytest

from epg_pipeline.title_map import TitleMapError, load_title_map


# --- Реалният config/title_map.csv ------------------------------------------

def test_real_map_merges_bluey_across_languages():
    tmap = load_title_map()
    assert tmap.resolve("bluey") == "Блуи"
    assert tmap.resolve("блуи") == "Блуи"
    assert tmap.resolve("bluey minisodes: season 2") == "Блуи"


def test_real_map_merges_the_two_turtle_translations():
    """Едно шоу, два превода: "Разказите" (Nickelodeon) и "Приказки"
    (Nicktoons) за костенурките нинджа."""
    tmap = load_title_map()
    assert (
        tmap.resolve("разказите на костенурките нинджа")
        == tmap.resolve("приказки за костенурките нинджа")
        == "Приказки за костенурките нинджа"
    )


def test_real_map_normalizes_raw_on_load():
    """В CSV-то стои "Batwheels , сезон 1 , епизод 28" (сурово, с епизодната
    опашка) — ключът се получава чак при зареждане."""
    tmap = load_title_map()
    assert tmap.resolve("batwheels") == "Batwheels"
    assert tmap.resolve("запознайте се с batwheels!") == "Batwheels"


def test_real_map_fixes_icarly():
    assert load_title_map().resolve("i - карли") == "iCarly"


def test_unmapped_key_passes_through():
    """Картата поправя изключенията — светът не се изброява."""
    assert load_title_map().resolve("пес патрул") == "пес патрул"


# --- Счупени файлове гърмят шумно -------------------------------------------

def write(tmp_path, text):
    path = tmp_path / "title_map.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_is_loud(tmp_path):
    with pytest.raises(TitleMapError, match="липсва"):
        load_title_map(tmp_path / "no-such.csv")


def test_conflicting_canonicals_are_an_error(tmp_path):
    """Два реда, чиито raw форми се нормализират до ЕДИН ключ, но сочат
    различни канонични имена — това е противоречие, не избор."""
    path = write(
        tmp_path,
        "raw_title,canonical\n"
        "Блуи - Бабомобилът,Блуи\n"
        '"Блуи, сез.1, еп.2",Bluey\n',   # и двете -> ключ "блуи"
    )
    with pytest.raises(TitleMapError, match="блуи"):
        load_title_map(path)


def test_duplicate_consistent_rows_are_fine(tmp_path):
    path = write(
        tmp_path,
        "raw_title,canonical\n"
        "Блуи - Бабомобилът,Блуи\n"
        "Блуи - Блуи,Блуи\n",
    )
    assert load_title_map(path).resolve("блуи") == "Блуи"


@pytest.mark.parametrize(
    "content",
    [
        "",                                       # празен файл
        "raw,canon\nБлуи,Блуи",                   # крив хедър
        "raw_title,canonical\nБлуи",              # липсваща колона
        "raw_title,canonical\nБлуи,Блуи,екстра",  # излишна колона
        "raw_title,canonical\n,Блуи",             # празно raw
        "raw_title,canonical\nБлуи,",             # празно канонично име
        "raw_title,canonical\n(п),Блуи",          # raw -> празен ключ
    ],
)
def test_broken_map_is_loud(tmp_path, content):
    with pytest.raises(TitleMapError):
        load_title_map(write(tmp_path, content))


def test_comments_and_blank_lines_are_skipped(tmp_path):
    path = write(
        tmp_path,
        "# коментар\n"
        "\n"
        "raw_title,canonical\n"
        "# още един коментар\n"
        "Блуи - Блуи,Блуи\n"
        "\n",
    )
    tmap = load_title_map(path)
    assert len(tmap) == 1
    assert tmap.resolve("блуи") == "Блуи"
