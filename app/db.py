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

        conn.commit()
