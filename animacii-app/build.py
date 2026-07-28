# -*- coding: utf-8 -*-
"""animacii-app: статичен генератор върху epg.sqlite.

Чете базата на pipeline-а + title map и произвежда dist/:

  index.html — самодостатъчна страница (inline CSS/JS/данни), отваря се
               и от файловата система, и от GitHub Pages; нулев сървър.
  data.json  — същият модел като чист JSON, за програмно извличане.

Моделът се строи тук, на build време: групиране по предаване (през title
map), сортиране, search haystack. Браузърът само рисува и филтрира —
никаква бизнес логика в JS, за да има само едно място за поправяне.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from epg_pipeline.store import DEFAULT_DB_PATH
from epg_pipeline.title_map import DEFAULT_TITLE_MAP_PATH, load_title_map

APP_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE_PATH = APP_DIR / "template.html"
DEFAULT_OUT_DIR = APP_DIR / "dist"

_DATA_PLACEHOLDER = "/*__DATA_JSON__*/"


class BuildError(Exception):
    """Базата липсва или е празна — няма от какво да се строи."""


_SOFIA = ZoneInfo("Europe/Sofia")


def _today_start_utc() -> datetime:
    """Полунощ днес по софийско време, в UTC."""
    midnight = datetime.now(_SOFIA).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc)


def load_model(
    db_path: Path | str = DEFAULT_DB_PATH,
    title_map_path: Path | str = DEFAULT_TITLE_MAP_PATH,
    *,
    since: datetime | None = None,
) -> dict:
    """SQLite -> модел за страницата: предавания с излъчванията им.

    В модела влизат само излъчвания с начало от `since` нататък
    (по подразбиране: полунощ днес по софийско време). Базата трупа
    история без ограничение, но страницата носи само това, което
    потребителят може още да гледа — иначе index.html расте с всеки
    изминал ден.

    Ключът за групиране е каноничното име от title map (или самият
    norm_title за unmapped). Всяко предаване носи "search" — всички
    известни варианти на името, за да намира търсачката "Блуи" и по
    "bluey".
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise BuildError(f"липсва база: {db_path} — пусни ingest първо")

    since = since if since is not None else _today_start_utc()
    since_iso = since.astimezone(timezone.utc).isoformat()

    tmap = load_title_map(title_map_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT channel, start_utc, stop_utc, norm_title FROM airings"
        " WHERE start_utc >= ? ORDER BY start_utc",
        (since_iso,),
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM airings").fetchone()[0]
    conn.close()
    if not rows:
        if total:
            raise BuildError(
                f"в {db_path} има {total} излъчвания, но нито едно от"
                f" {since_iso} нататък — пусни ingest за свежи данни"
            )
        raise BuildError(f"базата е празна: {db_path}")

    shows: dict[str, dict] = {}
    for row in rows:
        name = tmap.resolve(row["norm_title"])
        show = shows.setdefault(
            name, {"name": name, "channels": [], "variants": set(), "airings": []}
        )
        show["variants"].add(row["norm_title"])
        if row["channel"] not in show["channels"]:
            show["channels"].append(row["channel"])
        show["airings"].append(
            {"ch": row["channel"], "s": row["start_utc"], "e": row["stop_utc"]}
        )

    for show in shows.values():
        show["channels"].sort()
        variants = show.pop("variants")
        show["search"] = " ".join(sorted({show["name"].lower(), *variants}))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "range": {"from": rows[0]["start_utc"], "to": rows[-1]["start_utc"]},
        "channels": sorted({row["channel"] for row in rows}),
        "shows": sorted(shows.values(), key=lambda s: s["name"].casefold()),
    }


def render(model: dict, template_path: Path | str = DEFAULT_TEMPLATE_PATH) -> str:
    """Влива модела в шаблона. ensure_ascii пази HTML-а от encoding драми,
    а '<' се escape-ва, за да не може заглавие да затвори <script> тага."""
    template = Path(template_path).read_text(encoding="utf-8")
    if _DATA_PLACEHOLDER not in template:
        raise BuildError(f"{template_path}: липсва placeholder {_DATA_PLACEHOLDER}")
    payload = json.dumps(model, ensure_ascii=True).replace("<", "\\u003c")
    return template.replace(_DATA_PLACEHOLDER, payload)


def build(
    db_path: Path | str = DEFAULT_DB_PATH,
    title_map_path: Path | str = DEFAULT_TITLE_MAP_PATH,
    template_path: Path | str = DEFAULT_TEMPLATE_PATH,
    out_dir: Path | str = DEFAULT_OUT_DIR,
    *,
    since: datetime | None = None,
) -> Path:
    """Строи dist/ и връща пътя до index.html."""
    model = load_model(db_path, title_map_path, since=since)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "data.json").write_text(
        json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    index = out_dir / "index.html"
    index.write_text(render(model, template_path), encoding="utf-8")
    return index


def main() -> None:
    index = build()
    model = json.loads((index.parent / "data.json").read_text(encoding="utf-8"))
    airings = sum(len(s["airings"]) for s in model["shows"])
    size_kb = index.stat().st_size // 1024
    print(f"OK: {index} ({size_kb} KB)")
    print(f"    {len(model['shows'])} предавания, {airings} излъчвания, "
          f"{len(model['channels'])} канала, от {model['range']['from']} нататък")


if __name__ == "__main__":
    main()
