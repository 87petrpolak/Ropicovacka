"""
Konektor pro football-data.org API (free tier).

Co umí free tier:
  - výsledky zápasů (skóre, datum, kolo)
  - střelci gólů a přihrávky z pole goals[]
  - výhra/prohra/remíza
  - čisté konto (odvozeno ze skóre)

Co free tier NEUMÍ:
  - sestavy (kdo nastoupil) — víme jen střelce a asistenty
  - pozice hráčů — hráče importuj zvlášť přes CSV

Hráči bez gólu/asistence v daném zápase mají played=False.
Pro přesné "played" je potřeba paid tier nebo ruční CSV.

Rate limit free tieru: 10 requestů / minutu.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

import requests

from app.providers.base import (
    BaseFootballDataProvider,
    MatchData,
    PlayerData,
    PlayerStatsData,
)

BASE_URL = "https://api.football-data.org/v4"

# Kódy podporovaných soutěží
COMPETITION_NAMES = {
    "PL":  "Premier League (Anglie)",
    "CL":  "Liga mistrů",
    "BL1": "Bundesliga (Německo)",
    "SA":  "Serie A (Itálie)",
    "PD":  "La Liga (Španělsko)",
    "FL1": "Ligue 1 (Francie)",
    "PPL": "Primeira Liga (Portugalsko)",
    "WC":  "MS ve fotbale",
}


class FootballDataOrgProvider(BaseFootballDataProvider):
    """
    Provider pro football-data.org (free tier).
    Dokumentace: https://www.football-data.org/documentation/quickstart
    """

    def __init__(
        self,
        api_key: str,
        competition_code: str = "PL",
        matchday: Optional[int] = None,
        season: Optional[int] = None,
    ):
        self.api_key = api_key
        self.competition_code = competition_code
        self.matchday = matchday
        self.season = season

    # ------------------------------------------------------------------
    # Interní HTTP helper
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{BASE_URL}{path}"
        headers = {"X-Auth-Token": self.api_key}
        resp = requests.get(url, headers=headers, params=params or {}, timeout=15)
        if resp.status_code == 429:
            # Rate limit — počkej a zkus znovu
            time.sleep(61)
            resp = requests.get(url, headers=headers, params=params or {}, timeout=15)
        resp.raise_for_status()
        time.sleep(0.7)  # bezpečnostní pauza mezi requesty (limit 10/min)
        return resp.json()

    # ------------------------------------------------------------------
    # BaseFootballDataProvider implementace
    # ------------------------------------------------------------------

    def fetch_players(self) -> list[PlayerData]:
        # Hráče nezískáme z match endpointu — importuj je přes CSV
        return []

    def fetch_matches(self, since: Optional[datetime] = None) -> list[MatchData]:
        params: dict = {"status": "FINISHED"}
        if self.matchday:
            params["matchday"] = self.matchday
        if self.season:
            params["season"] = self.season

        data = self._get(f"/competitions/{self.competition_code}/matches", params)
        matches = []
        for m in data.get("matches", []):
            if m.get("status") != "FINISHED":
                continue

            score = m.get("score", {}).get("fullTime", {})
            home_score = score.get("home") or 0
            away_score = score.get("away") or 0

            played_at = None
            raw_date = m.get("utcDate", "")
            if raw_date:
                try:
                    played_at = datetime.fromisoformat(
                        raw_date.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except ValueError:
                    pass

            if since and played_at and played_at <= since:
                continue

            matchday = m.get("matchday")
            matches.append(MatchData(
                home_team=m["homeTeam"]["name"],
                away_team=m["awayTeam"]["name"],
                home_score=home_score,
                away_score=away_score,
                played_at=played_at,
                external_id=str(m["id"]),
                round_name=f"Kolo {matchday}" if matchday else None,
                round_number=matchday,
                is_finished=True,
            ))
        return matches

    def fetch_player_stats(self, match_external_id: str) -> list[PlayerStatsData]:
        data = self._get(f"/matches/{match_external_id}")

        score = data.get("score", {}).get("fullTime", {})
        home_score = score.get("home") or 0
        away_score = score.get("away") or 0
        home_team = data.get("homeTeam", {}).get("name", "")
        away_team = data.get("awayTeam", {}).get("name", "")

        player_stats: dict[str, dict] = {}

        def _get_or_create(player_id: str, player_name: str, team_name: str) -> dict:
            if player_id not in player_stats:
                team_won = (
                    (team_name == home_team and home_score > away_score)
                    or (team_name == away_team and away_score > home_score)
                )
                clean_sheet = (
                    (team_name == home_team and away_score == 0)
                    or (team_name == away_team and home_score == 0)
                )
                player_stats[player_id] = {
                    "player_external_id": player_id,
                    "player_name": player_name,
                    "match_external_id": match_external_id,
                    "goals": 0,
                    "assists": 0,
                    "played": True,
                    "team_won": team_won,
                    "clean_sheet": clean_sheet,
                }
            return player_stats[player_id]

        for goal in data.get("goals", []):
            team_name = goal.get("team", {}).get("name", "")
            scorer = goal.get("scorer")
            assist = goal.get("assist")

            if scorer and scorer.get("id"):
                s = _get_or_create(str(scorer["id"]), scorer["name"], team_name)
                s["goals"] += 1

            if assist and assist.get("id"):
                a = _get_or_create(str(assist["id"]), assist["name"], team_name)
                a["assists"] += 1

        return [PlayerStatsData(**s) for s in player_stats.values()]
