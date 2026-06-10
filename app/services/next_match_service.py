"""
Načte příští zápas MS 2026 pro každý tým.
Vrátí: {country_name: {"opponent": str, "date_str": str}}
Čas je převeden do Prague timezone (CEST = UTC+2).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

import requests

try:
    import streamlit as st
    _cache = st.cache_data(ttl=1800)
except Exception:
    def _cache(fn):
        return fn

_BASE = "https://1.flashscore.ninja/1/x/feed"
_HEADERS = {
    "x-fsign": "SW9D1eZo",
    "Referer": "https://www.livesport.cz/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}
WC_TOURNAMENT_ID = "lvUBR5F8"
PRAGUE_TZ = timezone(timedelta(hours=2))  # CEST (léto)


def _fetch(path: str) -> str:
    r = requests.get(f"{_BASE}/{path}", headers=_HEADERS, timeout=10)
    r.raise_for_status()
    return r.text


def _parse(raw: str) -> list[dict]:
    records = []
    for block in raw.split("~"):
        rec: dict[str, str] = {}
        for pair in block.split("¬"):
            if "÷" in pair:
                k, _, v = pair.partition("÷")
                rec[k] = v
        if rec:
            records.append(rec)
    return records


@_cache
def get_next_matches() -> dict[str, dict]:
    """
    Vrátí slovník: česky název týmu → info o příštím zápasu.
    Příklad: {"Norsko": {"opponent": "Irák", "date_str": "17.6. 20:00"}}
    """
    upcoming: dict[str, dict] = {}

    for day_offset in range(1, 20):
        try:
            raw = _fetch(f"f_1_{day_offset}_2_cs_1")
            records = _parse(raw)
            in_wc = False

            for rec in records:
                if "ZEE" in rec:
                    in_wc = rec.get("ZEE") == WC_TOURNAMENT_ID
                    continue
                if not in_wc or "AA" not in rec or "AE" not in rec:
                    continue
                # Jen naplánované (AB=1) nebo live (AB=2), ne dokončené (AB=3)
                if rec.get("AB") == "3":
                    continue

                home = rec.get("AE", "").strip()
                away = rec.get("AF", "").strip()

                ts = rec.get("AD", "")
                date_str = ""
                if ts:
                    try:
                        dt_utc = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                        dt_prague = dt_utc.astimezone(PRAGUE_TZ)
                        date_str = dt_prague.strftime("%-d.%-m. %H:%M")
                    except Exception:
                        pass

                for team, opponent in [(home, away), (away, home)]:
                    if team and team not in upcoming:
                        upcoming[team] = {
                            "opponent": opponent,
                            "date_str": date_str,
                        }

            time.sleep(0.15)

        except Exception:
            continue

    return upcoming
