from __future__ import annotations
from dataclasses import dataclass
from app.models.models import Position, PlayerMatchStats, PointsRule


DEFAULT_RULES = {
    "goal": 25.0,
    "assist": 20.0,
    "team_win": 10.0,
    "defender_clean_sheet": 10.0,
    "goalkeeper_clean_sheet": 25.0,
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

    if stats.team_won:
        bd.team_win_pts = r["team_win"]

    if stats.clean_sheet:
        if position == Position.GK:
            bd.clean_sheet_pts = r["goalkeeper_clean_sheet"]
        elif position == Position.DEF:
            bd.clean_sheet_pts = r["defender_clean_sheet"]

    return bd


def rules_from_db(db_rules: list[PointsRule]) -> dict:
    mapping = {
        "goal": "goal",
        "assist": "assist",
        "team_win": "team_win",
        "defender_clean_sheet": "defender_clean_sheet",
        "goalkeeper_clean_sheet": "goalkeeper_clean_sheet",
    }
    result = {}
    for rule in db_rules:
        if rule.name in mapping:
            result[mapping[rule.name]] = rule.points
    return result
