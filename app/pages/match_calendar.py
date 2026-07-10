"""
Kalendář zápasů — zobrazuje jen zápasy kde máme nominované hráče.
Timeline: odehrané nahoře, nadcházející dole, auto-scroll na první nadcházející.
"""
import streamlit as st
import streamlit.components.v1 as components
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from app.state import get_db, require_active_game
from app.models.models import (
    Participant, Round, LineupNomination, LineupSlot, FootballPlayer, DraftSession
)
from app.services.next_match_service import get_all_ms_matches

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

round_opts = {r.id: r.name for r in rounds}
sel_round_id = st.selectbox(
    "Kolo",
    list(round_opts.keys()),
    index=len(rounds) - 1,
    format_func=lambda rid: round_opts[rid],
)
selected_round = next(r for r in rounds if r.id == sel_round_id)

st.divider()

# ----------------------------------------------------------------
# Barvy a ikony účastníků
# ----------------------------------------------------------------
PARTICIPANT_COLORS = ["🔵", "🟡", "🔴"]

# ----------------------------------------------------------------
# Načti nominované hráče pro každého účastníka v tomto kole
# ----------------------------------------------------------------
nominated: dict[int, dict] = {}
team_to_players: dict[str, list[dict]] = defaultdict(list)

for i, participant in enumerate(participants):
    nom = db.query(LineupNomination).filter(
        LineupNomination.participant_id == participant.id,
        LineupNomination.round_id == sel_round_id,
    ).first()
    if not nom:
        continue

    slots = db.query(LineupSlot).filter(LineupSlot.nomination_id == nom.id).all()
    captain_id = nom.captain_player_id
    substitute_id = nom.substitute_player_id

    for slot in slots:
        player = db.get(FootballPlayer, slot.player_id)
        if not player:
            continue
        team = player.club or player.country
        if not team:
            continue
        team_to_players[team].append({
            "participant": participant,
            "player": player,
            "icon": PARTICIPANT_COLORS[i % len(PARTICIPANT_COLORS)],
            "is_captain": (player.id == captain_id),
            "is_substitute": False,
        })

    if substitute_id:
        sub = db.get(FootballPlayer, substitute_id)
        if sub:
            team = sub.club or sub.country
            if team:
                team_to_players[team].append({
                    "participant": participant,
                    "player": sub,
                    "icon": PARTICIPANT_COLORS[i % len(PARTICIPANT_COLORS)],
                    "is_captain": False,
                    "is_substitute": True,
                })

if not team_to_players:
    st.warning("Pro toto kolo zatím nikdo nenominoval sestavu.")
    st.stop()

# ----------------------------------------------------------------
# Vyber zápasy pro dané kolo — Nth zápas (skupiny) nebo Nth playoff zápas
# ----------------------------------------------------------------
try:
    all_matches = get_all_ms_matches()
except Exception:
    all_matches = []

nominated_teams = set(team_to_players.keys())
round_number = selected_round.round_number

match_for_team: dict[str, dict] = {}

if round_number <= 3:
    # Skupiny: Nth skupinový zápas každého týmu (pořadí dle data)
    team_count: dict[str, int] = {}
    for m in all_matches:
        if m.get("is_playoff"):
            continue
        home, away = m.get("home", ""), m.get("away", "")
        for team, opp in [(home, away), (away, home)]:
            if not team:
                continue
            team_count[team] = team_count.get(team, 0) + 1
            if team_count[team] == round_number:
                match_for_team[team] = m
else:
    # Playoff: první playoff zápas každého týmu PO deadlinu kola.
    # Tím se vyhneme počítání Nth zápasu — které selhává pokud Flashscore
    # nevrátí všechna kola (R16 pro den -2 chybělo v datech).
    deadline = selected_round.lineup_deadline
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    for m in sorted(all_matches, key=lambda x: x.get("played_at") or datetime.max.replace(tzinfo=timezone.utc)):
        if not m.get("is_playoff"):
            continue
        played_at = m.get("played_at")
        if deadline and played_at:
            if played_at.tzinfo is None:
                played_at = played_at.replace(tzinfo=timezone.utc)
            if played_at < deadline:
                continue
        home, away = m.get("home", ""), m.get("away", "")
        for team, opp in [(home, away), (away, home)]:
            if not team:
                continue
            if team not in match_for_team:
                match_for_team[team] = m

seen_ids: set[str] = set()
relevant: list[dict] = []
missing_teams: list[str] = []
for team in nominated_teams:
    m = match_for_team.get(team)
    if m and m.get("match_id") not in seen_ids:
        seen_ids.add(m["match_id"])
        relevant.append(m)
    elif not m:
        missing_teams.append(team)

if not relevant:
    st.info("Žádné zápasy pro nominované týmy nenalezeny. Data se načítají z Flashscore.")
    st.stop()

if missing_teams:
    st.warning(
        f"Zápas pro toto kolo zatím nenalezen: **{', '.join(sorted(missing_teams))}**. "
        "Data se průběžně načítají z Flashscore (cache 2 h)."
    )

relevant.sort(key=lambda x: x.get("played_at") or datetime.max.replace(tzinfo=timezone.utc))

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
    "Česko": "🇨🇿", "Švédsko": "🇸🇪", "Egypt": "🇪🇬", "Nový Zéland": "🇳🇿",
}

def flag(team: str) -> str:
    return FLAGS.get(team, "⚽")

# ----------------------------------------------------------------
# Najdi index prvního nadcházejícího zápasu (split point)
# ----------------------------------------------------------------
PRAGUE_TZ = timezone(timedelta(hours=2))
CZ_DAYS = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]

now_utc = datetime.now(tz=timezone.utc)
split_idx = len(relevant)
for i, m in enumerate(relevant):
    pa = m.get("played_at")
    if pa:
        if pa.tzinfo is None:
            pa = pa.replace(tzinfo=timezone.utc)
        if pa > now_utc and m.get("status") != "3":
            split_idx = i
            break

# ----------------------------------------------------------------
# Render zápasů
# ----------------------------------------------------------------
def render_match(m: dict, dimmed: bool = False) -> None:
    home, away = m["home"], m["away"]
    is_finished = m["status"] == "3"

    if is_finished:
        time_label = "✅ odehráno"
    else:
        pa = m.get("played_at")
        if pa:
            if pa.tzinfo is None:
                pa = pa.replace(tzinfo=timezone.utc)
            dt_prague = pa.astimezone(PRAGUE_TZ)
            time_label = f"🕐 {dt_prague.strftime('%-d.%-m. %H:%M')}"
        else:
            time_label = f"🕐 {m.get('time_str', '?')}"

    opacity = "0.5" if dimmed else "1.0"
    st.markdown(
        f"<div style='opacity:{opacity}'>",
        unsafe_allow_html=True,
    )
    col_h, col_vs, col_a, col_t = st.columns([3, 1, 3, 2])
    with col_h:
        st.markdown(f"**{flag(home)} {home}**")
    with col_vs:
        st.markdown("<div style='text-align:center;font-weight:bold;'>vs</div>", unsafe_allow_html=True)
    with col_a:
        st.markdown(f"**{flag(away)} {away}**")
    with col_t:
        st.markdown(f"<div style='text-align:right;color:gray;'>{time_label}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    match_players: list[dict] = team_to_players.get(home, []) + team_to_players.get(away, [])
    by_participant: dict[str, list] = defaultdict(list)
    for entry in match_players:
        by_participant[entry["participant"].name].append(entry)

    for p_name, entries in by_participant.items():
        icon = entries[0]["icon"]
        player_names = []
        for e in sorted(entries, key=lambda x: (x["is_substitute"], x["player"].name)):
            name = e["player"].name
            if e["is_captain"]:
                name += " 🅲"
            if e["is_substitute"]:
                name = f"🔄 {name}"
            player_names.append(name)
        opacity_style = f"opacity:{opacity};" if dimmed else ""
        st.markdown(
            f"<div style='{opacity_style}'>{icon} <b>{p_name}:</b> {', '.join(player_names)}</div>",
            unsafe_allow_html=True,
        )

    st.divider()


def _day_label(m: dict) -> str:
    pa = m.get("played_at")
    if not pa:
        return m.get("date_str", "")
    if pa.tzinfo is None:
        pa = pa.replace(tzinfo=timezone.utc)
    dt = pa.astimezone(PRAGUE_TZ)
    return f"{CZ_DAYS[dt.weekday()]} {dt.strftime('%-d.%-m.')}"


def _render_section(matches: list[dict], dimmed: bool) -> None:
    last_day = None
    for m in matches:
        day = _day_label(m)
        if day != last_day:
            st.markdown(
                f"<div style='font-size:0.85rem;font-weight:600;color:gray;"
                f"margin:12px 0 4px 0;text-transform:uppercase;letter-spacing:.05em'>"
                f"── {day} ──</div>",
                unsafe_allow_html=True,
            )
            last_day = day
        render_match(m, dimmed=dimmed)


# Odehrané zápasy (ztlumené)
_render_section(relevant[:split_idx], dimmed=True)

# Marker pro auto-scroll
st.markdown('<div id="calendar-now"></div>', unsafe_allow_html=True)

# Nadcházející zápasy
_render_section(relevant[split_idx:], dimmed=False)

# Auto-scroll na první nadcházející zápas (jen pokud existují odehrané)
if split_idx > 0:
    components.html("""
    <script>
    const scroll = () => {
        const el = window.parent.document.getElementById('calendar-now');
        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            setTimeout(scroll, 200);
        }
    };
    setTimeout(scroll, 400);
    </script>
    """, height=0)
