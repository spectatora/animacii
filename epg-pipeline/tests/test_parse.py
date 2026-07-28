# -*- coding: utf-8 -*-
"""Тестове за parse слоя.

XMLTV фрагментът е скроен по реалната емисия (снета 23.07.2026):
същият формат на времената, същите структури, реални заглавия.
"""

import gzip
import io
from datetime import datetime, timedelta, timezone

import pytest

from epg_pipeline.parse import ParseError, iter_airings, parse_epg

CHANNELS = {
    "nickelodeon.tv": "Nickelodeon",
    "disneychannel.bg": "Disney Channel",
}

XMLTV = """<?xml version="1.0" encoding="UTF-8"?>
<tv generator-info-name="test">
  <channel id="nickelodeon.tv"><display-name>Nickeldeon</display-name></channel>
  <channel id="disneychannel.bg"><display-name>Disney Channel</display-name></channel>
  <channel id="bnt1.bg"><display-name>БНТ 1</display-name></channel>
  <programme start="20260723002300 +0300" stop="20260723004600 +0300" channel="nickelodeon.tv">
    <title>Соник Прайм - сезон 1 епизод 9</title>
    <desc>В Бездната Шадоу пресреща Соник.</desc>
  </programme>
  <programme start="20260723060000 +0300" stop="20260723061500 +0300" channel="disneychannel.bg">
    <title>Блуи - Бабомобилът</title>
  </programme>
  <programme start="20260723070000 +0300" channel="disneychannel.bg">
    <title>Блуи - Блуи</title>
  </programme>
  <programme start="20260723120000 +0300" stop="20260723123000 +0300" channel="bnt1.bg">
    <title>По света и у нас</title>
  </programme>
  <programme start="20260723130000 +0300" stop="20260723133000 +0300" channel="nickelodeon.tv">
    <title></title>
  </programme>
</tv>
"""


def airings_from(xml_text, channels=CHANNELS):
    return parse_epg(io.BytesIO(xml_text.encode("utf-8")), channels)


def test_filters_to_configured_channels_only():
    airings = airings_from(XMLTV)
    # БНТ 1 не е в конфига; излъчването без заглавие се прескача.
    assert len(airings) == 3
    assert {a.channel_id for a in airings} == set(CHANNELS)


def test_raw_and_norm_are_both_kept():
    """Двете стойности пътуват заедно — raw никога не се замества."""
    sonic = next(a for a in airings_from(XMLTV) if "Соник" in a.raw_title)
    assert sonic.raw_title == "Соник Прайм - сезон 1 епизод 9"
    assert sonic.norm_title == "соник прайм"
    assert sonic.description == "В Бездната Шадоу пресреща Соник."


def test_norm_title_groups_different_episodes():
    """Смисълът на ключа: две излъчвания на Блуи -> един norm_title."""
    bluey = [a for a in airings_from(XMLTV) if a.norm_title == "блуи"]
    assert len(bluey) == 2
    assert bluey[0].raw_title != bluey[1].raw_title


def test_times_are_tz_aware():
    sonic = next(a for a in airings_from(XMLTV) if "Соник" in a.raw_title)
    plus3 = timezone(timedelta(hours=3))
    assert sonic.start == datetime(2026, 7, 23, 0, 23, tzinfo=plus3)
    assert sonic.stop == datetime(2026, 7, 23, 0, 46, tzinfo=plus3)


def test_missing_stop_is_none():
    open_ended = next(a for a in airings_from(XMLTV) if a.stop is None)
    assert open_ended.raw_title == "Блуи - Блуи"


def test_channel_gets_our_name_not_the_feeds():
    """Емисията казва "Nickeldeon" (sic) — ние казваме Nickelodeon, по id."""
    sonic = next(a for a in airings_from(XMLTV) if "Соник" in a.raw_title)
    assert sonic.channel == "Nickelodeon"


def test_sorted_by_channel_then_start():
    airings = airings_from(XMLTV)
    assert airings == sorted(airings, key=lambda a: (a.channel, a.start))


def test_reads_gzip_from_path(tmp_path):
    path = tmp_path / "feed.xml.gz"
    path.write_bytes(gzip.compress(XMLTV.encode("utf-8")))
    assert len(parse_epg(path, CHANNELS)) == 3


def test_reads_plain_xml_from_path(tmp_path):
    path = tmp_path / "feed.xml"
    path.write_text(XMLTV, encoding="utf-8")
    assert len(parse_epg(path, CHANNELS)) == 3


def test_broken_xml_raises_parse_error():
    with pytest.raises(ParseError):
        list(iter_airings(io.BytesIO(b"<tv><programme"), CHANNELS))
