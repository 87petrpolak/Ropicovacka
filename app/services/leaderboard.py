from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.models import (
    Participant, DraftPick, PlayerMatchStats, LineupSlot,
    LineupNomination, FootballPlayer, Round, PointsRule
)
from app.services.scoring import compute_points, rules_from_db
from app.models.models import Position


def compute_leaderboard(db: Session, game_id: int) -> list[dict]:
    participants = db.query(Participant).filter(Participant.game_id == game_id).all()
    db_rules = db.query(PointsRule).filter(PointsRule.game_id == game_id).all()
    scoring_rules = rules_from_db(db_rules)

    rows = []
    for p in participants:
        total = _participant_total(db, p, game_id, scoring_rules)
        rows.append({"participant": p.name, "participant_id": p.id, "total_points": total})

    rows.sort(key=lambda r: r["total_points"], reverse=True)
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return rows


def _participant_total(db: Session, participant: Participant, game_id: int, scoring_rules: dict) -> float:
    total = 0.0

    rounds = db.query(Round).filter(Round.game_id == game_id).all()
    for round_ in rounds:
        nomination = db.query(LineupNomination).filter(
            LineupNomination.participant_id == participant.id,
            LineupNomination.round_id == round_.id,
        ).first()
        if nomination is None:
            continue

        slots = db.query(LineupSlot).filter(LineupSlot.nomination_id == nomination.id).all()
        nominated_player_ids = {s.player_id for s in slots}

        for pid in nominated_player_ids:
            player = db.get(FootballPlayer, pid)
            if player is None:
                continue
            stats_list = (
                db.query(PlayerMatchStats)
                .join(PlayerMatchStats.match)
                .filter(
                    PlayerMatchStats.player_id == pid,
                )
                .all()
            )
            for stats in stats_list:
                if stats.match.round_id != round_.id:
                    continue
                bd = compute_points(stats, Position(player.position), scoring_rules)
                total += bd.total

    return total


def compute_round_leaderboard(db: Session, game_id: int, round_id: int) -> list[dict]:
    participants = db.query(Participant).filter(Participant.game_id == game_id).all()
    db_rules = db.query(PointsRule).filter(PointsRule.game_id == game_id).all()
    scoring_rules = rules_from_db(db_rules)

    rows = []
    for p in participants:
        nomination = db.query(LineupNomination).filter(
            LineupNomination.participant_id == p.id,
            LineupNomination.round_id == round_id,
        ).first()
        pts = 0.0
        if nomination:
            slots = db.query(LineupSlot).filter(LineupSlot.nomination_id == nomination.id).all()
            nominated_ids = {s.player_id for s in slots}
            for pid in nominated_ids:
                player = db.get(FootballPlayer, pid)
                if player is None:
                    continue
                stats_list = (
                    db.query(PlayerMatchStats)
                    .join(PlayerMatchStats.match)
                    .filter(
                        PlayerMatchStats.player_id == pid,
                        PlayerMatchStats.match.has(round_id=round_id),
                    )
                    .all()
                )
                for stats in stats_list:
                    bd = compute_points(stats, Position(player.position), scoring_rules)
                    pts += bd.total
        rows.append({"participant": p.name, "participant_id": p.id, "round_points": pts})

    rows.sort(key=lambda r: r["round_points"], reverse=True)
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return rows
