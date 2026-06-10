"""
Tipy na turnaj — vítěz MS a nejlepší střelec.
Každý správný tip = +50 Kč od každého ostatního účastníka.
"""
import streamlit as st
from datetime import datetime
from app.state import get_db, require_active_game
from app.models.models import Participant, FootballPlayer, TournamentPrediction, Game, DraftSession, DraftPick

st.title("🎯 Tipy na turnaj")
st.caption("Každý správný tip = **+50 Kč** od každého ostatního. Vítěz MS a nejlepší střelec se počítají zvlášť — při 3 hráčích max. **+200 Kč** za obojí (2× 100 Kč).")

db = get_db()
game_id = require_active_game()
if game_id is None:
    st.stop()

game = db.get(Game, game_id)
participants = db.query(Participant).filter(Participant.game_id == game_id).order_by(Participant.draft_order).all()

if not participants:
    st.warning("Žádní účastníci.")
    st.stop()

# Všichni draftovaní hráči (pro výběr nejlepšího střelce)
session = db.query(DraftSession).filter(DraftSession.game_id == game_id).order_by(DraftSession.id.desc()).first()
drafted_ids = set()
if session:
    drafted_ids = {pick.player_id for pick in db.query(DraftPick).filter(DraftPick.session_id == session.id).all()}
all_players = db.query(FootballPlayer).order_by(FootballPlayer.name).all()
drafted_players = [p for p in all_players if p.id in drafted_ids]

# Všechny týmy MS (z hráčů v DB)
countries = sorted({p.club or p.country for p in all_players if p.club or p.country})

locked = getattr(game, "predictions_locked", False) if game else False
if locked:
    st.warning("🔒 Tipy jsou uzamčeny — turnaj již začal.")

st.divider()

# ----------------------------------------------------------------
# Zobrazení a editace tipů
# ----------------------------------------------------------------
for participant in participants:
    pred = db.query(TournamentPrediction).filter(
        TournamentPrediction.game_id == game_id,
        TournamentPrediction.participant_id == participant.id,
    ).first()

    with st.expander(f"**{participant.name}**" + (" ✅" if pred and pred.winner_country and pred.top_scorer_player_id else " ⏳"), expanded=not locked):
        col1, col2 = st.columns(2)

        # Vítěz
        with col1:
            st.markdown("**🏆 Vítěz MS**")
            winner_options = ["— nevybráno —"] + countries
            current_winner_idx = 0
            if pred and pred.winner_country and pred.winner_country in countries:
                current_winner_idx = countries.index(pred.winner_country) + 1
            sel_winner = st.selectbox(
                "Vítěz",
                range(len(winner_options)),
                index=current_winner_idx,
                format_func=lambda i: winner_options[i],
                key=f"winner_{participant.id}",
                disabled=locked,
                label_visibility="collapsed",
            )
            winner_val = winner_options[sel_winner] if sel_winner > 0 else None

        # Nejlepší střelec
        with col2:
            st.markdown("**⚽ Nejlepší střelec**")
            scorer_options = [None] + [p.id for p in drafted_players]
            scorer_labels = ["— nevybráno —"] + [f"{p.name} ({p.country})" for p in drafted_players]
            current_scorer_idx = 0
            if pred and pred.top_scorer_player_id:
                try:
                    current_scorer_idx = scorer_options.index(pred.top_scorer_player_id)
                except ValueError:
                    pass
            sel_scorer = st.selectbox(
                "Střelec",
                range(len(scorer_options)),
                index=current_scorer_idx,
                format_func=lambda i: scorer_labels[i],
                key=f"scorer_{participant.id}",
                disabled=locked,
                label_visibility="collapsed",
            )
            scorer_val = scorer_options[sel_scorer]

        if not locked:
            if st.button("💾 Uložit tip", key=f"save_pred_{participant.id}", type="primary"):
                if pred is None:
                    pred = TournamentPrediction(game_id=game_id, participant_id=participant.id)
                    db.add(pred)
                pred.winner_country = winner_val
                pred.top_scorer_player_id = scorer_val
                pred.submitted_at = datetime.utcnow()
                db.commit()
                st.success("✅ Tip uložen!")
                st.rerun()

# ----------------------------------------------------------------
# Přehled všech tipů (viditelný všem)
# ----------------------------------------------------------------
st.divider()
st.subheader("📋 Přehled tipů")

preds = db.query(TournamentPrediction).filter(TournamentPrediction.game_id == game_id).all()
pred_map = {p.participant_id: p for p in preds}

cols = st.columns(len(participants))
for i, participant in enumerate(participants):
    pred = pred_map.get(participant.id)
    with cols[i]:
        st.markdown(f"**{participant.name}**")
        if pred and pred.winner_country:
            st.write(f"🏆 {pred.winner_country}")
        else:
            st.write("🏆 —")
        if pred and pred.top_scorer_player_id:
            scorer = db.get(FootballPlayer, pred.top_scorer_player_id)
            st.write(f"⚽ {scorer.name}" if scorer else "⚽ —")
        else:
            st.write("⚽ —")
