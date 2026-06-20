"""
Cashflow výpočet — zero-sum systém.

Pravidlo: Když hráč bonifikuje (gól, asistence, výhra, čisté konto),
vlastník dostane hodnotu_eventu × (počet_ostatních) Kč.
Každý ostatní účastník zaplatí hodnotu_eventu Kč.
Součet přes všechny účastníky je vždy 0.

Příklad (3 účastníci, gól = 30 Kč):
  Vlastník:  +60 Kč  (30 × 2)
  Ostatní:   -30 Kč každý
  Součet:    60 - 30 - 30 = 0 ✓
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import (
    DraftPick, DraftSession, FootballPlayer, Game, LineupNomination, LineupSlot, Match,
    Participant, PlayerMatchStats, PointsRule, Position, Round, TournamentPrediction
)
from app.services.scoring import compute_points, rules_from_db

EVENT_LABELS = {
    "goals": "⚽ Gól",
    "assists": "🎯 Asistence",
    "team_win": "🏆 Výhra",
    "clean_sheet": "🧤 Čisté konto",
}


def get_player_owner_map(db: Session, game_id: int) -> dict[int, Participant]:
    """Vrátí mapu player_id → Participant z nejnovější draft session."""
    session = (
        db.query(DraftSession)
        .filter(DraftSession.game_id == game_id)
        .order_by(DraftSession.id.desc())
        .first()
    )
    if not session:
        return {}

    participants = {
        p.id: p
        for p in db.query(Participant).filter(Participant.game_id == game_id).all()
    }
    picks = db.query(DraftPick).filter(DraftPick.session_id == session.id).all()
    return {pick.player_id: participants[pick.participant_id] for pick in picks if pick.participant_id in participants}


def compute_events(db: Session, game_id: int) -> list[dict]:
    """
    Vrátí bodované eventy pro tuto hru.

    Logika:
    - Kolo zápasu se určuje z pohledu hráčova týmu: Nth zápas tohoto týmu = Kolo N.
    - Pro kola KDE existují nominace: počítají se pouze nominovaní hráči.
    - Pro kola BEZ nominací: žádné body (kolo přeskočíme).

    Každý event: {player, owner, match, event_type, event_value}
    """
    player_owner = get_player_owner_map(db, game_id)
    if not player_owner:
        return []

    scoring_rules = rules_from_db(
        db.query(PointsRule).filter(PointsRule.game_id == game_id).all()
    )

    participants = db.query(Participant).filter(Participant.game_id == game_id).all()

    # Pro každé kolo zjisti, kteří hráči jsou nominováni (per účastník)
    # nominated_ids[round_id][participant_id] = set of player_ids
    rounds = db.query(Round).filter(Round.game_id == game_id).all()
    nominated: dict[int, dict[int, set[int]]] = {}
    # captain_ids[round_id][participant_id] = player_id | None
    captain_ids: dict[int, dict[int, int | None]] = {}
    # substitute_ids[round_id][participant_id] = player_id | None
    substitute_ids: dict[int, dict[int, int | None]] = {}
    # played_ids[round_id] = set of player_ids kteří nastoupili (minutes_played > 0)
    played_in_round: dict[int, set[int]] = {}

    for round_ in rounds:
        round_noms: dict[int, set[int]] = {}
        round_captains: dict[int, int | None] = {}
        round_subs: dict[int, int | None] = {}
        for p in participants:
            nom = db.query(LineupNomination).filter(
                LineupNomination.participant_id == p.id,
                LineupNomination.round_id == round_.id,
            ).first()
            if nom:
                slots = db.query(LineupSlot).filter(LineupSlot.nomination_id == nom.id).all()
                round_noms[p.id] = {s.player_id for s in slots}
                round_captains[p.id] = nom.captain_player_id
                round_subs[p.id] = nom.substitute_player_id
        if round_noms:
            nominated[round_.id] = round_noms
            captain_ids[round_.id] = round_captains
            substitute_ids[round_.id] = round_subs

    # Pro každý zápas a každý tým: kolikátý je to zápas tohoto týmu v chronologickém pořadí.
    # Tím zjistíme kolo z pohledu hráčova týmu (nezávisle na match.round_id, který mohl být
    # přiřazen podle domácího týmu a je tak nesprávný pro hostující tým z jiné skupiny).
    rounds_by_number = {r.round_number: r for r in rounds}

    all_game_matches = (
        db.query(Match)
        .filter(Match.game_id == game_id)
        .order_by(Match.played_at)
        .all()
    )
    # (match_id, team) -> round_number (1-based)
    match_team_round: dict[tuple[int, str], int] = {}
    # (team, round_number) -> Match — pro zjištění, zda zápas už proběhl
    team_round_match: dict[tuple[str, int], Match] = {}
    _team_count: dict[str, int] = {}
    for m in all_game_matches:
        for team in (m.home_team, m.away_team):
            if team:
                _team_count[team] = _team_count.get(team, 0) + 1
                rn = _team_count[team]
                match_team_round[(m.id, team)] = rn
                team_round_match[(team, rn)] = m

    # played_in_round[round_id][team] = set of player_ids kteří nastoupili (pro náhradníka)
    # Sestavíme dle match_team_round, ne match.round_id
    all_match_stats = (
        db.query(PlayerMatchStats, FootballPlayer, Match)
        .join(FootballPlayer, PlayerMatchStats.player_id == FootballPlayer.id)
        .join(Match, PlayerMatchStats.match_id == Match.id)
        .filter(Match.game_id == game_id, PlayerMatchStats.minutes_played > 0)
        .all()
    )
    for _s, _fp, _m in all_match_stats:
        _pt = _fp.club or _fp.country
        _rn = match_team_round.get((_m.id, _pt))
        if _rn is None:
            continue
        _r = rounds_by_number.get(_rn)
        if _r is None:
            continue
        played_in_round.setdefault(_r.id, set()).add(_fp.id)

    events = []
    all_stats = (
        db.query(PlayerMatchStats, FootballPlayer, Match)
        .join(FootballPlayer, PlayerMatchStats.player_id == FootballPlayer.id)
        .join(Match, PlayerMatchStats.match_id == Match.id)
        .filter(Match.game_id == game_id)
        .order_by(Match.played_at)
        .all()
    )

    for stats, player, match in all_stats:
        owner = player_owner.get(player.id)
        if owner is None:
            continue

        # Zjisti kolo z pohledu hráčova týmu (Nth zápas tohoto týmu = kolo N)
        player_team = player.club or player.country
        effective_round_number = match_team_round.get((match.id, player_team))
        if effective_round_number is None:
            continue
        effective_round = rounds_by_number.get(effective_round_number)
        if effective_round is None:
            continue  # Zápas patří do kola, které není definováno (playoff apod.)
        round_id = effective_round.id

        is_captain = False
        is_substitute = False

        if round_id not in nominated:
            continue  # Kolo bez nominací — body se nepočítají

        owner_nominations = nominated[round_id].get(owner.id, set())
        owner_captain = captain_ids.get(round_id, {}).get(owner.id)
        owner_sub = substitute_ids.get(round_id, {}).get(owner.id)
        played = played_in_round.get(round_id, set())

        if player.id == owner_sub:
            # Náhradník — aktivuje se jen pokud někdo z 11 nenastoupil V UŽ ODEHRANÉM zápase.
            # Hráči, jejichž zápas ještě neproběhl, se nepočítají jako "absent".
            non_playing = set()
            for _pid in owner_nominations:
                if _pid in played:
                    continue  # Nastoupil — OK
                _fp = db.get(FootballPlayer, _pid)
                if not _fp:
                    continue
                _team = _fp.club or _fp.country
                if not _team:
                    continue
                _nom_match = team_round_match.get((_team, effective_round_number))
                if _nom_match and _nom_match.is_finished:
                    non_playing.add(_pid)  # Zápas dohrán, hráč nenastoupil → absent
            if non_playing:
                sub_player = db.get(FootballPlayer, player.id)
                sub_is_gk = Position(sub_player.position) == Position.GK
                replaceable = any(
                    (Position(db.get(FootballPlayer, pid).position) == Position.GK) == sub_is_gk
                    for pid in non_playing
                    if db.get(FootballPlayer, pid)
                )
                if not replaceable:
                    continue
                is_substitute = True
            else:
                continue  # Všichni nastoupili, náhradník se nepočítá

        elif player.id in owner_nominations:
            # Základní hráč — musí být nominován
            is_captain = (player.id == owner_captain)
        else:
            continue  # Hráč není nominován ani náhradník

        bd = compute_points(stats, Position(player.position), scoring_rules)
        captain_multiplier = 2 if is_captain else 1

        def _add(event_type: str, value: float) -> None:
            events.append({
                "player":        player,
                "owner":         owner,
                "match":         match,
                "round":         effective_round,
                "event_type":    event_type,
                "event_value":   value * captain_multiplier,
                "is_captain":    is_captain,
                "is_substitute": is_substitute,
            })

        # Góly a asistence — jeden řádek na každý gól/asistenci
        if bd.goals_pts > 0 and stats.goals > 0:
            per_goal = bd.goals_pts / stats.goals
            for _ in range(stats.goals):
                _add("goals", per_goal)

        if bd.assists_pts > 0 and stats.assists > 0:
            per_assist = bd.assists_pts / stats.assists
            for _ in range(stats.assists):
                _add("assists", per_assist)

        # Výhra a čisté konto — vždy jeden řádek
        if bd.team_win_pts > 0:
            _add("team_win", bd.team_win_pts)
        if bd.clean_sheet_pts > 0:
            _add("clean_sheet", bd.clean_sheet_pts)

    return events


def compute_balances(events: list[dict], participants: list[Participant]) -> dict[int, float]:
    """
    Spočítá Kč zůstatek pro každého účastníka ze seznamu eventů.
    Výsledek je vždy zero-sum (součet = 0).
    """
    balances: dict[int, float] = {p.id: 0.0 for p in participants}
    others_count = len(participants) - 1
    if others_count <= 0:
        return balances

    for ev in events:
        val = ev["event_value"]
        owner_id = ev["owner"].id
        balances[owner_id] += val * others_count
        for p in participants:
            if p.id != owner_id:
                balances[p.id] -= val

    return balances


def compute_prediction_balances(db: Session, game_id: int, participants: list[Participant]) -> dict[int, float]:
    """
    Spočítá Kč zůstatek z tipů na turnaj.

    Pravidlo: každý správný tipér dostane 50 Kč od každého špatného tipéra.
    Příklad (3 účastníci, 2 tipli správně, 1 špatně):
      Správní: +50 Kč každý (od špatného)
      Špatný:  -100 Kč (50 × 2 správným)
      Součet: 50 + 50 - 100 = 0 ✓
    """
    BONUS = 50.0
    balances: dict[int, float] = {p.id: 0.0 for p in participants}

    game = db.get(Game, game_id)
    if not game or (not game.actual_winner and not game.actual_top_scorer_id):
        return balances  # Výsledky ještě nejsou zadány

    preds = db.query(TournamentPrediction).filter(TournamentPrediction.game_id == game_id).all()
    pred_map = {p.participant_id: p for p in preds}

    for category, is_correct_fn in [
        ("winner",     lambda pr: pr.winner_country == game.actual_winner),
        ("top_scorer", lambda pr: pr.top_scorer_player_id == game.actual_top_scorer_id),
    ]:
        # Rozhodni kdo tipnul správně a kdo ne
        correct = [p for p in participants if (pr := pred_map.get(p.id)) and is_correct_fn(pr)]
        wrong   = [p for p in participants if p not in correct]

        if not correct or not wrong:
            continue  # Buď všichni správně, nebo nikdo — nulový pohyb

        # Každý správný dostane BONUS od každého špatného
        for c in correct:
            balances[c.id] += BONUS * len(wrong)
        for w in wrong:
            balances[w.id] -= BONUS * len(correct)

    return balances


def cashflow_per_event(ev: dict, participants: list[Participant]) -> dict[int, float]:
    """Cashflow pro jediný event — vrátí {participant_id: delta}."""
    result: dict[int, float] = {}
    val = ev["event_value"]
    owner_id = ev["owner"].id
    others_count = len(participants) - 1
    for p in participants:
        if p.id == owner_id:
            result[p.id] = val * others_count
        else:
            result[p.id] = -val
    return result
