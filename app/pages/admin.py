import pandas as pd
import streamlit as st
from datetime import datetime
from app.state import get_db, require_active_game
from app.models.models import Round, Participant, LineupNomination, DraftSession
from app.services.lineup_manager import lock_lineup, admin_unlock_lineup

st.title("Administrace")

db = get_db()
game_id = require_active_game()
if game_id is None:
    st.stop()

# ----------------------------------------------------------------
# Kola turnaje
# ----------------------------------------------------------------
st.subheader("Kola turnaje")

rounds = db.query(Round).filter(
    Round.game_id == game_id
).order_by(Round.round_number).all()

if rounds:
    rows = [
        {
            "ID": r.id,
            "Číslo kola": r.round_number,
            "Název": r.name,
            "Deadline (UTC)": (
                r.lineup_deadline.strftime("%Y-%m-%d %H:%M") if r.lineup_deadline else "—"
            ),
        }
        for r in rounds
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("Zatím žádná kola.")

with st.expander("➕ Vytvořit kolo"):
    with st.form("create_round"):
        r_number = st.number_input(
            "Číslo kola", min_value=1, step=1, value=len(rounds) + 1
        )
        r_name = st.text_input("Název kola", placeholder="Skupina A — 1. kolo")
        r_deadline_str = st.text_input(
            "Deadline nominace (RRRR-MM-DD HH:MM UTC, volitelné)",
            placeholder="2026-06-14 17:00",
        )
        if st.form_submit_button("Vytvořit kolo"):
            deadline_dt = None
            if r_deadline_str.strip():
                try:
                    deadline_dt = datetime.strptime(r_deadline_str.strip(), "%Y-%m-%d %H:%M")
                except ValueError:
                    st.error("Neplatný formát deadlinu. Použij RRRR-MM-DD HH:MM.")
                    st.stop()
            db.add(Round(
                game_id=game_id,
                name=r_name.strip() or f"Kolo {r_number}",
                round_number=int(r_number),
                lineup_deadline=deadline_dt,
            ))
            db.commit()
            st.success("Kolo bylo vytvořeno.")
            st.rerun()

if rounds:
    with st.expander("✏️ Upravit deadline kola"):
        sel_round_name = st.selectbox(
            "Kolo", [r.name for r in rounds], key="edit_round_sel"
        )
        sel_round = next(r for r in rounds if r.name == sel_round_name)
        current_dl = (
            sel_round.lineup_deadline.strftime("%Y-%m-%d %H:%M")
            if sel_round.lineup_deadline else ""
        )
        new_dl = st.text_input(
            "Nový deadline (RRRR-MM-DD HH:MM UTC, prázdné = smazat)",
            value=current_dl,
            key="edit_dl_input",
        )
        if st.button("Uložit deadline"):
            if new_dl.strip():
                try:
                    sel_round.lineup_deadline = datetime.strptime(
                        new_dl.strip(), "%Y-%m-%d %H:%M"
                    )
                    db.commit()
                    st.success("Deadline uložen.")
                    st.rerun()
                except ValueError:
                    st.error("Neplatný formát. Použij RRRR-MM-DD HH:MM.")
            else:
                sel_round.lineup_deadline = None
                db.commit()
                st.success("Deadline smazán.")
                st.rerun()

    with st.expander("🗑️ Smazat kolo"):
        del_round_name = st.selectbox(
            "Kolo ke smazání", [r.name for r in rounds], key="del_round_sel"
        )
        st.warning("Smazáním kola se odstraní i všechny nominace pro toto kolo.")
        if st.button("Smazat kolo", type="secondary"):
            del_round = next(r for r in rounds if r.name == del_round_name)
            db.delete(del_round)
            db.commit()
            st.success(f"Kolo '{del_round_name}' bylo smazáno.")
            st.rerun()

st.divider()

# ----------------------------------------------------------------
# Správa nominací
# ----------------------------------------------------------------
st.subheader("Správa nominací")

participants = db.query(Participant).filter(
    Participant.game_id == game_id
).order_by(Participant.draft_order).all()
sessions = db.query(DraftSession).filter(
    DraftSession.game_id == game_id
).order_by(DraftSession.id.desc()).all()

if rounds and participants and sessions:
    col1, col2 = st.columns(2)
    with col1:
        sel_p_name = st.selectbox("Účastník", [p.name for p in participants], key="admin_p")
        sel_p = next(p for p in participants if p.name == sel_p_name)
    with col2:
        sel_r_name = st.selectbox("Kolo", [r.name for r in rounds], key="admin_r")
        sel_r = next(r for r in rounds if r.name == sel_r_name)

    nom = db.query(LineupNomination).filter(
        LineupNomination.participant_id == sel_p.id,
        LineupNomination.round_id == sel_r.id,
    ).first()

    if nom:
        st.write(f"Stav: {'🔒 Zamknutá' if nom.is_locked else '🔓 Odemknutá'}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔒 Zamknout nominaci"):
                lock_lineup(db, nom)
                st.success("Nominace zamknutá.")
                st.rerun()
        with c2:
            if st.button("🔓 Administrátorsky odemknout"):
                admin_unlock_lineup(db, nom)
                st.success("Nominace odemknutá.")
                st.rerun()
    else:
        st.info("Pro tuto kombinaci účastníka a kola zatím nebyla podána nominace.")

    st.divider()
    st.subheader("Hromadné zamknutí nominací pro kolo")
    lock_round_name = st.selectbox(
        "Kolo", [r.name for r in rounds], key="lock_all_round"
    )
    lock_round = next(r for r in rounds if r.name == lock_round_name)
    if st.button("🔒 Zamknout všechny nominace tohoto kola", type="secondary"):
        noms = db.query(LineupNomination).filter(
            LineupNomination.round_id == lock_round.id
        ).all()
        count = sum(1 for n in noms if not n.is_locked)
        for n in noms:
            n.is_locked = True
        db.commit()
        st.success(f"Zamknuto {count} nominací.")
        st.rerun()
else:
    st.info("Pro správu nominací potřebuješ alespoň jednoho účastníka, jedno kolo a draft session.")

st.divider()
st.subheader("Debug: zápasy z Flashscore")
if st.button("🔄 Vynutit refresh zápasů z Flashscore"):
    from app.services.next_match_service import (
        _fetch_all_from_api, _db_set, _CACHE_KEY_ALL,
        get_all_ms_matches, get_next_matches, invalidate_match_cache,
    )
    invalidate_match_cache()
    try:
        raw = _fetch_all_from_api()
        _db_set(_CACHE_KEY_ALL, raw)
        st.success(f"Načteno {len(raw)} zápasů z Flashscore a uloženo do cache.")
        team_count: dict[str, int] = {}
        for m in raw:
            for team in [m.get("home", ""), m.get("away", "")]:
                if team:
                    team_count[team] = team_count.get(team, 0) + 1
        for t in ["Francie", "Argentina", "Švýcarsko", "Portugalsko", "Egypt"]:
            st.write(f"  {t}: {team_count.get(t, 0)} zápasů")
    except Exception as e:
        st.error(f"Chyba: {e}")

if st.button("🔍 Debug parsování dne 0"):
    import requests
    WC_ID = "lvUBR5F8"
    _BASE = "https://1.flashscore.ninja/1/x/feed"
    _HEADERS = {"x-fsign": "SW9D1eZo", "Referer": "https://www.livesport.cz/", "User-Agent": "Mozilla/5.0"}
    for day_off in [0, 1, 2]:
        r = requests.get(f"{_BASE}/f_1_{day_off}_2_cs_1", headers=_HEADERS, timeout=10)
        raw = r.text
        in_wc = False
        wc_matches = []
        prev_zee = ""
        for block in raw.split("~"):
            rec: dict[str, str] = {}
            for pair in block.split("¬"):
                if "÷" in pair:
                    k, _, v = pair.partition("÷")
                    rec[k] = v
            if "ZEE" in rec:
                prev_zee = rec["ZEE"]
                in_wc = rec["ZEE"] == WC_ID
                continue
            if in_wc and "AA" in rec and "AE" in rec:
                wc_matches.append(f"{rec.get('AE','')} vs {rec.get('AF','')} (ZEE={prev_zee})")
        st.write(f"**Den {day_off}:** {len(wc_matches)} WC zápasů")
        for s in wc_matches:
            st.write(f"  {s}")

if st.button("🔍 Zjisti ZEE tournament IDs z dnešního feedu"):
    import requests, time as _time
    _BASE = "https://1.flashscore.ninja/1/x/feed"
    _HEADERS = {
        "x-fsign": "SW9D1eZo",
        "Referer": "https://www.livesport.cz/",
        "User-Agent": "Mozilla/5.0",
    }
    zee_counts: dict[str, int] = {}
    for day_off in [0, 1, 2, 3]:
        try:
            r = requests.get(f"{_BASE}/f_1_{day_off}_2_cs_1", headers=_HEADERS, timeout=10)
            raw = r.text
            cur_zee = ""
            for block in raw.split("~"):
                rec: dict[str, str] = {}
                for pair in block.split("¬"):
                    if "÷" in pair:
                        k, _, v = pair.partition("÷")
                        rec[k] = v
                if "ZEE" in rec:
                    cur_zee = rec["ZEE"]
                if cur_zee and "AA" in rec and "AE" in rec:
                    zee_counts[cur_zee] = zee_counts.get(cur_zee, 0) + 1
            _time.sleep(0.2)
        except Exception as ex:
            st.warning(f"Day {day_off}: {ex}")
    st.write("ZEE ID → počet zápasů (dnes + 3 dny):")
    for zee, cnt in sorted(zee_counts.items(), key=lambda x: -x[1]):
        st.write(f"  `{zee}` → {cnt} zápasů")

st.divider()
st.subheader("Playoff posily")
st.caption("Přidá 9 hráčů (3 per účastník) draftovaných před play-off MS 2026.")
if st.button("➕ Přidat playoff posily do kádru", type="primary"):
    try:
        from app.models.models import FootballPlayer, DraftSession, DraftPick
        from app.db import _PLAYOFF_PICKS
        from sqlalchemy import text as _sql

        db.rollback()  # vyčisti případný chybový stav session

        # Obnov sekvenci na správnou hodnotu (mohla se rozjet po částečném rollbacku)
        db.execute(_sql(
            "SELECT setval(pg_get_serial_sequence('football_players', 'id'), "
            "COALESCE((SELECT MAX(id) FROM football_players), 0) + 1, false)"
        ))
        db.commit()

        session = db.query(DraftSession).filter(
            DraftSession.game_id == game_id
        ).order_by(DraftSession.id.desc()).first()

        if not session:
            st.error("Nenalezena draft session.")
        else:
            participants_map = {p.name.lower(): p for p in participants}
            existing_picks = db.query(DraftPick).filter(DraftPick.session_id == session.id).all()
            max_pick = max((p.pick_number for p in existing_picks), default=0)
            max_round = max((p.round_number for p in existing_picks), default=0)
            existing_player_ids = {p.player_id for p in existing_picks}
            playoff_round = max_round + 1
            added, skipped = [], []

            for p_name, pl_name, country, position, club in _PLAYOFF_PICKS:
                participant = participants_map.get(p_name.lower())
                if not participant:
                    skipped.append(f"{pl_name} — účastník '{p_name}' nenalezen")
                    continue

                # Hledej jen podle jména (club se mohl uložit jinak)
                player = db.query(FootballPlayer).filter(
                    FootballPlayer.name == pl_name,
                ).first()
                if not player:
                    player = FootballPlayer(
                        name=pl_name, country=country, position=position, club=club
                    )
                    db.add(player)
                    db.flush()
                else:
                    # Sjednoť club a pozici na správné hodnoty
                    if player.club != club:
                        player.club = club
                    if player.position != position:
                        player.position = position

                if player.id in existing_player_ids:
                    skipped.append(f"{pl_name} — již v draftu")
                    continue

                max_pick += 1
                db.add(DraftPick(
                    session_id=session.id,
                    participant_id=participant.id,
                    player_id=player.id,
                    pick_number=max_pick,
                    round_number=playoff_round,
                ))
                existing_player_ids.add(player.id)
                added.append(f"{pl_name} → {participant.name}")

            db.commit()
            if added:
                st.success("Přidáno:\n" + "\n".join(f"- {x}" for x in added))
            if skipped:
                st.warning("Přeskočeno:\n" + "\n".join(f"- {x}" for x in skipped))
            if not added and not skipped:
                st.info("Nic k přidání.")
    except Exception as e:
        db.rollback()
        st.error(f"Chyba: {e}")
