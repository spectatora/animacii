# -*- coding: utf-8 -*-
"""Сваляне на XMLTV емисията.

Източникът е избран във Фаза 0 (виж docs/PHASE0.md): агрегираната емисия на
harrygg/EPG, публикувана като release asset. Три дни програма, обновява се
редовно, GitHub следва redirect-а от releases/latest автоматично.

Самото сваляне е умишлено скучно: requests + timeout + прост retry цикъл.
Реалните опасности са мълчаливите:

  1. Сървърът връща HTML страница (грешка, rate limit, заглушка) със статус
     200 — затова сваленото се проверява: цял gzip и коренен елемент <tv>.
  2. Прекъснат download оставя половин файл — затова се пише във временен
     файл и се мести атомарно чак СЛЕД проверката. В data/ никога не лежи
     невалиден файл; при неуспех предишният остава непокътнат.

Файлът остава gzip-нат на диска — parse слоят чете директно през gzip.
"""

from __future__ import annotations

import gzip
import io
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

DEFAULT_URL = (
    "https://github.com/harrygg/EPG/releases/latest/download/"
    "all-3days.full.epg.xml.gz"
)

# Корен на репото (src/epg_pipeline/fetch.py -> два родителя нагоре).
# Проектът се инсталира editable, така че пътят сочи към работното копие.
DEFAULT_DEST_DIR = Path(__file__).resolve().parents[2] / "data"

DEFAULT_TIMEOUT = 60.0
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 5.0


class FetchError(Exception):
    """Емисията не можа да бъде свалена или не издържа проверката."""


def _validate_xmltv_gz(payload: bytes) -> None:
    """Проверява, че payload е цял gzip архив с XMLTV документ вътре.

    gzip проверява CRC и дължина в края на потока, така че прекъснат
    download пада още на decompress — това покрива непълните файлове.
    От XML-а се гледа само коренният елемент: <tv> е XMLTV; <html> е
    страница с грешка, сервирана със статус 200. Пълният parse (и памет
    за него) е работа на parse слоя, не на свалянето.
    """
    if not payload:
        raise FetchError("празен отговор от сървъра")

    try:
        xml_bytes = gzip.decompress(payload)
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise FetchError(f"отговорът не е валиден gzip: {exc}") from exc

    try:
        _, root = next(ET.iterparse(io.BytesIO(xml_bytes), events=("start",)))
    except ET.ParseError as exc:
        raise FetchError(f"съдържанието не е валиден XML: {exc}") from exc
    except StopIteration:
        raise FetchError("XML без нито един елемент") from None

    if root.tag != "tv":
        raise FetchError(
            f"коренният елемент е <{root.tag}>, очаква се <tv> (XMLTV)"
        )


def fetch_epg(
    url: str = DEFAULT_URL,
    dest_dir: Path | str = DEFAULT_DEST_DIR,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
    session: requests.Session | None = None,
) -> Path:
    """Сваля емисията в dest_dir и връща пътя до файла.

    Файлът носи името на последния сегмент от URL-а. Retry се прави и при
    мрежова грешка, и при невалидно съдържание (transient HTML страници от
    CDN-а изглеждат точно така). Паузата между опитите расте линейно:
    backoff, 2*backoff, ...
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / url.rsplit("/", 1)[-1]
    tmp = dest.with_name(dest.name + ".tmp")

    own_session = session is None
    if own_session:
        session = requests.Session()

    last_error: Exception | None = None
    try:
        for attempt in range(1, retries + 1):
            try:
                resp = session.get(url, timeout=timeout)
                if resp.status_code != 200:
                    raise FetchError(f"HTTP {resp.status_code}")
                payload = resp.content
                _validate_xmltv_gz(payload)
            except (requests.RequestException, FetchError) as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(backoff * attempt)
                continue

            # Проверката мина — чак сега се пипа data/. Записът е във
            # временен файл + атомарен rename на същата файлова система.
            try:
                tmp.write_bytes(payload)
                tmp.replace(dest)
            except OSError:
                tmp.unlink(missing_ok=True)
                raise
            return dest
    finally:
        if own_session:
            session.close()

    raise FetchError(
        f"свалянето се провали след {retries} опита: {last_error}"
    ) from last_error


def main() -> None:
    path = fetch_epg()
    print(f"OK: {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
