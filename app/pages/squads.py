import streamlit as st
from app.state import get_db, require_active_game
from app.models.models import Participant, DraftSession
from app.services.draft_engine import get_participant_squad
from app.services.squad_validator import validate_squad, SQUAD_SIZE

st.title("Sestavy")

db = get_db()
game_id = require_active_game()
if game_id is None:
    st.stop()

participants = db.query(Participant).filter(
    Participant.game_id == game_id
).order_by(Participant.draft_order).all()

if not participants:
    st.warning("Zatím žádní účastníci.")
    st.stop()

sessions = db.query(DraftSession).filter(
    DraftSession.game_id == game_id
).order_by(DraftSession.id.desc()).all()

if not sessions:
    st.info("Žádná draft session nenalezena. Nejprve proveď draft.")
    st.stop()

if len(sessions) > 1:
    session_id = st.selectbox(
        "Draft",
        [s.id for s in sessions],
        format_func=lambda sid: f"Draft {sid}" + (
            " ✓" if next(s for s in sessions if s.id == sid).is_complete else ""
        ),
    )
else:
    session_id = sessions[0].id

st.divider()

POS_ORDER = ["GK", "DEF", "MID", "FWD"]
POS_LABELS = {"GK": "Brankáři", "DEF": "Obránci", "MID": "Záložníci", "FWD": "Útočníci"}

for p in participants:
    squad = get_participant_squad(db, session_id, p.id)
    validation = validate_squad(squad) if squad else None
    icon = "✅" if (validation and validation.valid) else ("⚠️" if squad else "⬜")

    with st.expander(f"{icon} **{p.name}** — {len(squad)} / {SQUAD_SIZE}", expanded=True):
        if not squad:
            st.caption("Zatím žádní hráči.")
            continue

        by_pos: dict[str, list] = {pos: [] for pos in POS_ORDER}
        for pl in squad:
            by_pos.get(pl.position, []).append(pl)

        col_a, col_b = st.columns(2)
        for i, pos in enumerate(POS_ORDER):
            col = col_a if i < 2 else col_b
            with col:
                st.caption(f"**{POS_LABELS[pos]}** ({len(by_pos[pos])})")
                for pl in sorted(by_pos[pos], key=lambda x: x.name):
                    st.write(pl.name)
                    st.caption(pl.country)

        if validation and not validation.valid:
            for err in validation.errors:
                st.error(err)
