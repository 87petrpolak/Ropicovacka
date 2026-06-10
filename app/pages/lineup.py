import streamlit as st
from datetime import datetime
from app.state import get_db, require_active_game
from app.models.models import Participant, Round, DraftSession, FootballPlayer
from app.services.draft_engine import get_participant_squad
from app.services.lineup_manager import (
    get_or_create_nomination,
    submit_lineup,
    get_lineup_players,
    LineupError,
)
from app.models.models import LineupChangeLog
from app.services.squad_validator import LINEUP_SIZE
from app.services.next_match_service import get_next_matches
from app.utils.time_utils import fmt_prague

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
    round_opts = {r.id: r.name for r in rounds}
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
        f"⏰ Deadline uplynul ({fmt_prague(deadline, '%d.%m. %H:%M')}). "
        "Nominaci nelze změnit."
    )
elif deadline:
    remaining = deadline - now
    hours = int(remaining.total_seconds() // 3600)
    minutes = int((remaining.total_seconds() % 3600) // 60)
    st.info(
        f"📅 Deadline: {fmt_prague(deadline, '%d.%m. %H:%M')} — "
        f"zbývá {hours}h {minutes}m"
    )

editable = not locked and not deadline_passed

# ----------------------------------------------------------------
# Výběr hráčů — fragment = žádný DB dotaz při každém kliknutí
# ----------------------------------------------------------------
POS_ORDER = ["GK", "DEF", "MID", "FWD"]
POS_LABELS = {"GK": "Brankáři", "DEF": "Obránci", "MID": "Záložníci", "FWD": "Útočníci"}
POS_INFO = {"GK": "přesně 1", "DEF": "3–5", "MID": "3–5", "FWD": "1–3"}

by_pos: dict[str, list] = {}
for pl in squad:
    by_pos.setdefault(pl.position, []).append(pl)

# Načti příští zápasy na úrovni stránky (mimo fragment) — cachováno 30 min
try:
    next_matches = get_next_matches()
except Exception:
    next_matches = {}


@st.fragment
def _lineup_form():
    st.subheader(f"Vyber přesně {LINEUP_SIZE} hráčů z tvého {len(squad)}-hráčového kádru")

    selected_ids: set[int] = set()

    for pos in POS_ORDER:
        pos_players = by_pos.get(pos, [])
        if not pos_players:
            continue
        st.caption(f"**{POS_LABELS[pos]}** — {POS_INFO.get(pos, '')}")
        for pl in sorted(pos_players, key=lambda x: x.name):
            match_info = next_matches.get(pl.club or pl.country, {})
            if match_info:
                next_label = f"  —  vs {match_info['opponent']}, {match_info['date_str']}"
            else:
                next_label = ""
            checked = st.checkbox(
                f"{pl.name} ({pl.club or pl.country}){next_label}",
                value=pl.id in current_ids,
                key=f"ln_{nomination.id}_{pl.id}",
                disabled=not editable,
            )
            if checked:
                selected_ids.add(pl.id)

    count = len(selected_ids)
    color = "green" if count == LINEUP_SIZE else "red"
    st.markdown(f"**Vybráno: :{color}[{count} / {LINEUP_SIZE}]**")

    # Captain & substitute selectors (visible only when 11 players selected)
    captain_id: int | None = None
    substitute_id: int | None = None

    if count == LINEUP_SIZE or not editable:
        selected_players = [pl for pl in squad if pl.id in selected_ids]
        selected_players_sorted = sorted(selected_players, key=lambda x: (POS_ORDER.index(x.position), x.name))

        bench_players = [pl for pl in squad if pl.id not in selected_ids]
        bench_players_sorted = sorted(bench_players, key=lambda x: (POS_ORDER.index(x.position), x.name))

        st.divider()
        col_c, col_s = st.columns(2)

        with col_c:
            captain_options = [None] + [pl.id for pl in selected_players_sorted]
            captain_labels = ["— nevybráno —"] + [f"{pl.name} ({str(pl.position).split('.')[-1]})" for pl in selected_players_sorted]
            default_cap_idx = 0
            if nomination.captain_player_id and nomination.captain_player_id in selected_ids:
                try:
                    default_cap_idx = captain_options.index(nomination.captain_player_id)
                except ValueError:
                    pass
            cap_idx = st.selectbox(
                "🅲 Kapitán (2× body)",
                range(len(captain_options)),
                index=default_cap_idx,
                format_func=lambda i: captain_labels[i],
                key=f"cap_{nomination.id}",
                disabled=not editable,
            )
            captain_id = captain_options[cap_idx]

        with col_s:
            sub_options = [None] + [pl.id for pl in bench_players_sorted]
            sub_labels = ["— nevybráno —"] + [f"{pl.name} ({str(pl.position).split('.')[-1]})" for pl in bench_players_sorted]
            default_sub_idx = 0
            if nomination.substitute_player_id and nomination.substitute_player_id not in selected_ids:
                try:
                    default_sub_idx = sub_options.index(nomination.substitute_player_id)
                except ValueError:
                    pass
            sub_idx = st.selectbox(
                "🔄 Náhradník",
                range(len(sub_options)),
                index=default_sub_idx,
                format_func=lambda i: sub_labels[i],
                key=f"sub_{nomination.id}",
                disabled=not editable,
            )
            substitute_id = sub_options[sub_idx]

    if editable:
        if st.button("💾 Uložit nominaci", type="primary", use_container_width=True, disabled=count != LINEUP_SIZE):
            try:
                submit_lineup(db, nomination, list(selected_ids), session_id,
                              captain_id=captain_id, substitute_id=substitute_id)
                st.success("✅ Nominace uložena!")
            except LineupError as e:
                st.error(str(e))


_lineup_form()

# ----------------------------------------------------------------
# Historie změn nominace
# ----------------------------------------------------------------
change_logs = (
    db.query(LineupChangeLog)
    .filter(LineupChangeLog.nomination_id == nomination.id)
    .order_by(LineupChangeLog.changed_at.desc())
    .all()
)
if change_logs:
    def _reformat_log(names_str: str) -> str:
        """Přeformátuje starý 'Jméno1, Jméno2' formát na nový 'Pozice: Jméno1 | Pozice: Jméno2'."""
        if not names_str or " | " in names_str:
            return names_str  # Už nový formát
        pos_order = ["GK", "DEF", "MID", "FWD"]
        pos_labels = {"GK": "Brankář", "DEF": "Obránci", "MID": "Záložníci", "FWD": "Útočníci"}
        groups: dict[str, list[str]] = {p: [] for p in pos_order}
        for name in [n.strip() for n in names_str.split(",")]:
            player = db.query(FootballPlayer).filter(FootballPlayer.name == name).first()
            pos = player.position if player and player.position in groups else "FWD"
            groups[pos].append(name)
        parts = [f"{pos_labels[p]}: {', '.join(sorted(groups[p]))}" for p in pos_order if groups[p]]
        return " | ".join(parts)

    with st.expander(f"📋 Historie změn ({len(change_logs)})"):
        for log in change_logs:
            ts = fmt_prague(log.changed_at)
            parts = []
            if log.added_players:
                parts.append(f"✅ Přidáni: {_reformat_log(log.added_players)}")
            if log.removed_players:
                parts.append(f"❌ Odebráni: {_reformat_log(log.removed_players)}")
            if not parts:
                parts = ["Uložena nominace"]
            st.caption(f"**{ts}** — {' | '.join(parts)}")

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
            suffix = ""
            if pl.id == nomination.captain_player_id:
                suffix = " 🅲 kapitán"
            st.write(f"**{POS_LABELS.get(pl.position, pl.position)}** {pl.name} ({pl.club or pl.country}){suffix}")
    if nomination.substitute_player_id:
        from app.models.models import FootballPlayer as FP
        sub = db.get(FP, nomination.substitute_player_id)
        if sub:
            st.write(f"**Náhradník** 🔄 {sub.name} ({sub.club or sub.country})")
