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
    DraftPick, DraftSession, FootballPlayer, LineupNomination, LineupSlot, Match,
    Participant, PlayerMatchStats, PointsRule, Position, Round
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
    - Pro kola KDE existují nominace: počítají se pouze nominovaní hráči.
    - Pro kola BEZ nominací: počítají se všichni hráči z draftu (fallback pro testování).

    Každý event: {player, owner, match, round, event_type, event_value}
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
    for round_ in rounds:
        round_noms: dict[int, set[int]] = {}
        for p in participants:
            nom = db.query(LineupNomination).filter(
                LineupNomination.participant_id == p.id,
                LineupNomination.round_id == round_.id,
            ).first()
            if nom:
                slots = db.query(LineupSlot).filter(LineupSlot.nomination_id == nom.id).all()
                round_noms[p.id] = {s.player_id for s in slots}
        if round_noms:
            nominated[round_.id] = round_noms

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

        round_id = match.round_id

        # Pokud pro toto kolo existují nominace, hráč musí být nominován
        if round_id and round_id in nominated:
            owner_nominations = nominated[round_id].get(owner.id, set())
            if player.id not in owner_nominations:
                continue

        bd = compute_points(stats, Position(player.position), scoring_rules)

        for event_type, value in [
            ("goals",       bd.goals_pts),
            ("assists",     bd.assists_pts),
            ("team_win",    bd.team_win_pts),
            ("clean_sheet", bd.clean_sheet_pts),
        ]:
            if value > 0:
                events.append({
                    "player":      player,
                    "owner":       owner,
                    "match":       match,
                    "event_type":  event_type,
                    "event_value": value,
                })

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
