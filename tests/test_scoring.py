from unittest.mock import MagicMock
from app.models.models import Position, PlayerMatchStats
from app.services.scoring import compute_points, DEFAULT_RULES, ScoreBreakdown, MIN_MINUTES_FOR_BONUS


def _stats(**kw) -> PlayerMatchStats:
    defaults = dict(goals=0, assists=0, played=True, minutes_played=90, team_won=False, clean_sheet=False)
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


def test_not_played_returns_zero_total():
    bd = compute_points(
        _stats(goals=2, assists=1, team_won=True, clean_sheet=True, played=False),
        Position.FWD,
    )
    assert bd.total == 0.0


# ----------------------------------------------------------------
# Útočník — jen góly a asistence, žádné bonusy
# ----------------------------------------------------------------

def test_forward_goal_and_assist():
    bd = compute_points(_stats(goals=2, assists=1), Position.FWD)
    assert bd.goals_pts == 60.0
    assert bd.assists_pts == 25.0
    assert bd.team_win_pts == 0.0
    assert bd.clean_sheet_pts == 0.0
    assert bd.total == 85.0


def test_forward_no_team_win_bonus():
    bd = compute_points(_stats(team_won=True), Position.FWD)
    assert bd.team_win_pts == 0.0


def test_forward_no_clean_sheet_bonus():
    bd = compute_points(_stats(clean_sheet=True), Position.FWD)
    assert bd.clean_sheet_pts == 0.0


# ----------------------------------------------------------------
# Záložník — výhra jen při 60+ min
# ----------------------------------------------------------------

def test_midfielder_win_with_60min():
    bd = compute_points(_stats(team_won=True, minutes_played=60), Position.MID)
    assert bd.team_win_pts == DEFAULT_RULES["mid_team_win"]


def test_midfielder_win_without_60min():
    bd = compute_points(_stats(team_won=True, minutes_played=59), Position.MID)
    assert bd.team_win_pts == 0.0


def test_midfielder_no_clean_sheet_bonus():
    bd = compute_points(_stats(clean_sheet=True), Position.MID)
    assert bd.clean_sheet_pts == 0.0


# ----------------------------------------------------------------
# Obránce — výhra a čisté konto, oba při 60+ min
# ----------------------------------------------------------------

def test_defender_win_with_60min():
    bd = compute_points(_stats(team_won=True, minutes_played=90), Position.DEF)
    assert bd.team_win_pts == DEFAULT_RULES["def_team_win"]


def test_defender_win_without_60min():
    bd = compute_points(_stats(team_won=True, minutes_played=45), Position.DEF)
    assert bd.team_win_pts == 0.0


def test_defender_clean_sheet_with_60min():
    bd = compute_points(_stats(clean_sheet=True, minutes_played=90), Position.DEF)
    assert bd.clean_sheet_pts == DEFAULT_RULES["defender_clean_sheet"]


def test_defender_clean_sheet_without_60min():
    bd = compute_points(_stats(clean_sheet=True, minutes_played=30), Position.DEF)
    assert bd.clean_sheet_pts == 0.0


def test_defender_win_and_clean_sheet():
    bd = compute_points(_stats(team_won=True, clean_sheet=True, minutes_played=90), Position.DEF)
    assert bd.team_win_pts == DEFAULT_RULES["def_team_win"]
    assert bd.clean_sheet_pts == DEFAULT_RULES["defender_clean_sheet"]
    assert bd.total == DEFAULT_RULES["def_team_win"] + DEFAULT_RULES["defender_clean_sheet"]


# ----------------------------------------------------------------
# Brankář — čisté konto při 60+ min, bez bonusu za výhru
# ----------------------------------------------------------------

def test_goalkeeper_clean_sheet_with_60min():
    bd = compute_points(_stats(clean_sheet=True, minutes_played=90), Position.GK)
    assert bd.clean_sheet_pts == DEFAULT_RULES["goalkeeper_clean_sheet"]


def test_goalkeeper_clean_sheet_without_60min():
    bd = compute_points(_stats(clean_sheet=True, minutes_played=20), Position.GK)
    assert bd.clean_sheet_pts == 0.0


def test_goalkeeper_no_team_win_bonus():
    bd = compute_points(_stats(team_won=True, minutes_played=90), Position.GK)
    assert bd.team_win_pts == 0.0


# ----------------------------------------------------------------
# Misc
# ----------------------------------------------------------------

def test_total_property():
    bd = ScoreBreakdown(goals_pts=30, assists_pts=25, team_win_pts=15, clean_sheet_pts=15)
    assert bd.total == 85.0


def test_custom_rules_override():
    bd = compute_points(_stats(goals=1), Position.FWD, rules={"goal": 50.0})
    assert bd.goals_pts == 50.0


def test_custom_rules_partial_override():
    bd = compute_points(
        _stats(goals=1, assists=1, team_won=True, minutes_played=90),
        Position.MID,
        rules={"goal": 10.0},
    )
    assert bd.goals_pts == 10.0
    assert bd.assists_pts == DEFAULT_RULES["assist"]
    assert bd.team_win_pts == DEFAULT_RULES["mid_team_win"]


def test_multiple_goals():
    bd = compute_points(_stats(goals=3), Position.FWD)
    assert bd.goals_pts == 90.0
