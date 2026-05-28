from unittest.mock import MagicMock
from app.models.models import FootballPlayer
from app.services.squad_validator import (
    validate_squad,
    validate_lineup,
    SQUAD_SIZE,
    LINEUP_SIZE,
)


def _player(pos: str, name: str = "X") -> FootballPlayer:
    p = MagicMock(spec=FootballPlayer)
    p.position = pos
    p.name = name
    p.id = id(p)
    return p


def _make_squad() -> list:
    """18 players: 1 GK, 5 DEF, 5 MID, 3 FWD + 4 extra MID subs."""
    players = (
        [_player("GK", "GK1")]
        + [_player("DEF", f"D{i}") for i in range(5)]
        + [_player("MID", f"M{i}") for i in range(5)]
        + [_player("FWD", f"F{i}") for i in range(3)]
        + [_player("MID", f"SubM{i}") for i in range(4)]
    )
    assert len(players) == SQUAD_SIZE
    return players


def _make_lineup(squad: list) -> list:
    """11-player lineup: 1 GK + 4 DEF + 4 MID + 2 FWD."""
    gks = [p for p in squad if p.position == "GK"]
    defs = [p for p in squad if p.position == "DEF"]
    mids = [p for p in squad if p.position == "MID"]
    fwds = [p for p in squad if p.position == "FWD"]
    return gks[:1] + defs[:4] + mids[:4] + fwds[:2]


# ----------------------------------------------------------------
# validate_squad
# ----------------------------------------------------------------

def test_valid_squad():
    result = validate_squad(_make_squad())
    assert result.valid, result.errors


def test_squad_wrong_size_too_few():
    squad = _make_squad()[:-1]
    result = validate_squad(squad)
    assert not result.valid
    assert any(str(SQUAD_SIZE) in e for e in result.errors)


def test_squad_wrong_size_too_many():
    squad = _make_squad() + [_player("MID", "Extra")]
    result = validate_squad(squad)
    assert not result.valid


def test_squad_missing_gk():
    squad = [_player("DEF", f"D{i}") for i in range(6)]
    squad += [_player("MID", f"M{i}") for i in range(6)]
    squad += [_player("FWD", f"F{i}") for i in range(6)]
    assert len(squad) == SQUAD_SIZE
    result = validate_squad(squad)
    assert not result.valid
    assert any("GK" in e for e in result.errors)


def test_squad_not_enough_defenders():
    squad = (
        [_player("GK", "GK1")]
        + [_player("DEF", f"D{i}") for i in range(2)]  # only 2 DEF
        + [_player("MID", f"M{i}") for i in range(8)]
        + [_player("FWD", f"F{i}") for i in range(7)]
    )
    assert len(squad) == SQUAD_SIZE
    result = validate_squad(squad)
    assert not result.valid
    assert any("DEF" in e for e in result.errors)


def test_squad_not_enough_midfielders():
    squad = (
        [_player("GK", "GK1")]
        + [_player("DEF", f"D{i}") for i in range(8)]
        + [_player("MID", f"M{i}") for i in range(2)]  # only 2 MID
        + [_player("FWD", f"F{i}") for i in range(7)]
    )
    assert len(squad) == SQUAD_SIZE
    result = validate_squad(squad)
    assert not result.valid
    assert any("MID" in e for e in result.errors)


def test_squad_not_enough_forwards():
    squad = (
        [_player("GK", "GK1")]
        + [_player("DEF", f"D{i}") for i in range(8)]
        + [_player("MID", f"M{i}") for i in range(9)]
        # 0 FWD
    )
    assert len(squad) == SQUAD_SIZE
    result = validate_squad(squad)
    assert not result.valid
    assert any("FWD" in e for e in result.errors)


# ----------------------------------------------------------------
# validate_lineup
# ----------------------------------------------------------------

def test_valid_lineup():
    squad = _make_squad()
    lineup = _make_lineup(squad)
    assert len(lineup) == LINEUP_SIZE
    result = validate_lineup(lineup, squad)
    assert result.valid, result.errors


def test_lineup_wrong_size_too_few():
    squad = _make_squad()
    lineup = _make_lineup(squad)[:-1]
    result = validate_lineup(lineup, squad)
    assert not result.valid
    assert any(str(LINEUP_SIZE) in e for e in result.errors)


def test_lineup_wrong_size_too_many():
    squad = _make_squad()
    lineup = _make_lineup(squad) + [squad[0]]
    result = validate_lineup(lineup, squad)
    assert not result.valid


def test_lineup_player_not_in_squad():
    squad = _make_squad()
    lineup = _make_lineup(squad)
    outsider = _player("MID", "Outsider")
    lineup[5] = outsider
    result = validate_lineup(lineup, squad)
    assert not result.valid
    assert any("není v kádru" in e for e in result.errors)


def test_lineup_no_goalkeeper():
    squad = _make_squad()
    lineup = _make_lineup(squad)
    gk = next(p for p in lineup if p.position == "GK")
    extra_def = next(p for p in squad if p.position == "DEF" and p not in lineup)
    lineup = [p for p in lineup if p is not gk] + [extra_def]
    result = validate_lineup(lineup, squad)
    assert not result.valid
    assert any("GK" in e for e in result.errors)


def test_lineup_too_many_defenders():
    squad = (
        [_player("GK", "GK1")]
        + [_player("DEF", f"D{i}") for i in range(10)]
        + [_player("MID", f"M{i}") for i in range(5)]
        + [_player("FWD", f"F{i}") for i in range(2)]
    )
    assert len(squad) == SQUAD_SIZE
    # Try lineup with 6 DEF (exceeds max 5)
    gks = [p for p in squad if p.position == "GK"]
    defs = [p for p in squad if p.position == "DEF"]
    mids = [p for p in squad if p.position == "MID"]
    fwds = [p for p in squad if p.position == "FWD"]
    lineup = gks[:1] + defs[:6] + mids[:3] + fwds[:1]
    assert len(lineup) == LINEUP_SIZE
    result = validate_lineup(lineup, squad)
    assert not result.valid
    assert any("DEF" in e for e in result.errors)


def test_lineup_too_many_forwards():
    squad = (
        [_player("GK", "GK1")]
        + [_player("DEF", f"D{i}") for i in range(3)]
        + [_player("MID", f"M{i}") for i in range(3)]
        + [_player("FWD", f"F{i}") for i in range(8)]
        + [_player("MID", f"SubM{i}") for i in range(3)]
    )
    assert len(squad) == SQUAD_SIZE
    gks = [p for p in squad if p.position == "GK"]
    defs = [p for p in squad if p.position == "DEF"]
    mids = [p for p in squad if p.position == "MID"]
    fwds = [p for p in squad if p.position == "FWD"]
    lineup = gks[:1] + defs[:3] + mids[:3] + fwds[:4]
    assert len(lineup) == LINEUP_SIZE
    result = validate_lineup(lineup, squad)
    assert not result.valid
    assert any("FWD" in e for e in result.errors)
