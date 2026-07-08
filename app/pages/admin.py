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
        # Detail pro Portugalsko
        pt_matches = [m for m in raw if "Portugalsko" in (m.get("home",""), m.get("away",""))]
        st.write(f"**Všechny Portugalsko zápasy ({len(pt_matches)}):**")
        for m in pt_matches:
            st.write(f"  {m.get('date_str','')} {m.get('home','')} vs {m.get('away','')} (status={m.get('status','')})")
    except Exception as e:
        st.error(f"Chyba: {e}")

if st.button("🔍 Všechna pole WC zápasů (den 0)"):
    import requests
    WC_ID = "lvUBR5F8"
    _BASE = "https://1.flashscore.ninja/1/x/feed"
    _HEADERS = {"x-fsign": "SW9D1eZo", "Referer": "https://www.livesport.cz/", "User-Agent": "Mozilla/5.0"}
    r = requests.get(f"{_BASE}/f_1_0_2_cs_1", headers=_HEADERS, timeout=10)
    raw = r.text
    in_wc = False
    ctx: dict[str, str] = {}
    for block in raw.split("~"):
        rec: dict[str, str] = {}
        for pair in block.split("¬"):
            if "÷" in pair:
                k, _, v = pair.partition("÷")
                rec[k] = v
        if "ZEE" in rec:
            in_wc = rec["ZEE"] == WC_ID
            ctx = {k: v for k, v in rec.items() if k != "ZEE"}
            continue
        if in_wc and "AA" in rec and "AE" in rec:
            st.write(f"**{rec.get('AE','')} vs {rec.get('AF','')}**")
            all_fields = {**ctx, **rec}
            st.json({k: v for k, v in all_fields.items() if k not in ("AA", "AE", "AF", "AD")})

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
st.subheader("Oprava stats (Romero + Díaz Luis)")
from app.models.models import AppCache as _AC
ext_done = db.get(_AC, "playoff_fix_ext_id_v1")
stats_done = db.get(_AC, "playoff_fix_stats_v1")
diaz_done = db.get(_AC, "playoff_fix_diaz_v1")
all_fixed = bool(ext_done and stats_done and diaz_done)
if all_fixed:
    st.success("✅ Romero external_id ✅ Argentina vs Egypt stats ✅ Díaz Luis false gól opraven")
else:
    st.write(f"A (Romero ext_id): {'✅' if ext_done else '❌'}  "
             f"B (ARG vs EGY stats): {'✅' if stats_done else '❌'}  "
             f"C (Díaz Luis false gól): {'✅' if diaz_done else '❌'}")
if not all_fixed:
    if st.button("▶️ Spustit opravu teď", type="primary"):
        from app.models.models import FootballPlayer as _FP, Match as _M, AppCache as _AC2, PlayerMatchStats as _PMS
        from app.providers.livesport_provider import LivesportProvider as _LSP
        from app.services.data_refresh import _upsert_stats, _recompute_match_points
        from app.providers.base import RefreshResult as _RR
        from datetime import datetime as _dt

        # Krok A: sluč duplikátního "Romero C." s "Romero Cristian"
        try:
            romero = db.query(_FP).filter(_FP.name == "Romero Cristian").first()
            duplicate = db.query(_FP).filter(_FP.external_id == "jBZTWXMn").first()

            if not romero:
                st.error("Romero Cristian nenalezen v DB!")
            elif duplicate and duplicate.id != romero.id:
                st.write(f"Duplikát nalezen: '{duplicate.name}' (id={duplicate.id}) → přesouvám stats na Romero Cristian (id={romero.id})")
                dup_stats = db.query(_PMS).filter(_PMS.player_id == duplicate.id).all()
                for s in dup_stats:
                    exists = db.query(_PMS).filter(
                        _PMS.player_id == romero.id,
                        _PMS.match_id == s.match_id,
                    ).first()
                    if not exists:
                        s.player_id = romero.id
                    else:
                        db.delete(s)
                db.flush()
                db.delete(duplicate)
                db.flush()
                romero.external_id = "jBZTWXMn"
                st.write("→ Duplikát smazán, external_id přiřazen Romerovi")
            elif not romero.external_id:
                romero.external_id = "jBZTWXMn"
                st.write("→ external_id nastaven")
            else:
                st.write(f"Romero external_id již: {romero.external_id}")

            if not db.get(_AC2, "playoff_fix_ext_id_v1"):
                db.add(_AC2(key="playoff_fix_ext_id_v1", value="done", updated_at=_dt.utcnow()))
            db.commit()
            st.success("Krok A OK")
        except Exception as e:
            db.rollback()
            st.error(f"Krok A selhal: {e}")

        # Krok B: fetch stats ze Flashscore (Argentina vs Egypt)
        if not db.get(_AC2, "playoff_fix_stats_v1"):
            provider = _LSP()
            b_ok = True
            for home, away in [("Argentina", "Egypt"), ("Egypt", "Argentina")]:
                m = db.query(_M).filter(
                    _M.home_team == home, _M.away_team == away,
                    _M.game_id == game_id, _M.external_id.isnot(None),
                ).first()
                if m:
                    st.write(f"**Argentina vs Egypt**: match_id={m.external_id}")
                    try:
                        stats_data = provider.fetch_player_stats(m.external_id)
                        st.write(f"  → Flashscore vrátil {len(stats_data)} hráčů")
                        r = _RR()
                        for sd in stats_data:
                            _upsert_stats(db, sd, m, r)
                        _recompute_match_points(db, m, game_id)
                        db.commit()
                        st.success(f"  ✅ +{r.stats_added} přidáno, ↺{r.stats_updated} aktualizováno")
                    except Exception as e:
                        db.rollback()
                        st.error(f"  ❌ {e}")
                        b_ok = False
                    break
            else:
                st.warning("Argentina vs Egypt: zápas nenalezen v DB (chybí external_id)")
                b_ok = False
            if b_ok:
                try:
                    db.add(_AC2(key="playoff_fix_stats_v1", value="done", updated_at=_dt.utcnow()))
                    db.commit()
                except Exception:
                    db.rollback()
        else:
            st.write("Krok B: již hotovo")

        # Krok C: oprav false góly (Díaz Luis + kdokoli else kde tým neskóroval)
        if not db.get(_AC2, "playoff_fix_diaz_v1"):
            st.write("**Krok C**: hledám false góly...")
            fixed_match_ids: set[int] = set()
            all_stats_goals = db.query(_PMS).filter(_PMS.goals > 0).all()
            for stat in all_stats_goals:
                player = db.get(_FP, stat.player_id)
                match = db.get(_M, stat.match_id)
                if not player or not match or not player.club:
                    continue
                club = player.club
                if match.home_team == club:
                    club_goals = match.home_score or 0
                elif match.away_team == club:
                    club_goals = match.away_score or 0
                else:
                    continue
                if club_goals > 0:
                    continue
                # Tým neskóroval — oprav gól
                old_goals = stat.goals
                corrected = False
                if match.external_id:
                    try:
                        prov_c = _LSP()
                        fs_data = prov_c.fetch_player_stats(match.external_id)
                        for sd in fs_data:
                            if (sd.player_external_id and sd.player_external_id == player.external_id) or \
                               sd.player_name == player.name:
                                stat.goals = sd.goals
                                stat.assists = sd.assists
                                corrected = True
                                break
                        if not corrected:
                            stat.goals = 0
                            corrected = True
                    except Exception as e_c:
                        st.warning(f"Flashscore fetch selhal pro {player.name}: {e_c} → nastavuji 0")
                        stat.goals = 0
                        corrected = True
                else:
                    stat.goals = 0
                    corrected = True
                if corrected:
                    fixed_match_ids.add(match.id)
                    st.write(f"  {player.name} ({club}): goals {old_goals}→{stat.goals} "
                             f"v {match.home_team} {match.home_score}-{match.away_score} {match.away_team}"
                             f" (ext_id: {match.external_id or 'chybí'})")
            for mid in fixed_match_ids:
                m = db.get(_M, mid)
                if m:
                    _recompute_match_points(db, m, game_id)
            try:
                db.add(_AC2(key="playoff_fix_diaz_v1", value="done", updated_at=_dt.utcnow()))
                db.commit()
                st.success(f"✅ Krok C hotov ({len(fixed_match_ids)} zápasů opraveno)")
            except Exception as e_c2:
                db.rollback()
                st.error(f"Krok C selhal při commitu: {e_c2}")
        else:
            st.write("Krok C: již hotovo")

        st.rerun()

st.divider()
st.subheader("Debug & import stats konkrétního zápasu")
st.caption(
    "Načte hráče ze Flashscore pro vybraný zápas a ukáže, kdo byl nalezen v draftu. "
    "INSERT-only: existující záznamy nepřepisuje."
)

try:
    from app.models.models import Match as _Match, FootballPlayer as _FP, PlayerMatchStats as _PMS
    finished_matches = (
        db.query(_Match)
        .filter(_Match.game_id == game_id, _Match.is_finished == True, _Match.external_id.isnot(None))
        .order_by(_Match.played_at)
        .all()
    )
    if finished_matches:
        match_opts = {f"{m.home_team or '?'} vs {m.away_team or '?'} ({m.external_id})": m for m in finished_matches}
        sel_match_label = st.selectbox("Zápas", list(match_opts.keys()), key="debug_match_sel")
        sel_match = match_opts[sel_match_label]

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            do_debug = st.button("🔍 Zobrazit hráče z Flashscore", key="debug_match_btn")
        with col_b:
            do_import = st.button("➕ Doplnit chybějící stats", key="import_match_btn", type="primary")
        with col_c:
            do_overwrite = st.button("🔧 Přepsat stats (opravit chyby)", key="overwrite_match_btn", type="secondary")

        if do_debug or do_import or do_overwrite:
            try:
                from app.providers.livesport_provider import LivesportProvider
                provider = LivesportProvider()
                stats_data = provider.fetch_player_stats(sel_match.external_id)
                st.write(f"Flashscore vrátil **{len(stats_data)} hráčů**:")
                added_count = 0
                for sd in stats_data:
                    pl = None
                    if sd.player_external_id:
                        pl = db.query(_FP).filter(_FP.external_id == sd.player_external_id).first()
                    if pl is None:
                        pl = db.query(_FP).filter(_FP.name == sd.player_name).first()

                    already = pl and db.query(_PMS).filter(
                        _PMS.match_id == sel_match.id, _PMS.player_id == pl.id
                    ).first()

                    if pl:
                        status = "✅ v draftu"
                        if already:
                            status += " (stats již existují)"
                        else:
                            status += " — CHYBÍ stats"
                    else:
                        status = "⚪ není v draftu"

                    g = sd.goals or 0
                    a = sd.assists or 0
                    w = "✓" if sd.team_won else "✗"
                    cs = "✓" if sd.clean_sheet else "✗"
                    st.write(
                        f"  **{sd.player_name}** — G:{g} A:{a} výhra:{w} čisté:{cs} | {status}"
                    )

                    if do_import and pl and not already:
                        db.add(_PMS(
                            match_id=sel_match.id,
                            player_id=pl.id,
                            goals=sd.goals,
                            assists=sd.assists,
                            played=sd.played,
                            minutes_played=sd.minutes_played,
                            team_won=sd.team_won,
                            clean_sheet=sd.clean_sheet,
                        ))
                        added_count += 1
                    elif do_overwrite and pl:
                        if already:
                            already.goals = sd.goals
                            already.assists = sd.assists
                            already.played = sd.played
                            already.minutes_played = sd.minutes_played
                            already.team_won = sd.team_won
                            already.clean_sheet = sd.clean_sheet
                        else:
                            db.add(_PMS(
                                match_id=sel_match.id,
                                player_id=pl.id,
                                goals=sd.goals,
                                assists=sd.assists,
                                played=sd.played,
                                minutes_played=sd.minutes_played,
                                team_won=sd.team_won,
                                clean_sheet=sd.clean_sheet,
                            ))
                        added_count += 1

                if do_import or do_overwrite:
                    if added_count:
                        from app.services.data_refresh import _recompute_match_points
                        _recompute_match_points(db, sel_match, game_id)
                        db.commit()
                        action = "Přepsáno" if do_overwrite else "Přidáno"
                        st.success(f"{action} {added_count} stats.")
                    else:
                        st.info("Nic k doplnění." if do_import else "Nic ke změně.")
            except Exception as e_d:
                db.rollback()
                st.error(f"Chyba: {e_d}")
    else:
        st.info("Žádné odehrané zápasy s external_id v DB.")
except Exception as e_outer:
    st.error(f"Chyba při načítání zápasů: {e_outer}")

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
