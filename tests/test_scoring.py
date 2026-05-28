from unittest.mock import MagicMock
from app.models.models import Position, PlayerMatchStats
from app.services.scoring import compute_points, DEFAULT_RULES, ScoreBreakdown


def _stats(**kw) -> PlayerMatchStats:
    defaults = dict(goals=0, assists=0, played=True, team_won=False, clean_sheet=False)
    defaults.update(kw)
    s = MagicMock(spec=PlayerMatchStats)
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


def test_goal_all_positions():
    for pos in Position:
        bd = compute_points(_stats(goals=1), pos)
        assert bd.goals_pts == DEFAULT_RULES["goal"]


def test_assist_all_positions():
    for pos in Position:
        bd = compute_points(_stats(assists=1), pos)
        assert bd.assists_pts == DEFAULT_RULES["assist"]


def test_team_win_all_positions():
    for pos in Position:
        bd = compute_points(_stats(team_won=True), pos)
        assert bd.team_win_pts == DEFAULT_RULES["team_win"]


def test_goalkeeper_clean_sheet():
    bd = compute_points(_stats(clean_sheet=True), Position.GK)
    assert bd.clean_sheet_pts == DEFAULT_RULES["goalkeeper_clean_sheet"]


def test_defender_clean_sheet():
    bd = compute_points(_stats(clean_sheet=True), Position.DEF)
    assert bd.clean_sheet_pts == DEFAULT_RULES["defender_clean_sheet"]


def test_midfielder_no_clean_sheet_bonus():
    bd = compute_points(_stats(clean_sheet=True), Position.MID)
    assert bd.clean_sheet_pts == 0.0


def test_forward_no_clean_sheet_bonus():
    bd = compute_points(_stats(clean_sheet=True), Position.FWD)
    assert bd.clean_sheet_pts == 0.0


def test_not_played_returns_zero_total():
    bd = compute_points(
        _stats(goals=2, assists=1, team_won=True, clean_sheet=True, played=False),
        Position.FWD,
    )
    assert bd.total == 0.0


def test_combined_forward_haul():
    bd = compute_points(_stats(goals=2, assists=1, team_won=True), Position.FWD)
    assert bd.goals_pts == 50.0
    assert bd.assists_pts == 20.0
    assert bd.team_win_pts == 10.0
    assert bd.total == 80.0


def test_total_property():
    bd = ScoreBreakdown(goals_pts=25, assists_pts=20, team_win_pts=10, clean_sheet_pts=10)
    assert bd.total == 65.0


def test_custom_rules_override():
    bd = compute_points(_stats(goals=1), Position.FWD, rules={"goal": 30.0})
    assert bd.goals_pts == 30.0


def test_custom_rules_partial_override():
    bd = compute_points(
        _stats(goals=1, assists=1, team_won=True),
        Position.MID,
        rules={"goal": 10.0},
    )
    assert bd.goals_pts == 10.0
    assert bd.assists_pts == DEFAULT_RULES["assist"]


def test_multiple_goals():
    bd = compute_points(_stats(goals=3), Position.FWD)
    assert bd.goals_pts == 75.0


def test_goalkeeper_win_and_clean_sheet():
    bd = compute_points(_stats(team_won=True, clean_sheet=True), Position.GK)
    assert bd.team_win_pts == 10.0
    assert bd.clean_sheet_pts == 25.0
    assert bd.total == 35.0
