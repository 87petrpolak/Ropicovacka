"""Hlavní dashboard — aktuální stav cashflow a přehled eventů."""
import pandas as pd
import streamlit as st
from app.state import get_db, require_active_game
from app.models.models import Participant, LineupNomination, LineupSlot, FootballPlayer, PlayerMatchStats, Match, Round, Game, TournamentPrediction
from app.services.cashflow import compute_events, compute_balances, cashflow_per_event, compute_prediction_balances, EVENT_LABELS



col_title, col_btn = st.columns([4, 1])
col_title.title("Dashboard")

with col_btn:
    st.markdown("<div style='margin-top:1.5rem'>", unsafe_allow_html=True)
    if st.button("🔄 Aktualizovat", use_container_width=True, help="Načte nejnovější výsledky z Livesport.cz"):
        from app.providers.livesport_provider import LivesportProvider
        from app.services.data_refresh import run_refresh
        game_id_tmp = require_active_game()
        if game_id_tmp:
            with st.spinner("Načítám…"):
                try:
                    provider = LivesportProvider()
                    result = run_refresh(get_db(), provider, game_id_tmp, import_players=False, import_matches=True)
                    from app.services.next_match_service import invalidate_match_cache
                    invalidate_match_cache()
                    if result.errors:
                        st.error("\n".join(result.errors[:5]))
                    total = result.matches_added + result.matches_updated
                    st.success(f"✅ {total} zápasů" if total else "✅ Nic nového")
                except Exception as e:
                    st.error(str(e))
    st.markdown("</div>", unsafe_allow_html=True)

db = get_db()
game_id = require_active_game()
if game_id is None:
    st.stop()

participants = (
    db.query(Participant)
    .filter(Participant.game_id == game_id)
    .order_by(Participant.draft_order)
    .all()
)
if not participants:
    st.info("Přidej účastníky a proveď draft.")
    st.stop()

events = compute_events(db, game_id)
balances = compute_balances(events, participants)
pred_balances = compute_prediction_balances(db, game_id, participants)

# Sloučení bilancí (zápasy + tipovačka)
total_balances = {p.id: balances[p.id] + pred_balances[p.id] for p in participants}

# Ověření zero-sum (debug)
total = sum(total_balances.values())

# ----------------------------------------------------------------
# SEKCE 1: Aktuální stav
# ----------------------------------------------------------------
st.subheader("Aktuální stav")

cols = st.columns(len(participants))
for i, p in enumerate(participants):
    bal = total_balances[p.id]
    icon = "🟢" if bal > 0 else ("🔴" if bal < 0 else "⚪")
    cols[i].metric(label=p.name, value=f"{bal:+.0f} Kč")
    cols[i].markdown(f"<div style='text-align:center;font-size:1.8rem'>{icon}</div>", unsafe_allow_html=True)

if abs(total) > 0.01:
    st.warning(f"⚠️ Součet není nula: {total:.2f} Kč — zkontroluj data.")

st.divider()

# ----------------------------------------------------------------
# SEKCE 2: Feed eventů
# ----------------------------------------------------------------
st.subheader("Co se dělo")

def _build_event_rows(evs: list[dict], participants: list) -> list[dict]:
    rows = []
    for ev in evs:
        match = ev["match"]
        match_label = (
            f"{match.home_team} {match.home_score}–{match.away_score} {match.away_team}"
            if match.home_team else match.external_id
        )
        cf = cashflow_per_event(ev, participants)
        row = {
            "Zápas": match_label,
            "Hráč": ev["player"].name,
            "Post": ev["player"].position,
            "Vlastník": ev["owner"].name,
            "Event": EVENT_LABELS.get(ev["event_type"], ev["event_type"]),
        }
        for p in participants:
            row[p.name] = f"{cf[p.id]:+.0f} Kč"
        rows.append(row)
    return rows


def _build_prediction_rows(db, game_id: int, participants: list, pred_balances: dict) -> list[dict]:
    """Řádky tipovačky do tabulky Co se dělo."""
    rows = []
    game = db.get(Game, game_id)
    if not game or (not game.actual_winner and not game.actual_top_scorer_id):
        return rows
    preds = db.query(TournamentPrediction).filter(TournamentPrediction.game_id == game_id).all()
    pred_map = {p.participant_id: p for p in preds}
    others = len(participants) - 1

    for label, actual_id, get_name, get_tip_id in [
        ("🎯 Nejlepší střelec",
         game.actual_top_scorer_id,
         lambda: db.get(FootballPlayer, game.actual_top_scorer_id).name if game.actual_top_scorer_id and db.get(FootballPlayer, game.actual_top_scorer_id) else None,
         lambda pr: pr.top_scorer_player_id if pr else None),
        ("🏆 Vítěz MS",
         game.actual_winner,
         lambda: game.actual_winner,
         lambda pr: pr.winner_country if pr else None),
    ]:
        actual_name = get_name()
        if not actual_name:
            continue
        correct = [p for p in participants if get_tip_id(pred_map.get(p.id)) == actual_id]
        wrong = [p for p in participants if p not in correct]
        if not correct or not wrong:
            continue
        row = {
            "Zápas": "Tipovačka",
            "Hráč": actual_name,
            "Post": "—",
            "Vlastník": ", ".join(p.name for p in correct),
            "Event": label,
        }
        for p in participants:
            if p in correct:
                row[p.name] = f"+{50 * len(wrong):.0f} Kč"
            else:
                row[p.name] = f"-{50 * len(correct):.0f} Kč"
        rows.append(row)
    return rows


if not events:
    st.info("Zatím žádné body. Importuj výsledky zápasů.")
else:
    sorted_events = sorted(events, key=lambda e: (e["match"].played_at or "", -e["event_value"]), reverse=True)
    all_rows = _build_event_rows(sorted_events, participants) + _build_prediction_rows(db, game_id, participants, pred_balances)
    st.dataframe(pd.DataFrame(all_rows), use_container_width=True, hide_index=True)

st.divider()

# ----------------------------------------------------------------
# SEKCE 3: Detail účastníka
# ----------------------------------------------------------------
st.subheader("Detail účastníka")

# Příprava: kola a Nth zápas každého týmu
rounds = db.query(Round).filter(Round.game_id == game_id).order_by(Round.round_number).all()
rounds_by_id = {r.id: r for r in rounds}

all_game_matches = (
    db.query(Match).filter(Match.game_id == game_id).order_by(Match.played_at).all()
)
team_matches: dict[str, list[int]] = {}  # team -> [match_id kola 1, kola 2, ...]
_tc: dict[str, int] = {}
for _m in all_game_matches:
    for _team in (_m.home_team, _m.away_team):
        if _team:
            _tc[_team] = _tc.get(_team, 0) + 1
            team_matches.setdefault(_team, []).append(_m.id)

col_p, col_r = st.columns(2)
with col_p:
    sel_name = st.selectbox("Vyber účastníka", [p.name for p in participants])
    sel_p = next(p for p in participants if p.name == sel_name)
with col_r:
    round_opts = {r.id: r.name for r in rounds}
    sel_round_id = st.selectbox(
        "Kolo",
        list(round_opts.keys()),
        index=len(rounds) - 1,
        format_func=lambda rid: round_opts[rid],
        key="detail_round",
    )
    sel_round = rounds_by_id[sel_round_id]

others_count = len(participants) - 1

# Eventy pro tohoto účastníka a vybrané kolo
my_events_round = [
    ev for ev in events
    if ev["owner"].id == sel_p.id and ev.get("round") and ev["round"].id == sel_round_id
]

if my_events_round:
    sorted_my = sorted(my_events_round, key=lambda e: (e["match"].played_at or "", -e["event_value"]), reverse=True)
    detail_rows = []
    for ev in sorted_my:
        match = ev["match"]
        match_label = (
            f"{match.home_team} {match.home_score}–{match.away_score} {match.away_team}"
            if match.home_team else match.external_id
        )
        detail_rows.append({
            "Zápas": match_label,
            "Hráč": ev["player"].name,
            "Post": ev["player"].position,
            "Event": EVENT_LABELS.get(ev["event_type"], ev["event_type"]),
            "Získáno": f"+{ev['event_value'] * others_count:.0f} Kč",
        })
    st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

# Nominovaní hráči bez bodů pro vybrané kolo
event_match_set: set[tuple[int, int]] = {
    (ev["player"].id, ev["match"].id) for ev in my_events_round
}

nom = db.query(LineupNomination).filter(
    LineupNomination.participant_id == sel_p.id,
    LineupNomination.round_id == sel_round_id,
).first()

zero_rows = []
if nom:
    slots = db.query(LineupSlot).filter(LineupSlot.nomination_id == nom.id).all()
    for slot in slots:
        pid = slot.player_id
        player = db.get(FootballPlayer, pid)
        if not player:
            continue
        team = player.club or player.country
        if not team:
            continue
        team_match_ids = team_matches.get(team, [])
        idx = sel_round.round_number - 1
        if idx < 0 or idx >= len(team_match_ids):
            continue
        match_id = team_match_ids[idx]
        if (pid, match_id) in event_match_set:
            continue  # Má body → zobrazí se nahoře
        stat = db.query(PlayerMatchStats).filter(
            PlayerMatchStats.player_id == pid,
            PlayerMatchStats.match_id == match_id,
            PlayerMatchStats.played == True,
        ).first()
        if not stat:
            continue
        match = db.get(Match, match_id)
        if not match:
            continue
        match_label = (
            f"{match.home_team} {match.home_score}–{match.away_score} {match.away_team}"
            if match.home_team else match.external_id
        )
        zero_rows.append({
            "Zápas": match_label,
            "Hráč": player.name,
            "Post": player.position,
            "Event": "—",
            "Získáno": "0 Kč",
        })

if zero_rows:
    if my_events_round:
        st.caption("Hráči bez bodů v odehraných zápasech:")
    st.dataframe(pd.DataFrame(zero_rows), use_container_width=True, hide_index=True)

if not my_events_round and not zero_rows:
    if not nom:
        st.info(f"Pro {sel_round.name} zatím není uložena nominace.")
    else:
        st.info("Žádné odehrané zápasy v tomto kole.")
    st.metric("Celkový zůstatek", f"{total_balances[sel_p.id]:+.0f} Kč")

# ----------------------------------------------------------------
# SEKCE 4: Tipovačka — vyhodnocení
# ----------------------------------------------------------------
game = db.get(Game, game_id)
if game and (game.actual_winner or game.actual_top_scorer_id):
    st.divider()
    st.subheader("🎯 Tipovačka — vyhodnocení")

    preds = db.query(TournamentPrediction).filter(TournamentPrediction.game_id == game_id).all()
    pred_map = {p.participant_id: p for p in preds}

    tip_rows = []
    for category, label, actual_val, get_tip in [
        ("winner", "🏆 Vítěz MS", game.actual_winner,
         lambda pr: pr.winner_country if pr else None),
        ("top_scorer", "⚽ Nejlepší střelec",
         db.get(FootballPlayer, game.actual_top_scorer_id).name if game.actual_top_scorer_id and db.get(FootballPlayer, game.actual_top_scorer_id) else None,
         lambda pr: db.get(FootballPlayer, pr.top_scorer_player_id).name if pr and pr.top_scorer_player_id and db.get(FootballPlayer, pr.top_scorer_player_id) else None),
    ]:
        if not actual_val:
            continue
        row = {"Kategorie": label, "Skutečnost": actual_val}
        for p in participants:
            pr = pred_map.get(p.id)
            tip = get_tip(pr)
            delta = pred_balances[p.id]  # souhrnně, ne per-kategorie
            hit = tip == actual_val
            row[p.name] = f"{'✅' if hit else '❌'} {tip or '—'}"
        tip_rows.append(row)

    if tip_rows:
        st.dataframe(pd.DataFrame(tip_rows), use_container_width=True, hide_index=True)

    # Výplata tipovačky
    pred_cols = st.columns(len(participants))
    for i, p in enumerate(participants):
        bal = pred_balances[p.id]
        if abs(bal) > 0.01:
            pred_cols[i].metric(p.name, f"{bal:+.0f} Kč", delta_color="normal")
        else:
            pred_cols[i].metric(p.name, "0 Kč")
