from dataclasses import dataclass, field
from app.models.models import FootballPlayer, Position


SQUAD_SIZE = 18
LINEUP_SIZE = 11
SUB_SIZE = 7

# Squad-level rules: just enough players of each position to form a valid lineup.
# Subs can be any position, so no upper cap per position.
SQUAD_RULES = {
    Position.GK:  {"min": 1, "max": 18},
    Position.DEF: {"min": 3, "max": 18},
    Position.MID: {"min": 3, "max": 18},
    Position.FWD: {"min": 1, "max": 18},
}

# Lineup rules: constraints on the nominated 11-player starting XI.
LINEUP_RULES = {
    Position.GK:  {"min": 1, "max": 1},
    Position.DEF: {"min": 3, "max": 5},
    Position.MID: {"min": 3, "max": 5},
    Position.FWD: {"min": 1, "max": 3},
}

# Alias kept for any callers that imported POSITION_RULES
POSITION_RULES = LINEUP_RULES


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)

    def fail(self, msg: str):
        self.valid = False
        self.errors.append(msg)


def validate_squad(players: list[FootballPlayer]) -> ValidationResult:
    result = ValidationResult()

    if len(players) != SQUAD_SIZE:
        result.fail(f"Kádr musí mít přesně {SQUAD_SIZE} hráčů, aktuálně {len(players)}")

    counts = _count_positions(players)
    for pos, rules in SQUAD_RULES.items():
        n = counts.get(pos, 0)
        if n < rules["min"]:
            result.fail(f"Málo hráčů na pozici {pos.value}: minimum {rules['min']}, aktuálně {n}")
        if n > rules["max"]:
            result.fail(f"Příliš mnoho hráčů na pozici {pos.value}: maximum {rules['max']}, aktuálně {n}")

    return result


def validate_lineup(
    nominated: list[FootballPlayer],
    squad: list[FootballPlayer],
) -> ValidationResult:
    result = ValidationResult()

    if len(nominated) != LINEUP_SIZE:
        result.fail(f"Nominace musí mít přesně {LINEUP_SIZE} hráčů, aktuálně {len(nominated)}")

    squad_ids = {p.id for p in squad}
    for p in nominated:
        if p.id not in squad_ids:
            result.fail(f"{p.name} není v kádru tohoto účastníka")

    counts = _count_positions(nominated)
    for pos, rules in LINEUP_RULES.items():
        n = counts.get(pos, 0)
        if n < rules["min"]:
            result.fail(f"Málo hráčů na pozici {pos.value} v nominaci: minimum {rules['min']}, aktuálně {n}")
        if n > rules["max"]:
            result.fail(f"Příliš mnoho hráčů na pozici {pos.value} v nominaci: maximum {rules['max']}, aktuálně {n}")

    return result


def _count_positions(players: list[FootballPlayer]) -> dict:
    counts: dict = {}
    for p in players:
        pos = Position(p.position)
        counts[pos] = counts.get(pos, 0) + 1
    return counts
