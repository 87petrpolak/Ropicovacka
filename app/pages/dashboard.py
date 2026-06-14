"""Hlavní dashboard — aktuální stav cashflow a přehled eventů."""
import pandas as pd
import streamlit as st
from app.state import get_db, require_active_game
from app.models.models import Participant, LineupNomination, LineupSlot, FootballPlayer, PlayerMatchStats, Match
from app.services.cashflow import compute_events, compute_balances, cashflow_per_event, EVENT_LABELS

col_title, col_btn = st.columns([4, 1])
col_title.title("Dashboard")

with col_btn:
    st.markdown("<div style='margin-top:1.5rem'>", unsafe_allow_html=True)
    force = st.checkbox("↺ Přeimportovat vše", help="Smaže a znovu stáhne statistiky všech zápasů (použij při opravě chyby)")
    if st.button("🔄 Aktualizovat", use_container_width=True, help="Načte nejnovější výsledky z Livesport.cz"):
        from app.providers.livesport_provider import LivesportProvider
        from app.services.data_refresh import run_refresh
        game_id_tmp = require_active_game()
        if game_id_tmp:
            with st.spinner("Načítám…"):
                try:
                    if force:
                        from app.models.models import PlayerMatchStats as PMS
                        db_tmp = get_db()
                        db_tmp.query(PMS).delete()
                        db_tmp.commit()
                    provider = LivesportProvider()
                    result = run_refresh(get_db(), provider, game_id_tmp, import_players=False, import_matches=True)
                    from app.services.next_match_service import invalidate_match_cache
                    invalidate_match_cache()
                    if result.errors:
                        st.error("\n".join(result.errors[:5]))
                    parts = []
                    if result.matches_added: parts.append(f"+{result.matches_added} zápasů")
                    if result.matches_updated: parts.append(f"~{result.matches_updated} zápasů aktualizováno")
                    if result.stats_added: parts.append(f"+{result.stats_added} statistik")
                    if result.stats_updated: parts.append(f"~{result.stats_updated} statistik aktualizováno")
                    st.success("✅ " + (", ".join(parts) or "Nic nového"))
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

# Ověření zero-sum (debug)
total = sum(balances.values())

# ----------------------------------------------------------------
# SEKCE 1: Aktuální stav
# ----------------------------------------------------------------
st.subheader("Aktuální stav")

cols = st.columns(len(participants))
for i, p in enumerate(participants):
    bal = balances[p.id]
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


if not events:
    st.info("Zatím žádné body. Importuj výsledky zápasů.")
else:
    sorted_events = sorted(events, key=lambda e: (e["match"].played_at or "", -e["event_value"]), reverse=True)
    st.dataframe(pd.DataFrame(_build_event_rows(sorted_events, participants)), use_container_width=True, hide_index=True)

st.divider()

# ----------------------------------------------------------------
# SEKCE 3: Detail účastníka
# ----------------------------------------------------------------
st.subheader("Detail účastníka")

sel_name = st.selectbox("Vyber účastníka", [p.name for p in participants])
sel_p = next(p for p in participants if p.name == sel_name)

my_events = [ev for ev in events if ev["owner"].id == sel_p.id]

others_count = len(participants) - 1

if my_events:
    sorted_my = sorted(my_events, key=lambda e: (e["match"].played_at or "", -e["event_value"]), reverse=True)
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

# Nominovaní hráči bez bodů (odehráli zápas, ale nic nevydělali)
noms = db.query(LineupNomination).filter(
    LineupNomination.participant_id == sel_p.id
).all()
nom_ids_q = [n.id for n in noms]

# Základní sestava (11 hráčů)
nominated_pids = {
    s.player_id for s in db.query(LineupSlot).filter(
        LineupSlot.nomination_id.in_(nom_ids_q)
    ).all()
}
# Náhradník — přidej jen pokud skutečně nastoupil (played=True)
sub_pids = {n.substitute_player_id for n in noms if n.substitute_player_id}
for spid in sub_pids:
    stats = db.query(PlayerMatchStats).filter(
        PlayerMatchStats.player_id == spid,
        PlayerMatchStats.played == True,
    ).first()
    if stats:
        nominated_pids.add(spid)
event_pids = {ev["player"].id for ev in my_events}
zero_rows = []
for pid in nominated_pids - event_pids:
    played_stats = db.query(PlayerMatchStats).filter(
        PlayerMatchStats.player_id == pid,
        PlayerMatchStats.played == True,
    ).all()
    for s in played_stats:
        match = db.get(Match, s.match_id)
        player = db.get(FootballPlayer, pid)
        if match and player:
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
    if my_events:
        st.caption("Hráči bez bodů v odehraných zápasech:")
    st.dataframe(pd.DataFrame(zero_rows), use_container_width=True, hide_index=True)

if not my_events and not zero_rows:
    st.info("Tento účastník zatím nemá žádné body.")
    st.metric("Celkový zůstatek", f"{balances[sel_p.id]:+.0f} Kč")
