from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class PlayerData:
    name: str
    country: str
    position: str
    club: Optional[str] = None
    external_id: Optional[str] = None


@dataclass
class MatchData:
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    played_at: Optional[datetime] = None
    external_id: Optional[str] = None
    round_name: Optional[str] = None
    round_number: Optional[int] = None
    is_finished: bool = True


@dataclass
class PlayerStatsData:
    player_external_id: Optional[str]
    player_name: str
    match_external_id: Optional[str]
    goals: int = 0
    assists: int = 0
    played: bool = False
    minutes_played: int = 0
    team_won: bool = False
    clean_sheet: bool = False


@dataclass
class RefreshResult:
    matches_added: int = 0
    matches_updated: int = 0
    stats_added: int = 0
    stats_updated: int = 0
    players_added: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @property
    def records_added(self) -> int:
        return self.matches_added + self.stats_added + self.players_added

    @property
    def records_updated(self) -> int:
        return self.matches_updated + self.stats_updated


class BaseFootballDataProvider(ABC):
    """Interface all data providers must implement."""

    @abstractmethod
    def fetch_players(self) -> list[PlayerData]:
        """Return list of players from the data source."""

    @abstractmethod
    def fetch_matches(self, since: Optional[datetime] = None) -> list[MatchData]:
        """Return matches, optionally filtered to those after `since`."""

    @abstractmethod
    def fetch_player_stats(self, match_external_id: str) -> list[PlayerStatsData]:
        """Return per-player stats for a single match."""
