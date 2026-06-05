"""
Livesport.cz / Flashscore scraper.

Používá interní Flashscore API (flashscore.ninja) s proprietárním
¬-odděleným formátem. Token x-fsign je statický, uložený v jejich JS.

Endpointy:
  f_1_0_2_cs_1          — dnešní/aktuální výsledky všech fotbalových zápasů
  dc_1_{matchId}         — metadata zápasu (skóre, čas, týmy)
  df_sui_1_{matchId}     — incidents: góly, asistence, střídání, karty
  (soupiska)             — HTML stránka týmu /tym/{slug}/{teamId}/soupiska/

Minuty na hřišti:
  Nastoupil od začátku = 90 min (pokud nebyl střídán ven)
  Střídán ven v min X  = X minut
  Střídán dovnitř v min X = (90 - X) minut
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

from app.providers.base import BaseFootballDataProvider, PlayerData, MatchData, PlayerStatsData

_BASE = "https://1.flashscore.ninja/1/x/feed"
_LIVESPORT_BASE = "https://www.livesport.cz"
_HEADERS = {
    "x-fsign": "SW9D1eZo",
    "Referer": "https://www.livesport.cz/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}
_HTML_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "cs-CZ,cs;q=0.9",
    "Referer": "https://www.livesport.cz/",
}
_REQUEST_DELAY = 1.0

# Flashscore tournament ID pro MS 2026
WC_2026_TOURNAMENT_ID = "zeSHfCx3"

# Mapování českých pozic na interní enum
_POS_MAP = {
    "brankáři": "GK",
    "brankář": "GK",
    "obránci": "DEF",
    "obránce": "DEF",
    "záložníci": "MID",
    "záložník": "MID",
    "útočníci": "FWD",
    "útočník": "FWD",
}

# Typy incidentů
_INCIDENT_GOAL = "Gól"
_INCIDENT_OWN_GOAL = "Vlastní gól"
_INCIDENT_SUB_IN = "Střídání"
_INCIDENT_SUB_OUT = "Střídání - Out"


def _fetch(path: str) -> str:
    url = f"{_BASE}/{path}"
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    time.sleep(_REQUEST_DELAY)
    return resp.text


def _fetch_html(url: str) -> str:
    resp = requests.get(url, headers=_HTML_HEADERS, timeout=15)
    resp.raise_for_status()
    time.sleep(_REQUEST_DELAY)
    return resp.text


def _parse_feed(raw: str) -> list[dict]:
    """Parsuje ¬-oddělený Flashscore formát do seznamu slovníků."""
    records = []
    for block in raw.split("~"):
        block = block.strip()
        if not block:
            continue
        record: dict[str, str] = {}
        for pair in block.split("¬"):
            if "÷" in pair:
                key, _, val = pair.partition("÷")
                record[key] = val
        if record:
            records.append(record)
    return records


def _parse_minute(minute_str: str) -> int:
    """'75'' → 75, '90+2'' → 92"""
    s = minute_str.replace("'", "").strip()
    if "+" in s:
        base, extra = s.split("+", 1)
        try:
            return int(base) + int(extra)
        except ValueError:
            pass
    try:
        return int(s)
    except ValueError:
        return 0


def scrape_squad(team_slug: str, team_id: str, team_name: str) -> list[PlayerData]:
    """
    Stáhne soupisku týmu ze stránky Livesport.cz/tym/{slug}/{id}/soupiska/
    Vrátí seznam PlayerData s pozicí, jménem a external_id.
    """
    url = f"{_LIVESPORT_BASE}/tym/{team_slug}/{team_id}/soupiska/"
    html = _fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    players = []
    seen_ids: set[str] = set()
    current_pos = None
    in_players_section = False  # jen GK/DEF/MID/FWD sekce, ne trenéři

    for el in soup.select(".lineupTable .lineupTable__title, .lineupTable .lineupTable__row"):
        if "lineupTable__title" in el.get("class", []):
            title = el.get_text().strip().lower()
            pos = _POS_MAP.get(title)
            if pos:
                current_pos = pos
                in_players_section = True
            else:
                in_players_section = False  # trenéři / kouči
            continue

        if not in_players_section:
            continue

        link = el.select_one('a[href*="/hrac/"]')
        if not link:
            continue

        name = link.get_text().strip()
        href = link.get("href", "")
        m = re.search(r"/hrac/[^/]+/([A-Za-z0-9]+)/", href)
        player_id = m.group(1) if m else None

        if not name or not player_id:
            continue
        if player_id in seen_ids:
            continue
        seen_ids.add(player_id)

        players.append(PlayerData(
            name=name,
            country="",
            position=current_pos,
            club=team_name,
            external_id=player_id,
        ))

    return players


def fetch_match_metadata(match_id: str) -> dict:
    """Načte základní metadata zápasu (skóre, týmy, čas) přes dc_ endpoint."""
    raw = _fetch(f"dc_1_{match_id}")
    records = _parse_feed(raw)
    return records[0] if records else {}


class LivesportProvider(BaseFootballDataProvider):
    """
    Scraper pro livesport.cz (Flashscore backend).

    Dva režimy:
      - tournament_id: filtruje dnešní feed podle turnaje (pro živé MS zápasy)
      - match_ids: přímý import konkrétních historických zápasů
    """

    def __init__(
        self,
        tournament_id: str = WC_2026_TOURNAMENT_ID,
        match_ids: Optional[list[str]] = None,
    ):
        self.tournament_id = tournament_id
        self.match_ids = match_ids  # pokud je zadáno, ignoruje tournament_id a dnešní feed

    def fetch_players(self) -> list[PlayerData]:
        return []

    def fetch_matches(self, since: Optional[datetime] = None) -> list[MatchData]:
        """
        Pokud jsou zadány match_ids — načte tato konkrétní historická utkání.
        Jinak prochází dnešní feed a filtruje podle tournament_id.
        """
        if self.match_ids:
            return self._fetch_matches_by_ids(self.match_ids)
        return self._fetch_from_live_feed(since)

    def _fetch_matches_by_ids(self, match_ids: list[str]) -> list[MatchData]:
        """Načte metadata pro každý match_id zvlášť přes dc_ endpoint."""
        matches = []
        for match_id in match_ids:
            meta = fetch_match_metadata(match_id)
            if not meta:
                continue

            home_score = int(meta.get("DG", 0) or 0)
            away_score = int(meta.get("DH", 0) or 0)

            played_at = None
            raw_ts = meta.get("DC", "")
            if raw_ts:
                try:
                    played_at = datetime.utcfromtimestamp(int(raw_ts))
                except (ValueError, OSError):
                    pass

            # Týmy z dc_ endpointu nejsou přímo dostupné — použijeme match_id jako placeholder
            # Skutečné názvy týmů načteme z incidents feedu pokud jsou potřeba
            matches.append(MatchData(
                home_team="",
                away_team="",
                home_score=home_score,
                away_score=away_score,
                played_at=played_at,
                external_id=match_id,
                is_finished=True,
            ))

        return matches

    def _fetch_from_live_feed(self, since: Optional[datetime]) -> list[MatchData]:
        """Prochází dnešní feed a vrací dokončené zápasy daného turnaje."""
        raw = _fetch("f_1_0_2_cs_1")
        records = _parse_feed(raw)

        matches = []
        current_tournament_id = None

        for rec in records:
            if "ZEE" in rec:
                current_tournament_id = rec.get("ZEE", "")
                continue
            if "AA" not in rec:
                continue
            if self.tournament_id and current_tournament_id != self.tournament_id:
                continue
            if rec.get("AB") != "3":
                continue

            played_at = None
            raw_ts = rec.get("AD", "")
            if raw_ts:
                try:
                    played_at = datetime.utcfromtimestamp(int(raw_ts))
                except (ValueError, OSError):
                    pass

            if since and played_at and played_at <= since:
                continue

            matches.append(MatchData(
                home_team=rec.get("AE", ""),
                away_team=rec.get("AF", ""),
                home_score=int(rec.get("AG", 0) or 0),
                away_score=int(rec.get("AH", 0) or 0),
                played_at=played_at,
                external_id=rec["AA"],
                is_finished=True,
            ))

        return matches

    def fetch_player_stats(self, match_external_id: str) -> list[PlayerStatsData]:
        """Načte góly, asistence a minuty na hřišti pro daný zápas."""
        meta = fetch_match_metadata(match_external_id)
        home_score = int(meta.get("DG", 0) or 0)
        away_score = int(meta.get("DH", 0) or 0)

        home_won = home_score > away_score
        away_won = away_score > home_score
        home_clean = away_score == 0
        away_clean = home_score == 0

        raw = _fetch(f"df_sui_1_{match_external_id}")
        players = self._parse_incidents(raw, match_external_id, home_won, away_won, home_clean, away_clean)

        return [
            PlayerStatsData(
                player_external_id=p["player_external_id"],
                player_name=p["player_name"],
                match_external_id=p["match_external_id"],
                goals=p["goals"],
                assists=p["assists"],
                played=p["played"],
                minutes_played=p["minutes_played"],
                team_won=p["team_won"],
                clean_sheet=p["clean_sheet"],
            )
            for p in players.values()
        ]

    def _parse_incidents(
        self,
        raw: str,
        match_id: str,
        home_won: bool,
        away_won: bool,
        home_clean: bool,
        away_clean: bool,
        match_duration: int = 90,
    ) -> dict:
        players: dict[str, dict] = {}

        def _get_or_create(key: str, name: str, pid: str, team_side: str) -> dict:
            if key not in players:
                team_won = (team_side == "1" and home_won) or (team_side == "2" and away_won)
                clean_sheet = (team_side == "1" and home_clean) or (team_side == "2" and away_clean)
                players[key] = {
                    "player_external_id": pid or None,
                    "player_name": name,
                    "match_external_id": match_id,
                    "goals": 0,
                    "assists": 0,
                    "played": True,
                    "minutes_played": match_duration,
                    "team_won": team_won,
                    "clean_sheet": clean_sheet,
                    "_team_side": team_side,
                }
            return players[key]

        for block in raw.split("~"):
            if "III÷" not in block:
                continue

            # Parsuj celý blok jako klíč-hodnota
            kv: dict[str, list[str]] = {}
            for pair in block.split("¬"):
                if "÷" not in pair:
                    continue
                k, _, v = pair.partition("÷")
                kv.setdefault(k, []).append(v)

            team_side = kv.get("IA", [""])[0]
            minute = _parse_minute(kv.get("IB", ["0"])[0])

            # Každý blok může mít více IE/IF/IU/IM/IK záznamů (střelec + asistent)
            ie_list = kv.get("IE", [])
            if_list = kv.get("IF", [])
            iu_list = kv.get("IU", [])
            im_list = kv.get("IM", [])
            ik_list = kv.get("IK", [])

            for i, ik in enumerate(ik_list):
                name = if_list[i] if i < len(if_list) else ""
                url = iu_list[i] if i < len(iu_list) else ""
                pid = im_list[i] if i < len(im_list) else ""
                name = name.strip()
                if not name:
                    continue

                key = url.strip() or name

                if ik == _INCIDENT_GOAL:
                    p = _get_or_create(key, name, pid, team_side)
                    p["goals"] += 1

                elif ik in ("Asistence", "Asistace"):
                    p = _get_or_create(key, name, pid, team_side)
                    p["assists"] += 1

                elif ik == _INCIDENT_SUB_OUT:
                    p = _get_or_create(key, name, pid, team_side)
                    p["minutes_played"] = minute

                elif ik == _INCIDENT_SUB_IN:
                    p = _get_or_create(key, name, pid, team_side)
                    p["minutes_played"] = match_duration - minute

        return players
