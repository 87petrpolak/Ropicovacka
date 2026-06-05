import streamlit as st
from datetime import datetime
from app.state import get_db, require_active_game
from app.models.models import Participant, Round, DraftSession
from app.services.draft_engine import get_participant_squad
from app.services.lineup_manager import (
    get_or_create_nomination,
    submit_lineup,
    get_lineup_players,
    LineupError,
)
from app.services.squad_validator import LINEUP_SIZE

st.title("Nominace sestavy")

db = get_db()
game_id = require_active_game()
if game_id is None:
    st.stop()

participants = db.query(Participant).filter(
    Participant.game_id == game_id
).order_by(Participant.draft_order).all()

rounds = db.query(Round).filter(
    Round.game_id == game_id
).order_by(Round.round_number).all()

sessions = db.query(DraftSession).filter(
    DraftSession.game_id == game_id
).order_by(DraftSession.id.desc()).all()

if not participants:
    st.warning("Zatím žádní účastníci.")
    st.stop()
if not rounds:
    st.info("Žádná kola nejsou definována. Přejdi na **Administrace** a vytvoř kola.")
    st.stop()
if not sessions:
    st.warning("Žádná draft session nenalezena. Nejprve proveď draft.")
    st.stop()

session_id = sessions[0].id

col1, col2 = st.columns(2)
with col1:
    sel_name = st.selectbox("Účastník", [p.name for p in participants])
    participant = next(p for p in participants if p.name == sel_name)
with col2:
    round_opts = {r.id: f"Kolo {r.round_number}: {r.name}" for r in rounds}
    sel_round_id = st.selectbox(
        "Kolo", list(round_opts.keys()), format_func=lambda rid: round_opts[rid]
    )
    selected_round = next(r for r in rounds if r.id == sel_round_id)

squad = get_participant_squad(db, session_id, participant.id)
if not squad:
    st.warning("Tento účastník zatím nemá žádné draftované hráče.")
    st.stop()

nomination = get_or_create_nomination(db, participant, selected_round)
current_lineup = get_lineup_players(db, nomination)
current_ids = {p.id for p in current_lineup}

st.divider()

# ----------------------------------------------------------------
# Stavový banner
# ----------------------------------------------------------------
now = datetime.utcnow()
deadline = selected_round.lineup_deadline
deadline_passed = bool(deadline and now > deadline)
locked = nomination.is_locked

if locked:
    st.error("🔒 Nominace je zamknutá. Kontaktuj administrátora pro odemknutí.")
elif deadline_passed:
    st.warning(
        f"⏰ Deadline uplynul ({deadline.strftime('%Y-%m-%d %H:%M')} UTC). "
        "Nominaci nelze změnit."
    )
elif deadline:
    remaining = deadline - now
    hours = int(remaining.total_seconds() // 3600)
    minutes = int((remaining.total_seconds() % 3600) // 60)
    st.info(
        f"📅 Deadline: {deadline.strftime('%Y-%m-%d %H:%M')} UTC — "
        f"zbývá {hours}h {minutes}m"
    )

editable = not locked and not deadline_passed

# ----------------------------------------------------------------
# Výběr hráčů
# ----------------------------------------------------------------
st.subheader(f"Vyber přesně {LINEUP_SIZE} hráčů z tvého {len(squad)}-hráčového kádru")

POS_ORDER = ["GK", "DEF", "MID", "FWD"]
POS_LABELS = {"GK": "Brankáři", "DEF": "Obránci", "MID": "Záložníci", "FWD": "Útočníci"}
POS_INFO = {"GK": "přesně 1", "DEF": "3–5", "MID": "3–5", "FWD": "1–3"}

by_pos: dict[str, list] = {}
for pl in squad:
    by_pos.setdefault(pl.position, []).append(pl)

selected_ids: set[int] = set()

for pos in POS_ORDER:
    pos_players = by_pos.get(pos, [])
    if not pos_players:
        continue
    st.caption(f"**{POS_LABELS[pos]}** — {POS_INFO.get(pos, '')}")
    for pl in sorted(pos_players, key=lambda x: x.name):
        checked = st.checkbox(
            f"{pl.name} ({pl.club or pl.country})",
            value=pl.id in current_ids,
            key=f"ln_{nomination.id}_{pl.id}",
            disabled=not editable,
        )
        if checked:
            selected_ids.add(pl.id)

count = len(selected_ids)
color = "green" if count == LINEUP_SIZE else "red"
st.markdown(f"**Vybráno: :{color}[{count} / {LINEUP_SIZE}]**")

if editable:
    if st.button("💾 Uložit nominaci", type="primary", use_container_width=True):
        try:
            submit_lineup(db, nomination, list(selected_ids), session_id)
            st.success("Nominace byla úspěšně uložena!")
            st.rerun()
        except LineupError as e:
            st.error(str(e))

# ----------------------------------------------------------------
# Aktuálně uložená nominace
# ----------------------------------------------------------------
if current_lineup:
    st.divider()
    st.subheader("Aktuálně uložená nominace")
    by_pos_saved: dict[str, list] = {}
    for pl in current_lineup:
        by_pos_saved.setdefault(pl.position, []).append(pl)
    for pos in POS_ORDER:
        for pl in sorted(by_pos_saved.get(pos, []), key=lambda x: x.name):
            st.write(f"**{POS_LABELS.get(pl.position, pl.position)}** {pl.name} ({pl.country})")
