# -*- coding: utf-8 -*-
"""Дневният цикъл: сваляне -> parse -> SQLite.

Това е командата, която автоматизацията (GitHub Actions cron) ще пуска:

    python -m epg_pipeline.ingest

Идемпотентна е — може да се пуска колкото пъти е нужно.
"""

from __future__ import annotations

from epg_pipeline.config import load_channels
from epg_pipeline.fetch import fetch_epg
from epg_pipeline.parse import parse_epg
from epg_pipeline.store import DEFAULT_DB_PATH, save_airings


def main() -> None:
    channels = load_channels()
    feed_path = fetch_epg()
    airings = parse_epg(feed_path, channels)
    count = save_airings(airings)

    per_channel: dict[str, int] = {}
    for a in airings:
        per_channel[a.channel] = per_channel.get(a.channel, 0) + 1

    print(f"OK: {count} излъчвания от {len(per_channel)} канала -> {DEFAULT_DB_PATH}")
    for name in sorted(per_channel):
        print(f"  {name}: {per_channel[name]}")


if __name__ == "__main__":
    main()
