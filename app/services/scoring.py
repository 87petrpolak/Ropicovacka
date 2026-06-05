from __future__ import annotations
from dataclasses import dataclass
from app.models.models import Position, PlayerMatchStats, PointsRule

MIN_MINUTES_FOR_BONUS = 60

DEFAULT_RULES = {
    "goal": 30.0,
    "assist": 25.0,
    "mid_team_win": 15.0,
    "def_team_win": 15.0,
    "defender_clean_sheet": 15.0,
    "goalkeeper_clean_sheet": 30.0,
}


@dataclass
class ScoreBreakdown:
    goals_pts: float = 0.0
    assists_pts: float = 0.0
    team_win_pts: float = 0.0
    clean_sheet_pts: float = 0.0

    @property
    def total(self) -> float:
        return self.goals_pts + self.assists_pts + self.team_win_pts + self.clean_sheet_pts


def compute_points(
    stats: PlayerMatchStats,
    position: Position,
    rules: dict | None = None,
) -> ScoreBreakdown:
    r = {**DEFAULT_RULES, **(rules or {})}
    bd = ScoreBreakdown()

    if not stats.played:
        return bd

    bd.goals_pts = stats.goals * r["goal"]
    bd.assists_pts = stats.assists * r["assist"]

    qualified = stats.minutes_played >= MIN_MINUTES_FOR_BONUS

    if position == Position.MID:
        if stats.team_won and qualified:
            bd.team_win_pts = r["mid_team_win"]

    elif position == Position.DEF:
        if stats.team_won and qualified:
            bd.team_win_pts = r["def_team_win"]
        if stats.clean_sheet and qualified:
            bd.clean_sheet_pts = r["defender_clean_sheet"]

    elif position == Position.GK:
        if stats.clean_sheet and qualified:
            bd.clean_sheet_pts = r["goalkeeper_clean_sheet"]

    # FWD: pouze góly a asistence, žádné bonusy za výhru/čisté konto

    return bd


def rules_from_db(db_rules: list[PointsRule]) -> dict:
    mapping = {
        "goal": "goal",
        "assist": "assist",
        "mid_team_win": "mid_team_win",
        "def_team_win": "def_team_win",
        "defender_clean_sheet": "defender_clean_sheet",
        "goalkeeper_clean_sheet": "goalkeeper_clean_sheet",
        "team_win": "mid_team_win",  # zpětná kompatibilita
    }
    result = {}
    for rule in db_rules:
        if rule.name in mapping:
            result[mapping[rule.name]] = rule.points
    return result
