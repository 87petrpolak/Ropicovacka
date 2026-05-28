"""
Livesport data provider — STUB / placeholder.

WARNING: Scraping Livesport.com may be fragile and is subject to:
- Website terms of service and robots.txt
- HTML structure changes without notice
- Rate limiting or IP blocking
- Availability / downtime

This module is a placeholder for a future implementation.
Consider using an official football data API (e.g. football-data.org,
API-Football, StatsBomb Open Data) instead.
"""
from datetime import datetime
from typing import Optional

from app.providers.base import BaseFootballDataProvider, PlayerData, MatchData, PlayerStatsData


class LivesportFootballDataProvider(BaseFootballDataProvider):
    """
    Stub connector for Livesport-style HTML scraping.
    Implement _scrape_* methods when a real scraper is available.
    """

    def __init__(self, tournament_url: str = "", request_delay: float = 2.0):
        self.tournament_url = tournament_url
        self.request_delay = request_delay

    def fetch_players(self) -> list[PlayerData]:
        raise NotImplementedError(
            "LivesportFootballDataProvider.fetch_players is not yet implemented. "
            "Use CsvFootballDataProvider for the MVP."
        )

    def fetch_matches(self, since: Optional[datetime] = None) -> list[MatchData]:
        raise NotImplementedError(
            "LivesportFootballDataProvider.fetch_matches is not yet implemented."
        )

    def fetch_player_stats(self, match_external_id: str) -> list[PlayerStatsData]:
        raise NotImplementedError(
            "LivesportFootballDataProvider.fetch_player_stats is not yet implemented."
        )

    # ------------------------------------------------------------------
    # Placeholder private helpers for future implementation
    # ------------------------------------------------------------------

    def _scrape_match_list(self, since: Optional[datetime]) -> list[dict]:
        """Scrape match schedule/results page. NOT YET IMPLEMENTED."""
        raise NotImplementedError

    def _scrape_match_detail(self, match_url: str) -> dict:
        """Scrape individual match page for stats. NOT YET IMPLEMENTED."""
        raise NotImplementedError
