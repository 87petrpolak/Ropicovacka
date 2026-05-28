"""Snake draft logic — stateless calculations over the DB session."""
from __future__ import annotations
from sqlalchemy.orm import Session
from app.models.models import DraftSession, DraftPick, Participant, FootballPlayer
from app.services.squad_validator import SQUAD_SIZE


class DraftError(Exception):
    pass


def build_snake_order(participants: list[Participant], total_rounds: int) -> list[int]:
    """Returns participant ids in snake order for `total_rounds` draft rounds."""
    ids = [p.id for p in sorted(participants, key=lambda p: p.draft_order or 0)]
    order = []
    for r in range(total_rounds):
        order.extend(ids if r % 2 == 0 else reversed(ids))
    return order


def current_picker(session: DraftSession, participants: list[Participant]) -> Participant | None:
    if session.is_complete:
        return None
    order = build_snake_order(participants, SQUAD_SIZE)
    idx = session.current_pick_index
    if idx >= len(order):
        return None
    pid = order[idx]
    return next((p for p in participants if p.id == pid), None)


def make_pick(
    db: Session,
    draft_session: DraftSession,
    participant: Participant,
    player: FootballPlayer,
) -> DraftPick:
    participants = db.query(Participant).filter(
        Participant.game_id == draft_session.game_id
    ).all()

    expected = current_picker(draft_session, participants)
    if expected is None:
        raise DraftError("Draft je již dokončen.")
    if expected.id != participant.id:
        raise DraftError(f"Na řadě je {expected.name}, ne {participant.name}.")

    already_picked = db.query(DraftPick).filter(
        DraftPick.session_id == draft_session.id,
        DraftPick.player_id == player.id,
    ).first()
    if already_picked:
        raise DraftError(f"{player.name} již byl draftnutý.")

    pick_number = draft_session.current_pick_index + 1
    round_number = draft_session.current_round

    pick = DraftPick(
        session_id=draft_session.id,
        participant_id=participant.id,
        player_id=player.id,
        pick_number=pick_number,
        round_number=round_number,
    )
    db.add(pick)

    draft_session.current_pick_index += 1

    order = build_snake_order(participants, SQUAD_SIZE)
    if draft_session.current_pick_index >= len(order):
        draft_session.is_complete = True
    else:
        current_round = (draft_session.current_pick_index // len(participants)) + 1
        draft_session.current_round = current_round

    db.commit()
    db.refresh(pick)
    return pick


def undo_last_pick(db: Session, draft_session: DraftSession) -> DraftPick | None:
    last = (
        db.query(DraftPick)
        .filter(DraftPick.session_id == draft_session.id)
        .order_by(DraftPick.pick_number.desc())
        .first()
    )
    if last is None:
        return None

    participants = db.query(Participant).filter(
        Participant.game_id == draft_session.game_id
    ).all()

    draft_session.current_pick_index -= 1
    current_round = (draft_session.current_pick_index // max(len(participants), 1)) + 1
    draft_session.current_round = current_round
    draft_session.is_complete = False

    db.delete(last)
    db.commit()
    return last


def get_participant_squad(
    db: Session,
    session_id: int,
    participant_id: int,
) -> list[FootballPlayer]:
    picks = (
        db.query(DraftPick)
        .filter(
            DraftPick.session_id == session_id,
            DraftPick.participant_id == participant_id,
        )
        .all()
    )
    player_ids = [p.player_id for p in picks]
    if not player_ids:
        return []
    return db.query(FootballPlayer).filter(FootballPlayer.id.in_(player_ids)).all()


def get_drafted_player_ids(db: Session, session_id: int) -> set[int]:
    picks = db.query(DraftPick).filter(DraftPick.session_id == session_id).all()
    return {p.player_id for p in picks}
