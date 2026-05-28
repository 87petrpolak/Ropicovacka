import streamlit as st
import pandas as pd
from datetime import datetime
from app.state import get_db, require_active_game, get_active_draft_session_id, set_active_draft_session_id
from app.models.models import DraftSession, Participant, FootballPlayer, Position, DraftPick
from app.services import draft_engine
from app.services.squad_validator import SQUAD_SIZE, validate_squad

st.title("Draft")

db = get_db()
game_id = require_active_game()
if game_id is None:
    st.stop()

participants = db.query(Participant).filter(
    Participant.game_id == game_id
).order_by(Participant.draft_order).all()
if not participants:
    st.warning("Nejprve přidej účastníky.")
    st.stop()

all_players = db.query(FootballPlayer).order_by(
    FootballPlayer.country, FootballPlayer.name
).all()
if not all_players:
    st.warning("Nejprve importuj hráče (stránka Hráči).")
    st.stop()

# ------------------------------------------------------------------
# Správa session
# ------------------------------------------------------------------
sessions = db.query(DraftSession).filter(
    DraftSession.game_id == game_id
).order_by(DraftSession.id.desc()).all()

with st.sidebar:
    st.subheader("Draft")
    if sessions:
        sel_session_id = st.selectbox(
            "Vyber draft",
            [s.id for s in sessions],
            format_func=lambda sid: f"Draft {sid}" + (
                " ✓" if next(s for s in sessions if s.id == sid).is_complete else ""
            ),
        )
        set_active_draft_session_id(sel_session_id)
    else:
        sel_session_id = None

    if st.button("➕ Nový draft"):
        ns = DraftSession(game_id=game_id, started_at=datetime.utcnow())
        db.add(ns)
        db.commit()
        db.refresh(ns)
        set_active_draft_session_id(ns.id)
        st.rerun()

session_id = get_active_draft_session_id() or (sessions[0].id if sessions else None)
if session_id is None:
    st.info("Vytvoř draft session a začni výběr.")
    st.stop()

draft_session = db.get(DraftSession, session_id)
if draft_session is None:
    st.error("Draft nenalezen.")
    st.stop()

# ------------------------------------------------------------------
# Průběh draftu
# ------------------------------------------------------------------
order = draft_engine.build_snake_order(participants, SQUAD_SIZE)
total_picks = len(order)
done_picks = draft_session.current_pick_index
progress = done_picks / total_picks if total_picks else 0

st.progress(progress, text=f"Pick {done_picks} / {total_picks}")

if draft_session.is_complete:
    st.success("Draft je dokončen!")
else:
    current_picker = draft_engine.current_picker(draft_session, participants)
    if current_picker:
        st.info(f"🎯 **Vybírá: {current_picker.name}** — Kolo {draft_session.current_round}")

# ------------------------------------------------------------------
# Draftnutí hráči
# ------------------------------------------------------------------
drafted_ids = draft_engine.get_drafted_player_ids(db, session_id)

# ------------------------------------------------------------------
# Panel dostupných hráčů
# ------------------------------------------------------------------
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Dostupní hráči")
    c1, c2, c3 = st.columns(3)
    with c1:
        countries = sorted({p.country for p in all_players})
        f_country = st.multiselect("Reprezentace", countries, key="draft_country")
    with c2:
        f_pos = st.multiselect("Pozice", [p.value for p in Position], key="draft_pos")
    with c3:
        f_name = st.text_input("Hledat jméno", key="draft_name")

    available = [p for p in all_players if p.id not in drafted_ids]
    if f_country:
        available = [p for p in available if p.country in f_country]
    if f_pos:
        available = [p for p in available if p.position in f_pos]
    if f_name:
        available = [p for p in available if f_name.lower() in p.name.lower()]

    st.caption(f"{len(available)} dostupných hráčů")

    if available and not draft_session.is_complete:
        pick_name = st.selectbox(
            "Vyber hráče k draftování",
            [p.name for p in available],
            key="pick_player",
        )
        pick_player = next(p for p in available if p.name == pick_name)

        if st.button("✅ Draftovat hráče", type="primary"):
            try:
                current_picker = draft_engine.current_picker(draft_session, participants)
                if current_picker is None:
                    st.error("Žádný aktuální výběrčí.")
                else:
                    draft_engine.make_pick(db, draft_session, current_picker, pick_player)
                    st.success(f"{current_picker.name} draftoval {pick_player.name}!")
                    st.rerun()
            except draft_engine.DraftError as e:
                st.error(str(e))

# ------------------------------------------------------------------
# Přehled sestav
# ------------------------------------------------------------------
with col_right:
    st.subheader("Sestavy")
    for p in participants:
        squad = draft_engine.get_participant_squad(db, session_id, p.id)
        with st.expander(f"{p.name} ({len(squad)}/{SQUAD_SIZE})", expanded=False):
            if squad:
                for pl in sorted(squad, key=lambda x: x.position):
                    st.write(f"**{pl.position}** {pl.name} ({pl.country})")
            else:
                st.write("Zatím žádné picks.")

# ------------------------------------------------------------------
# Admin: vrátit poslední pick
# ------------------------------------------------------------------
st.divider()
with st.expander("⚙️ Administrace — Vrátit poslední pick"):
    if st.button("Vrátit poslední pick", type="secondary"):
        undone = draft_engine.undo_last_pick(db, draft_session)
        if undone:
            player = db.get(FootballPlayer, undone.player_id)
            participant = db.get(Participant, undone.participant_id)
            st.success(f"Vráceno: {participant.name} — {player.name}")
            st.rerun()
        else:
            st.info("Není co vracet.")

# ------------------------------------------------------------------
# Historie picků
# ------------------------------------------------------------------
with st.expander("📋 Celá historie picků"):
    picks = db.query(DraftPick).filter(
        DraftPick.session_id == session_id
    ).order_by(DraftPick.pick_number).all()
    if picks:
        rows = []
        for pk in picks:
            player = db.get(FootballPlayer, pk.player_id)
            part = db.get(Participant, pk.participant_id)
            rows.append({
                "Pick č.": pk.pick_number,
                "Kolo": pk.round_number,
                "Účastník": part.name if part else "?",
                "Hráč": player.name if player else "?",
                "Pozice": player.position if player else "?",
                "Reprezentace": player.country if player else "?",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Zatím žádné picks.")
