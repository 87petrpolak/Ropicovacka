from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os

DB_PATH = os.environ.get("ROPICOVACKA_DB", "ropicovacka.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
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
    _migrate(engine)


def _migrate(eng):
    """Lightweight additive migrations for SQLite (no alembic)."""
    with eng.connect() as conn:
        existing = {row[1] for row in conn.execute(
            __import__('sqlalchemy').text("PRAGMA table_info(player_match_stats)")
        )}
        if "minutes_played" not in existing:
            conn.execute(__import__('sqlalchemy').text(
                "ALTER TABLE player_match_stats ADD COLUMN minutes_played INTEGER DEFAULT 0"
            ))
            conn.commit()
