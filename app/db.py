from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os


def _get_db_url() -> str:
    # 1. Streamlit secrets (produkce)
    try:
        import streamlit as st
        url = st.secrets.get("DATABASE_URL", "")
        if url:
            # psycopg2 vyžaduje postgresql:// místo postgres://
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

engine = create_engine(
    _DB_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
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


def _migrate_sqlite(eng):
    """Additive migrations pro SQLite (lokální vývoj)."""
    with eng.connect() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(player_match_stats)"))}
        if "minutes_played" not in existing:
            conn.execute(text("ALTER TABLE player_match_stats ADD COLUMN minutes_played INTEGER DEFAULT 0"))
            conn.commit()
