from sqlalchemy.orm import Session
from app.models.models import Participant, Round, PointsRule
from app.services.cashflow import compute_events, compute_balances


def compute_leaderboard(db: Session, game_id: int) -> list[dict]:
    participants = db.query(Participant).filter(Participant.game_id == game_id).all()
    events = compute_events(db, game_id)
    balances = compute_balances(events, participants)

    rows = [
        {"participant": p.name, "participant_id": p.id, "total_points": balances[p.id]}
        for p in participants
    ]
    rows.sort(key=lambda r: r["total_points"], reverse=True)
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return rows


def compute_round_leaderboard(db: Session, game_id: int, round_id: int) -> list[dict]:
    participants = db.query(Participant).filter(Participant.game_id == game_id).all()
    all_events = compute_events(db, game_id)

    # Filtruj jen eventy z tohoto kola — použij ev["round"].id (efektivní kolo dle hráčova týmu)
    round_events = [ev for ev in all_events if ev.get("round") and ev["round"].id == round_id]
    balances = compute_balances(round_events, participants)

    rows = [
        {"participant": p.name, "participant_id": p.id, "round_points": balances[p.id]}
        for p in participants
    ]
    rows.sort(key=lambda r: r["round_points"], reverse=True)
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return rows
