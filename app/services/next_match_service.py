"""
Načte příští zápas MS 2026 pro každý tým.
Data jsou cachována v DB (TTL 2 hodiny), API se volá jen při cache miss.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta

import requests

_BASE = "https://1.flashscore.ninja/1/x/feed"
_HEADERS = {
    "x-fsign": "SW9D1eZo",
    "Referer": "https://www.livesport.cz/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}
WC_TOURNAMENT_ID = "lvUBR5F8"
PRAGUE_TZ = timezone(timedelta(hours=2))  # CEST (léto)

_CACHE_KEY_ALL = "ms_all_matches_v2"  # v2: zahrnuje i odehrané zápasy (day -14)
_CACHE_KEY_NEXT = "ms_next_matches"
_CACHE_TTL_HOURS = 2


# ----------------------------------------------------------------
# In-memory vrstva (sdílená v rámci jednoho Streamlit worker procesu)
# ----------------------------------------------------------------
try:
    import streamlit as st
    _mem_cache = st.cache_data(ttl=_CACHE_TTL_HOURS * 3600)
except Exception:
    def _mem_cache(fn):
        return fn


# ----------------------------------------------------------------
# DB cache helpers
# ----------------------------------------------------------------
def _db_get(key: str) -> list | dict | None:
    """Načte hodnotu z AppCache pokud není starší než TTL."""
    try:
        from app.db import SessionLocal
        from app.models.models import AppCache
        db = SessionLocal()
        try:
            row = db.get(AppCache, key)
            if row is None:
                return None
            age = (datetime.utcnow() - row.updated_at).total_seconds() / 3600
            if age > _CACHE_TTL_HOURS:
                return None
            return json.loads(row.value)
        finally:
            db.close()
    except Exception:
        return None


def _db_set(key: str, data) -> None:
    """Uloží nebo aktualizuje hodnotu v AppCache."""
    try:
        from app.db import SessionLocal
        from app.models.models import AppCache
        db = SessionLocal()
        try:
            row = db.get(AppCache, key)
            if row is None:
                row = AppCache(key=key, value=json.dumps(data), updated_at=datetime.utcnow())
                db.add(row)
            else:
                row.value = json.dumps(data)
                row.updated_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()
    except Exception:
        pass


# ----------------------------------------------------------------
# Flashscore API
# ----------------------------------------------------------------
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


def _fetch_all_from_api() -> list[dict]:
    all_matches = []
    seen_ids: set[str] = set()

    for day_offset in range(-14, 35):  # -14 = odehrané zápasy skupinové fáze
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

                match_id = rec["AA"]
                if match_id in seen_ids:
                    continue
                seen_ids.add(match_id)

                ts = rec.get("AD", "")
                date_str = time_str = ""
                played_at_iso = None
                if ts:
                    try:
                        dt_utc = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                        dt_prague = dt_utc.astimezone(PRAGUE_TZ)
                        played_at_iso = dt_utc.isoformat()
                        date_str = dt_prague.strftime("%-d.%-m.")
                        time_str = dt_prague.strftime("%H:%M")
                    except Exception:
                        pass

                all_matches.append({
                    "match_id": match_id,
                    "home": rec.get("AE", "").strip(),
                    "away": rec.get("AF", "").strip(),
                    "played_at_iso": played_at_iso,
                    "date_str": date_str,
                    "time_str": time_str,
                    "status": rec.get("AB", "1"),
                })

            time.sleep(0.1)
        except Exception:
            continue

    all_matches.sort(key=lambda x: x.get("played_at_iso") or "9999")
    return all_matches


def _deserialize_matches(raw_list: list[dict]) -> list[dict]:
    """Přidá zpět datetime objekt played_at (JSON ho neumí uložit přímo)."""
    result = []
    for m in raw_list:
        m = dict(m)
        iso = m.pop("played_at_iso", None)
        if iso:
            try:
                m["played_at"] = datetime.fromisoformat(iso)
            except Exception:
                m["played_at"] = None
        else:
            m["played_at"] = None
        result.append(m)
    return result


# ----------------------------------------------------------------
# Veřejné funkce — vrstvená cache: memory → DB → API
# ----------------------------------------------------------------
@_mem_cache
def get_all_ms_matches() -> list[dict]:
    """
    Vrátí všechny zápasy MS 2026 (nadcházející i odehrané).
    Každý zápas: {match_id, home, away, played_at (UTC datetime), date_str, time_str, status}
    Cachováno v DB po dobu 2 hodin.
    """
    cached = _db_get(_CACHE_KEY_ALL)
    if cached is not None:
        return _deserialize_matches(cached)

    raw = _fetch_all_from_api()
    _db_set(_CACHE_KEY_ALL, raw)
    return _deserialize_matches(raw)


@_mem_cache
def get_next_matches() -> dict[str, dict]:
    """
    Vrátí slovník: název týmu → info o příštím zápasu.
    Příklad: {"Norsko": {"opponent": "Irák", "date_str": "17.6. 20:00"}}
    Odvozeno z get_all_ms_matches() — bez extra API volání.
    """
    cached = _db_get(_CACHE_KEY_NEXT)
    if cached is not None:
        return cached

    now_utc = datetime.now(tz=timezone.utc)
    upcoming: dict[str, dict] = {}

    for m in get_all_ms_matches():
        if m.get("status") == "3":
            continue
        played_at = m.get("played_at")
        if played_at and played_at < now_utc:
            continue

        home = m.get("home", "")
        away = m.get("away", "")
        dt_str = ""
        if played_at:
            try:
                dt_prague = played_at.astimezone(PRAGUE_TZ)
                dt_str = dt_prague.strftime("%-d.%-m. %H:%M")
            except Exception:
                pass

        for team, opponent in [(home, away), (away, home)]:
            if team and team not in upcoming:
                upcoming[team] = {"opponent": opponent, "date_str": dt_str}

    _db_set(_CACHE_KEY_NEXT, upcoming)
    return upcoming


def invalidate_match_cache() -> None:
    """Smaže DB cache — zavolá se při manuálním refreshi dat."""
    try:
        from app.db import SessionLocal
        from app.models.models import AppCache
        db = SessionLocal()
        try:
            for key in [_CACHE_KEY_ALL, _CACHE_KEY_NEXT]:
                row = db.get(AppCache, key)
                if row:
                    db.delete(row)
            db.commit()
        finally:
            db.close()
    except Exception:
        pass
