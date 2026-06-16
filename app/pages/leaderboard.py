import pandas as pd
import streamlit as st
from app.state import get_db, require_active_game
from app.models.models import Round, Participant, DraftSession
from app.services.leaderboard import compute_leaderboard, compute_round_leaderboard
from app.services.draft_engine import get_participant_squad

st.title("Pořadí")

db = get_db()
game_id = require_active_game()
if game_id is None:
    st.stop()

# ----------------------------------------------------------------
# Celkové pořadí
# ----------------------------------------------------------------
st.subheader("Celkové pořadí")

rows = compute_leaderboard(db, game_id)
if rows:
    df = pd.DataFrame([
        {
            "Místo": r["rank"],
            "Účastník": r["participant"],
            "Celkem bodů": r["total_points"],
        }
        for r in rows
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("Zatím žádné body. Importuj statistiky zápasů a nominuj sestavy.")

st.divider()

# ----------------------------------------------------------------
# Pořadí po kolech
# ----------------------------------------------------------------
rounds = db.query(Round).filter(
    Round.game_id == game_id
).order_by(Round.round_number).all()

if rounds:
    st.subheader("Pořadí v kole")
    round_opts = {r.id: f"Kolo {r.round_number}: {r.name}" for r in rounds}
    sel_round_id = st.selectbox(
        "Vyber kolo", list(round_opts.keys()),
        index=len(rounds) - 1,
        format_func=lambda rid: round_opts[rid],
    )
    round_rows = compute_round_leaderboard(db, game_id, sel_round_id)
    if round_rows:
        df_round = pd.DataFrame([
            {
                "Místo": r["rank"],
                "Účastník": r["participant"],
                "Body v kole": r["round_points"],
            }
            for r in round_rows
        ])
        st.dataframe(df_round, use_container_width=True, hide_index=True)
    else:
        st.info("Žádné body pro toto kolo.")

st.divider()

# ----------------------------------------------------------------
# Detail týmu
# ----------------------------------------------------------------
st.subheader("Detail kádru")

participants = db.query(Participant).filter(Participant.game_id == game_id).all()
sessions = db.query(DraftSession).filter(
    DraftSession.game_id == game_id
).order_by(DraftSession.id.desc()).all()

if not participants:
    st.info("Zatím žádní účastníci.")
elif not sessions:
    st.info("Žádná draft session.")
else:
    session_id = sessions[0].id
    sel_pname = st.selectbox("Zobrazit kádr", [p.name for p in participants])
    participant = next(p for p in participants if p.name == sel_pname)
    squad = get_participant_squad(db, session_id, participant.id)

    if not squad:
        st.info("Žádný kádr zatím.")
    else:
        POS_ORDER = ["GK", "DEF", "MID", "FWD"]
        POS_LABELS = {
            "GK": "Brankáři", "DEF": "Obránci",
            "MID": "Záložníci", "FWD": "Útočníci",
        }
        by_pos: dict[str, list] = {}
        for pl in squad:
            by_pos.setdefault(pl.position, []).append(pl)

        col_a, col_b = st.columns(2)
        for i, pos in enumerate(POS_ORDER):
            col = col_a if i < 2 else col_b
            with col:
                st.caption(f"**{POS_LABELS[pos]}**")
                for pl in sorted(by_pos.get(pos, []), key=lambda x: x.name):
                    st.write(pl.name)
                    st.caption(pl.country)
