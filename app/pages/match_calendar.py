"""
Kalendář zápasů — zobrazuje jen zápasy kde máme nominované hráče.
"""
import streamlit as st
from collections import defaultdict
from app.state import get_db, require_active_game
from app.models.models import (
    Participant, Round, LineupNomination, LineupSlot, FootballPlayer, DraftSession
)
from app.services.next_match_service import get_all_ms_matches
from app.services.draft_engine import get_participant_squad

st.title("📅 Kalendář zápasů")

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

if not rounds:
    st.info("Nejsou definována žádná kola. Přejdi na **Administrace**.")
    st.stop()

# Výběr kola
round_opts = {r.id: r.name for r in rounds}
sel_round_id = st.selectbox(
    "Kolo",
    list(round_opts.keys()),
    format_func=lambda rid: round_opts[rid],
)
selected_round = next(r for r in rounds if r.id == sel_round_id)

st.divider()

# ----------------------------------------------------------------
# Barvy a ikony účastníků
# ----------------------------------------------------------------
PARTICIPANT_COLORS = ["🔵", "🟡", "🔴"]
PARTICIPANT_BG = ["#e8f4fd", "#fffbe6", "#fdecea"]

# ----------------------------------------------------------------
# Načti nominované hráče pro každého účastníka v tomto kole
# hrac_id → {participant, player}
# ----------------------------------------------------------------
session = db.query(DraftSession).filter(
    DraftSession.game_id == game_id
).order_by(DraftSession.id.desc()).first()

nominated: dict[int, dict] = {}   # player_id → {participant, player}
team_to_players: dict[str, list[dict]] = defaultdict(list)  # team_name → [{participant, player}]

for i, participant in enumerate(participants):
    nom = db.query(LineupNomination).filter(
        LineupNomination.participant_id == participant.id,
        LineupNomination.round_id == sel_round_id,
    ).first()
    if not nom:
        continue

    slots = db.query(LineupSlot).filter(LineupSlot.nomination_id == nom.id).all()
    captain_id = nom.captain_player_id

    for slot in slots:
        player = db.get(FootballPlayer, slot.player_id)
        if not player:
            continue
        team = player.club or player.country
        if not team:
            continue
        entry = {
            "participant": participant,
            "player": player,
            "icon": PARTICIPANT_COLORS[i % len(PARTICIPANT_COLORS)],
            "is_captain": (player.id == captain_id),
        }
        team_to_players[team].append(entry)

if not team_to_players:
    st.warning("Pro toto kolo zatím nikdo nenominoval sestavu.")
    st.stop()

# ----------------------------------------------------------------
# Vlajky týmů
# ----------------------------------------------------------------
FLAGS: dict[str, str] = {
    "Španělsko": "🇪🇸", "Anglie": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Francie": "🇫🇷", "Německo": "🇩🇪",
    "Brazílie": "🇧🇷", "Argentina": "🇦🇷", "Portugalsko": "🇵🇹", "Nizozemsko": "🇳🇱",
    "Norsko": "🇳🇴", "Belgie": "🇧🇪", "Kolumbie": "🇨🇴", "Mexiko": "🇲🇽",
    "USA": "🇺🇸", "Kanada": "🇨🇦", "Uruguay": "🇺🇾", "Chile": "🇨🇱",
    "Ekvádor": "🇪🇨", "Peru": "🇵🇪", "Paraguay": "🇵🇾", "Venezuela": "🇻🇪",
    "Japonsko": "🇯🇵", "Jižní Korea": "🇰🇷", "Austrálie": "🇦🇺", "Írán": "🇮🇷",
    "Saúdská Arábie": "🇸🇦", "Irák": "🇮🇶", "Maroko": "🇲🇦", "Senegal": "🇸🇳",
    "Nigérie": "🇳🇬", "Kamerun": "🇨🇲", "Ghana": "🇬🇭", "Pobřeží slonoviny": "🇨🇮",
    "Chorvatsko": "🇭🇷", "Švýcarsko": "🇨🇭", "Dánsko": "🇩🇰", "Turecko": "🇹🇷",
    "Polsko": "🇵🇱", "Srbsko": "🇷🇸", "Slovinsko": "🇸🇮", "Slovensko": "🇸🇰",
    "Kapverdy": "🇨🇻", "Curacao": "🇨🇼", "DR Kongo": "🇨🇩", "Alžírsko": "🇩🇿",
    "Jihoafrická republika": "🇿🇦", "Katar": "🇶🇦", "Panama": "🇵🇦",
    "Bosna a Hercegovina": "🇧🇦", "Haiti": "🇭🇹", "Skotsko": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
}

def flag(team: str) -> str:
    return FLAGS.get(team, "⚽")

# ----------------------------------------------------------------
# Načti všechny MS zápasy a filtruj relevantní
# ----------------------------------------------------------------
try:
    all_matches = get_all_ms_matches()
except Exception:
    all_matches = []

relevant = [
    m for m in all_matches
    if m["home"] in team_to_players or m["away"] in team_to_players
]

if not relevant:
    st.info("Žádné zápasy pro nominované týmy nenalezeny. Data se načítají z Flashscore.")
    st.stop()

# ----------------------------------------------------------------
# Seskup podle data a zobraz
# ----------------------------------------------------------------
by_date: dict[str, list] = defaultdict(list)
for m in relevant:
    by_date[m["date_str"] or "?"].append(m)

for date_label, matches in by_date.items():
    st.markdown(f"### 📆 {date_label}")

    for m in matches:
        home, away = m["home"], m["away"]
        is_finished = m["status"] == "3"
        time_label = "✅ odehráno" if is_finished else f"🕐 {m['time_str']}"

        # Hlavička zápasu
        col_h, col_vs, col_a, col_t = st.columns([3, 1, 3, 2])
        with col_h:
            st.markdown(f"**{flag(home)} {home}**")
        with col_vs:
            st.markdown("<div style='text-align:center;font-weight:bold;'>vs</div>", unsafe_allow_html=True)
        with col_a:
            st.markdown(f"**{flag(away)} {away}**")
        with col_t:
            st.markdown(f"<div style='text-align:right;color:gray;'>{time_label}</div>", unsafe_allow_html=True)

        # Nominovaní hráči v tomto zápasu
        match_players: list[dict] = team_to_players.get(home, []) + team_to_players.get(away, [])

        # Seskup podle účastníka
        by_participant: dict[str, list] = defaultdict(list)
        for entry in match_players:
            by_participant[entry["participant"].name].append(entry)

        for p_name, entries in by_participant.items():
            icon = entries[0]["icon"]
            player_names = []
            for e in sorted(entries, key=lambda x: x["player"].name):
                name = e["player"].name
                if e["is_captain"]:
                    name += " 🅲"
                player_names.append(name)
            st.caption(f"{icon} **{p_name}:** {', '.join(player_names)}")

        st.divider()
