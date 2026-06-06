from datetime import datetime
from sqlalchemy.orm import Session
from app.models.models import LineupNomination, LineupSlot, LineupChangeLog, Round, Participant, FootballPlayer
from app.services.squad_validator import validate_lineup
from app.services.draft_engine import get_participant_squad


class LineupError(Exception):
    pass


def get_or_create_nomination(
    db: Session,
    participant: Participant,
    round_: Round,
) -> LineupNomination:
    nom = db.query(LineupNomination).filter(
        LineupNomination.participant_id == participant.id,
        LineupNomination.round_id == round_.id,
    ).first()
    if nom is None:
        nom = LineupNomination(participant_id=participant.id, round_id=round_.id)
        db.add(nom)
        db.commit()
        db.refresh(nom)
    return nom


def submit_lineup(
    db: Session,
    nomination: LineupNomination,
    player_ids: list[int],
    session_id: int,
    admin_override: bool = False,
) -> LineupNomination:
    if nomination.is_locked and not admin_override:
        raise LineupError("Nominace je zamknutá. Požádej administrátora o odemknutí.")

    round_ = db.get(Round, nomination.round_id)
    if round_ and round_.lineup_deadline and not admin_override:
        if datetime.utcnow() > round_.lineup_deadline:
            raise LineupError(
                f"Deadline uplynul ({round_.lineup_deadline.strftime('%Y-%m-%d %H:%M')} UTC). "
                "Kontaktuj administrátora pro odemknutí."
            )

    participant = db.get(Participant, nomination.participant_id)
    squad = get_participant_squad(db, session_id, participant.id)
    nominated = [p for p in squad if p.id in set(player_ids)]

    result = validate_lineup(nominated, squad)
    if not result.valid:
        raise LineupError("Neplatná nominace:\n" + "\n".join(result.errors))

    # Zjisti předchozí sestavu pro log
    old_ids = {s.player_id for s in db.query(LineupSlot).filter(LineupSlot.nomination_id == nomination.id).all()}
    new_ids = set(player_ids)

    # Replace slots
    db.query(LineupSlot).filter(LineupSlot.nomination_id == nomination.id).delete()
    for pid in player_ids:
        db.add(LineupSlot(nomination_id=nomination.id, player_id=pid))

    # Zapiš log změn
    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids
    if added_ids or removed_ids or not old_ids:
        def _names(ids):
            players = db.query(FootballPlayer).filter(FootballPlayer.id.in_(ids)).all()
            return ", ".join(p.name for p in players) if players else None
        db.add(LineupChangeLog(
            nomination_id=nomination.id,
            added_players=_names(added_ids) if added_ids else None,
            removed_players=_names(removed_ids) if removed_ids else None,
        ))

    nomination.submitted_at = datetime.utcnow()
    nomination.is_locked = False
    db.commit()
    db.refresh(nomination)
    return nomination


def lock_lineup(db: Session, nomination: LineupNomination) -> None:
    nomination.is_locked = True
    db.commit()


def admin_unlock_lineup(db: Session, nomination: LineupNomination) -> None:
    nomination.is_locked = False
    nomination.locked_by_admin = True
    db.commit()


def get_lineup_players(db: Session, nomination: LineupNomination) -> list[FootballPlayer]:
    slots = db.query(LineupSlot).filter(LineupSlot.nomination_id == nomination.id).all()
    player_ids = [s.player_id for s in slots]
    if not player_ids:
        return []
    return db.query(FootballPlayer).filter(FootballPlayer.id.in_(player_ids)).all()
