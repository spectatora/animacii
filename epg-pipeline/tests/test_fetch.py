# -*- coding: utf-8 -*-
"""Тестове за свалянето. Без мрежа — всичко минава през фалшива сесия.

Проверяват се двете мълчаливи опасности от docstring-а на fetch.py:
HTML със статус 200 и прекъснат download. И инвариантът на data/:
при неуспех предишният валиден файл остава непокътнат.
"""

import gzip

import pytest
import requests

from epg_pipeline.fetch import FetchError, fetch_epg

XMLTV = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<tv generator-info-name="test">'
    b'<channel id="x"><display-name>X</display-name></channel>'
    b"</tv>"
)
GOOD_PAYLOAD = gzip.compress(XMLTV)

URL = "https://example.com/feed/all-3days.full.epg.xml.gz"


class FakeResponse:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content


class FakeSession:
    """Връща наредените отговори един по един; брои опитите.

    Елемент, който е изключение, се хвърля вместо да се върне —
    така се симулира мрежова грешка.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def fetch(tmp_path, responses, **kwargs):
    session = FakeSession(responses)
    kwargs.setdefault("retries", 3)
    kwargs.setdefault("backoff", 0)  # тестовете не спят
    path = None
    error = None
    try:
        path = fetch_epg(URL, tmp_path, session=session, **kwargs)
    except FetchError as exc:
        error = exc
    return path, error, session


# --- Успешният път ----------------------------------------------------------

def test_success_writes_file(tmp_path):
    path, error, session = fetch(tmp_path, [FakeResponse(200, GOOD_PAYLOAD)])
    assert error is None
    assert path == tmp_path / "all-3days.full.epg.xml.gz"  # името идва от URL-а
    assert path.read_bytes() == GOOD_PAYLOAD                # gzip-ът се пази 1:1
    assert session.calls == 1


def test_retry_after_transient_failures(tmp_path):
    """HTTP 500, после мрежова грешка, после успех — retry покрива и двете."""
    responses = [
        FakeResponse(500),
        requests.ConnectionError("connection reset"),
        FakeResponse(200, GOOD_PAYLOAD),
    ]
    path, error, session = fetch(tmp_path, responses)
    assert error is None
    assert path.read_bytes() == GOOD_PAYLOAD
    assert session.calls == 3


# --- Опасност 1: не-XMLTV съдържание със статус 200 -------------------------

BAD_PAYLOADS = [
    # HTML страница с грешка, коректно gzip-ната — минава decompress,
    # пада на коренния елемент.
    gzip.compress(b"<html><body>Rate limit exceeded</body></html>"),
    # Изобщо не е gzip (сурова HTML страница).
    b"<html><body>Not Found</body></html>",
    # Gzip, но вътре не е XML.
    gzip.compress(b"Internal Server Error"),
    # Празен отговор.
    b"",
]


@pytest.mark.parametrize("payload", BAD_PAYLOADS)
def test_invalid_content_rejected_and_retried(tmp_path, payload):
    responses = [FakeResponse(200, payload)] * 3
    path, error, session = fetch(tmp_path, responses)
    assert path is None
    assert error is not None
    assert session.calls == 3                     # невалидното съдържание също се retry-ва
    assert list(tmp_path.iterdir()) == []         # нищо не е докоснало data/


# --- Опасност 2: прекъснат download ------------------------------------------

def test_truncated_gzip_rejected(tmp_path):
    truncated = GOOD_PAYLOAD[:-5]  # без CRC опашката gzip-ът е невалиден
    path, error, _ = fetch(tmp_path, [FakeResponse(200, truncated)] * 3)
    assert path is None
    assert error is not None


# --- Инвариантът на data/ ----------------------------------------------------

def test_failure_preserves_previous_file(tmp_path):
    """Провален refresh не бива да съсипе последната валидна емисия."""
    dest = tmp_path / "all-3days.full.epg.xml.gz"
    dest.write_bytes(GOOD_PAYLOAD)

    path, error, _ = fetch(tmp_path, [FakeResponse(503)] * 3)
    assert path is None
    assert error is not None
    assert dest.read_bytes() == GOOD_PAYLOAD          # старият файл е непокътнат
    assert list(tmp_path.iterdir()) == [dest]         # и няма .tmp боклуци


def test_success_overwrites_previous_file_atomically(tmp_path):
    dest = tmp_path / "all-3days.full.epg.xml.gz"
    dest.write_bytes(b"old")

    new_payload = gzip.compress(XMLTV.replace(b'id="x"', b'id="y"'))
    path, error, _ = fetch(tmp_path, [FakeResponse(200, new_payload)])
    assert error is None
    assert path == dest
    assert dest.read_bytes() == new_payload
    assert list(tmp_path.iterdir()) == [dest]


def test_error_message_carries_last_cause(tmp_path):
    _, error, _ = fetch(tmp_path, [FakeResponse(403)] * 3)
    assert "HTTP 403" in str(error)
    assert "3" in str(error)  # споменава броя опити
