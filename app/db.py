from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os
from urllib.parse import quote_plus

# Supabase Session Pooler (IPv4, eu-west-1)
_POOLER_HOST = "aws-0-eu-west-1.pooler.supabase.com"
_POOLER_PORT = 5432
_POOLER_USER = "postgres.owtxlwmluyaspwagtzzo"
_POOLER_DB   = "postgres"


def _get_db_url() -> str:
    # 1. Streamlit secrets (produkce)
    try:
        import streamlit as st
        # Heslo uložené zvlášť (bezpečnější, bez URL-encoding problémů)
        password = st.secrets.get("DB_PASSWORD", "")
        if password:
            return (
                f"postgresql://{_POOLER_USER}:{quote_plus(password)}"
                f"@{_POOLER_HOST}:{_POOLER_PORT}/{_POOLER_DB}"
            )
        # Fallback: celé DATABASE_URL
        url = st.secrets.get("DATABASE_URL", "")
        if url:
            return url.replace("postgres://", "postgresql://", 1)
    except Exception:
        pass

    # 2. Env proměnná (lokální vývoj s Postgres)
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url.replace("postgres://", "postgresql://", 1)

    # 3. SQLite fallback (lokální vývoj)
    db_path = os.environ.get("ROPICOVACKA_DB", "ropicovacka.db")
    return f"sqlite:///{db_path}"


_DB_URL = _get_db_url()
_is_sqlite = _DB_URL.startswith("sqlite")

if _is_sqlite:
    engine = create_engine(
        _DB_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    # Session Pooler (port 5432) podporuje persistent connections — rychlejší než NullPool
    engine = create_engine(
        _DB_URL,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=3,
        pool_recycle=300,
    )
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.models import models  # noqa: F401 — registers all models
    Base.metadata.create_all(engine)
    if _is_sqlite:
        _migrate_sqlite(engine)
    else:
        migrate_postgres(engine)


def _migrate_sqlite(eng):
    """Additive migrations pro SQLite (lokální vývoj)."""
    with eng.connect() as conn:
        stats_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(player_match_stats)"))}
        if "minutes_played" not in stats_cols:
            conn.execute(text("ALTER TABLE player_match_stats ADD COLUMN minutes_played INTEGER DEFAULT 0"))
            conn.commit()

        players_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(football_players)"))}
        if "position" in players_cols and "pos" not in players_cols:
            conn.execute(text("ALTER TABLE football_players RENAME COLUMN position TO pos"))
            conn.commit()


def migrate_postgres(eng):
    """Additive migrations pro PostgreSQL (Supabase)."""

    with eng.connect() as conn:
        # lineup_nominations: captain + substitute
        ln_cols = {row[0] for row in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='lineup_nominations'"
        ))}
        for col, ddl in [
            ("captain_player_id",    "ALTER TABLE lineup_nominations ADD COLUMN captain_player_id INTEGER REFERENCES football_players(id)"),
            ("substitute_player_id", "ALTER TABLE lineup_nominations ADD COLUMN substitute_player_id INTEGER REFERENCES football_players(id)"),
        ]:
            if col not in ln_cols:
                conn.execute(text(ddl))

        # lineup_change_logs: captain_name, substitute_name
        cl_cols = {row[0] for row in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='lineup_change_logs'"
        ))}
        for col, ddl in [
            ("captain_name",    "ALTER TABLE lineup_change_logs ADD COLUMN captain_name TEXT"),
            ("substitute_name", "ALTER TABLE lineup_change_logs ADD COLUMN substitute_name TEXT"),
        ]:
            if col not in cl_cols:
                conn.execute(text(ddl))

        # games: actual_winner, actual_top_scorer_id, predictions_locked
        g_cols = {row[0] for row in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='games'"
        ))}
        for col, ddl in [
            ("actual_winner",        "ALTER TABLE games ADD COLUMN actual_winner VARCHAR(100)"),
            ("actual_top_scorer_id", "ALTER TABLE games ADD COLUMN actual_top_scorer_id INTEGER REFERENCES football_players(id)"),
            ("predictions_locked",   "ALTER TABLE games ADD COLUMN predictions_locked BOOLEAN DEFAULT FALSE"),
        ]:
            if col not in g_cols:
                conn.execute(text(ddl))

        # app_cache — vytvoří se přes create_all, ale pro jistotu
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS app_cache (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))

        # Jednorázový reimport stats po opravě parsování penalty gólů
        stats_reimport = conn.execute(text(
            "SELECT value FROM app_cache WHERE key = 'stats_reimport_v2'"
        )).fetchone()
        if stats_reimport is None:
            conn.execute(text("DELETE FROM player_match_stats"))
            conn.execute(text(
                "INSERT INTO app_cache (key, value, updated_at) VALUES "
                "('stats_reimport_v2', 'done', NOW()) "
                "ON CONFLICT (key) DO UPDATE SET value='done', updated_at=NOW()"
            ))

        # Oprav hodnoty bodovacích pravidel na správné hodnoty
        conn.execute(text("""
            UPDATE points_rules SET points = CASE name
                WHEN 'goal'                   THEN 30
                WHEN 'assist'                 THEN 25
                WHEN 'mid_team_win'           THEN 15
                WHEN 'def_team_win'           THEN 15
                WHEN 'goalkeeper_clean_sheet' THEN 30
                WHEN 'defender_clean_sheet'   THEN 15
                ELSE points
            END
            WHERE name IN ('goal','assist','mid_team_win','def_team_win',
                           'goalkeeper_clean_sheet','defender_clean_sheet')
        """))

        conn.commit()

    # Přepočítej computed_points pro všechny existující statistiky se správnými pravidly
    _recompute_all_points(eng)

    # Playoff posily — přidány před 1/16-finále MS 2026
    _add_playoff_players(eng)

    # Oprava stats po chybném re-importu
    _fix_playoff_stats(eng)


def _recompute_all_points(eng):
    """Přepočítá computed_points pro všechny PlayerMatchStats podle aktuálních pravidel."""
    try:
        from app.models.models import PlayerMatchStats, FootballPlayer, PointsRule, Game, Position
        from app.services.scoring import compute_points, rules_from_db
        db = SessionLocal()
        try:
            game = db.query(Game).filter(Game.is_active == True).first()
            if not game:
                return
            db_rules = db.query(PointsRule).filter(PointsRule.game_id == game.id).all()
            scoring_rules = rules_from_db(db_rules)
            stats_list = db.query(PlayerMatchStats).all()
            for stats in stats_list:
                player = db.get(FootballPlayer, stats.player_id)
                if player:
                    bd = compute_points(stats, Position(player.position), scoring_rules)
                    stats.computed_points = bd.total
            db.commit()
        finally:
            db.close()
    except Exception:
        pass


# (participant_name, player_name, country, position, club)
# club = česky název národního týmu — musí odpovídat match.home_team / away_team
_PLAYOFF_PICKS = [
    ("Péťa",   "Doué Désiré",        "", "FWD", "Francie"),
    ("Péťa",   "Manzambi Johan",      "", "MID", "Švýcarsko"),
    ("Péťa",   "Medina Facundo",      "", "DEF", "Argentina"),
    ("Chajda", "Ronaldo Cristiano",   "", "FWD", "Portugalsko"),
    ("Chajda", "Martínez Lisandro",   "", "DEF", "Argentina"),
    ("Chajda", "Rabiot Adrien",       "", "MID", "Francie"),
    ("Saša",   "Salah Mohamed",       "", "FWD", "Egypt"),
    ("Saša",   "Mac Allister Alexis", "", "MID", "Argentina"),
    ("Saša",   "Romero Cristian",     "", "DEF", "Argentina"),
]


def _fix_playoff_stats(eng):
    """
    Oprava stats ve třech oddělených krocích:
    Krok A (jen DB): nastav Romero external_id aby ho budoucí importy našly.
    Krok B (Flashscore): re-fetchni stats pro Argentina vs Egypt.
    Krok C (odvozeno ze skóre): oprav false góly hráčů v zápasech kde jejich tým neskóroval.
    """
    from app.models.models import AppCache, FootballPlayer, PlayerMatchStats, Game, Match
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.is_active == True).first()
        if not game:
            return

        # === Krok A: nastav Romero external_id (jen DB, nikdy neselhává) ===
        if not db.get(AppCache, "playoff_fix_ext_id_v1"):
            romero = db.query(FootballPlayer).filter(
                FootballPlayer.name == "Romero Cristian"
            ).first()
            if romero and not romero.external_id:
                romero.external_id = "jBZTWXMn"
            db.add(AppCache(
                key="playoff_fix_ext_id_v1",
                value="done",
                updated_at=__import__("datetime").datetime.utcnow(),
            ))
            db.commit()

        # === Krok B: re-fetchni stats ze Flashscore ===
        # v2: opravený parser (penalty rozstřel se nepočítá), přidán Švýcarsko vs Kolumbie
        if not db.get(AppCache, "playoff_fix_stats_v2"):
            from app.providers.livesport_provider import LivesportProvider
            from app.services.data_refresh import _upsert_stats, _recompute_match_points
            from app.providers.base import RefreshResult

            provider = LivesportProvider()
            errors = []

            for label, pairs in [
                ("Argentina vs Egypt",    [("Argentina", "Egypt"), ("Egypt", "Argentina")]),
                ("Švýcarsko vs Kolumbie", [("Švýcarsko", "Kolumbie"), ("Kolumbie", "Švýcarsko")]),
            ]:
                for home, away in pairs:
                    m = db.query(Match).filter(
                        Match.home_team == home, Match.away_team == away,
                        Match.game_id == game.id, Match.external_id.isnot(None),
                    ).first()
                    if m:
                        try:
                            r = RefreshResult()
                            for sd in provider.fetch_player_stats(m.external_id):
                                _upsert_stats(db, sd, m, r)
                            _recompute_match_points(db, m, game.id)
                            db.flush()
                            print(f"[playoff_fix] {label}: +{r.stats_added} ↺{r.stats_updated}")
                        except Exception as e:
                            errors.append(f"{label}: {e}")
                        break
                else:
                    print(f"[playoff_fix] {label}: nenalezen v DB nebo chybí external_id")

            if not errors:
                db.add(AppCache(
                    key="playoff_fix_stats_v2",
                    value="done",
                    updated_at=__import__("datetime").datetime.utcnow(),
                ))
            db.commit()
            if errors:
                print(f"[playoff_fix] Chyby Krok B: {errors}")

        # === Krok C: oprav false góly — odvozeno ze skóre zápasu ===
        # Hledáme hráče jejichž tým v daném zápase neskóroval, ale player má goals > 0.
        # To je fyzicky nemožné — gól musí být false positive z parsování.
        # Pokud zápas má external_id, zkusíme Flashscore; jinak nastavíme 0 ze skóre.
        if not db.get(AppCache, "playoff_fix_diaz_v2"):
            from app.services.data_refresh import _recompute_match_points

            fixed_match_ids: set[int] = set()

            all_stats_with_goals = db.query(PlayerMatchStats).filter(
                PlayerMatchStats.goals > 0
            ).all()

            for stat in all_stats_with_goals:
                player = db.get(FootballPlayer, stat.player_id)
                match = db.get(Match, stat.match_id)
                if not player or not match or not player.club:
                    continue

                club = player.club
                if match.home_team == club:
                    club_goals = match.home_score or 0
                elif match.away_team == club:
                    club_goals = match.away_score or 0
                else:
                    continue  # hráčův klub nehrál v tomto zápase

                if club_goals > 0:
                    continue  # tým skóroval, gól může být validní

                # Tým neskóroval 0 — gól je false positive
                corrected = False
                if match.external_id:
                    try:
                        from app.providers.livesport_provider import LivesportProvider
                        prov = LivesportProvider()
                        for sd in prov.fetch_player_stats(match.external_id):
                            pid_match = (sd.player_external_id and
                                         sd.player_external_id == player.external_id)
                            name_match = sd.player_name == player.name
                            if pid_match or name_match:
                                stat.goals = sd.goals
                                stat.assists = sd.assists
                                corrected = True
                                break
                        if not corrected:
                            stat.goals = 0
                            corrected = True
                    except Exception as e:
                        print(f"[playoff_fix C] Flashscore fetch selhal ({player.name}): {e}")
                        stat.goals = 0
                        corrected = True
                else:
                    stat.goals = 0
                    corrected = True

                if corrected:
                    fixed_match_ids.add(match.id)
                    print(f"[playoff_fix C] {player.name}: goals opraveny v {match.home_team} vs {match.away_team}")

            for mid in fixed_match_ids:
                m = db.get(Match, mid)
                if m:
                    _recompute_match_points(db, m, game.id)

            db.add(AppCache(
                key="playoff_fix_diaz_v2",
                value="done",
                updated_at=__import__("datetime").datetime.utcnow(),
            ))
            db.commit()

    except Exception as e:
        db.rollback()
        print(f"[playoff_fix] Kritická chyba: {e}")
    finally:
        db.close()


def _add_playoff_players(eng):
    """Přidá playoff posily (3 hráči na účastníka) do draft session před play-off MS 2026."""
    from app.models.models import (
        AppCache, FootballPlayer, Game, Participant, DraftSession, DraftPick
    )
    db = SessionLocal()
    try:
        # Idempotentní — spustí se jen jednou
        if db.get(AppCache, "playoff_draft_v2"):
            return

        game = db.query(Game).filter(Game.is_active == True).first()
        if not game:
            return

        participants = {
            p.name: p
            for p in db.query(Participant).filter(Participant.game_id == game.id).all()
        }
        session = (
            db.query(DraftSession)
            .filter(DraftSession.game_id == game.id)
            .order_by(DraftSession.id.desc())
            .first()
        )
        if not session:
            return

        existing_picks = db.query(DraftPick).filter(DraftPick.session_id == session.id).all()
        max_pick = max((p.pick_number for p in existing_picks), default=0)
        max_round = max((p.round_number for p in existing_picks), default=0)
        existing_player_ids = {p.player_id for p in existing_picks}

        pick_num = max_pick
        playoff_round = max_round + 1
        for p_name, pl_name, country, position, club in _PLAYOFF_PICKS:
            participant = next(
                (p for name, p in participants.items() if name.lower() == p_name.lower()),
                None,
            )
            if not participant:
                continue

            player = db.query(FootballPlayer).filter(
                FootballPlayer.name == pl_name,
                FootballPlayer.club == club,
            ).first()
            if not player:
                player = FootballPlayer(
                    name=pl_name,
                    country=country,
                    position=position,
                    club=club,
                )
                db.add(player)
                db.flush()

            if player.id in existing_player_ids:
                continue

            pick_num += 1
            db.add(DraftPick(
                session_id=session.id,
                participant_id=participant.id,
                player_id=player.id,
                pick_number=pick_num,
                round_number=playoff_round,
            ))
            existing_player_ids.add(player.id)

        cache_row = AppCache(
            key="playoff_draft_v2",
            value="done",
            updated_at=__import__("datetime").datetime.utcnow(),
        )
        db.add(cache_row)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[playoff_migration] CHYBA: {e}")
    finally:
        db.close()
