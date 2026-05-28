"""CSV-based data provider. Reads pre-prepared CSV files."""
from __future__ import annotations
import csv
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Optional

from app.providers.base import BaseFootballDataProvider, PlayerData, MatchData, PlayerStatsData


class CsvFootballDataProvider(BaseFootballDataProvider):
    """Reads players, matches and stats from CSV files or file-like objects."""

    def __init__(
        self,
        players_csv: str | Path | StringIO | None = None,
        matches_csv: str | Path | StringIO | None = None,
        stats_csv: str | Path | StringIO | None = None,
    ):
        self._players_src = players_csv
        self._matches_src = matches_csv
        self._stats_src = stats_csv

    # ------------------------------------------------------------------
    # Required columns
    # players.csv:  name, country, position, club (opt), external_id (opt)
    # matches.csv:  home_team, away_team, home_score, away_score,
    #               played_at (opt), external_id (opt),
    #               round_name (opt), round_number (opt), is_finished (opt)
    # stats.csv:    player_name, match_external_id, goals, assists,
    #               played, team_won, clean_sheet,
    #               player_external_id (opt)
    # ------------------------------------------------------------------

    def fetch_players(self) -> list[PlayerData]:
        if self._players_src is None:
            return []
        rows = self._read_csv(self._players_src)
        players = []
        for r in rows:
            players.append(PlayerData(
                name=r["name"].strip(),
                country=r["country"].strip(),
                position=r["position"].strip().upper(),
                club=r.get("club", "").strip() or None,
                external_id=r.get("external_id", "").strip() or None,
            ))
        return players

    def fetch_matches(self, since: Optional[datetime] = None) -> list[MatchData]:
        if self._matches_src is None:
            return []
        rows = self._read_csv(self._matches_src)
        matches = []
        for r in rows:
            played_at = None
            if r.get("played_at", "").strip():
                for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d.%m.%Y"):
                    try:
                        played_at = datetime.strptime(r["played_at"].strip(), fmt)
                        break
                    except ValueError:
                        pass
            if since and played_at and played_at <= since:
                continue
            matches.append(MatchData(
                home_team=r["home_team"].strip(),
                away_team=r["away_team"].strip(),
                home_score=int(r["home_score"]),
                away_score=int(r["away_score"]),
                played_at=played_at,
                external_id=r.get("external_id", "").strip() or None,
                round_name=r.get("round_name", "").strip() or None,
                round_number=int(r["round_number"]) if r.get("round_number", "").strip() else None,
                is_finished=r.get("is_finished", "true").strip().lower() != "false",
            ))
        return matches

    def fetch_player_stats(self, match_external_id: str) -> list[PlayerStatsData]:
        if self._stats_src is None:
            return []
        rows = self._read_csv(self._stats_src)
        stats = []
        for r in rows:
            if r.get("match_external_id", "").strip() != match_external_id:
                continue
            stats.append(PlayerStatsData(
                player_name=r["player_name"].strip(),
                player_external_id=r.get("player_external_id", "").strip() or None,
                match_external_id=match_external_id,
                goals=int(r.get("goals", 0)),
                assists=int(r.get("assists", 0)),
                played=r.get("played", "true").strip().lower() != "false",
                team_won=r.get("team_won", "false").strip().lower() == "true",
                clean_sheet=r.get("clean_sheet", "false").strip().lower() == "true",
            ))
        return stats

    @staticmethod
    def _read_csv(src) -> list[dict]:
        if isinstance(src, (str, Path)):
            with open(src, encoding="utf-8") as f:
                return list(csv.DictReader(f))
        # file-like
        src.seek(0)
        return list(csv.DictReader(src))
