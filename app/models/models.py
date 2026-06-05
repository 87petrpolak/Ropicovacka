from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Integer, String, Float, Boolean, DateTime, ForeignKey,
    UniqueConstraint, Enum as SAEnum, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base
import enum


class Position(str, enum.Enum):
    GK = "GK"
    DEF = "DEF"
    MID = "MID"
    FWD = "FWD"


class DraftDirection(str, enum.Enum):
    FORWARD = "forward"
    BACKWARD = "backward"


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    season: Mapped[str] = mapped_column(String(50), default="2026")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    participants: Mapped[list["Participant"]] = relationship("Participant", back_populates="game")
    matches: Mapped[list["Match"]] = relationship("Match", back_populates="game")
    draft_sessions: Mapped[list["DraftSession"]] = relationship("DraftSession", back_populates="game")
    rounds: Mapped[list["Round"]] = relationship("Round", back_populates="game")
    points_rules: Mapped[list["PointsRule"]] = relationship("PointsRule", back_populates="game")


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(200))
    draft_order: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    game: Mapped["Game"] = relationship("Game", back_populates="participants")
    draft_picks: Mapped[list["DraftPick"]] = relationship("DraftPick", back_populates="participant")
    lineups: Mapped[list["LineupNomination"]] = relationship("LineupNomination", back_populates="participant")

    __table_args__ = (UniqueConstraint("game_id", "name"),)


class FootballPlayer(Base):
    __tablename__ = "football_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[str] = mapped_column(SAEnum(Position), nullable=False)
    club: Mapped[Optional[str]] = mapped_column(String(200))
    external_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    draft_picks: Mapped[list["DraftPick"]] = relationship("DraftPick", back_populates="player")
    match_stats: Mapped[list["PlayerMatchStats"]] = relationship("PlayerMatchStats", back_populates="player")
    lineup_slots: Mapped[list["LineupSlot"]] = relationship("LineupSlot", back_populates="player")


class DraftSession(Base):
    __tablename__ = "draft_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    current_round: Mapped[int] = mapped_column(Integer, default=1)
    current_pick_index: Mapped[int] = mapped_column(Integer, default=0)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    game: Mapped["Game"] = relationship("Game", back_populates="draft_sessions")
    picks: Mapped[list["DraftPick"]] = relationship("DraftPick", back_populates="session", order_by="DraftPick.pick_number")


class DraftPick(Base):
    __tablename__ = "draft_picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("draft_sessions.id"), nullable=False)
    participant_id: Mapped[int] = mapped_column(Integer, ForeignKey("participants.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("football_players.id"), nullable=False)
    pick_number: Mapped[int] = mapped_column(Integer, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    picked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["DraftSession"] = relationship("DraftSession", back_populates="picks")
    participant: Mapped["Participant"] = relationship("Participant", back_populates="draft_picks")
    player: Mapped["FootballPlayer"] = relationship("FootballPlayer", back_populates="draft_picks")

    __table_args__ = (
        UniqueConstraint("session_id", "player_id"),
        UniqueConstraint("session_id", "pick_number"),
    )


class Round(Base):
    """Tournament round (group stage, R16, QF, SF, Final…)."""
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lineup_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)

    game: Mapped["Game"] = relationship("Game", back_populates="rounds")
    matches: Mapped[list["Match"]] = relationship("Match", back_populates="round")
    lineups: Mapped[list["LineupNomination"]] = relationship("LineupNomination", back_populates="round")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False)
    round_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("rounds.id"))
    home_team: Mapped[str] = mapped_column(String(100), nullable=False)
    away_team: Mapped[str] = mapped_column(String(100), nullable=False)
    home_score: Mapped[Optional[int]] = mapped_column(Integer)
    away_score: Mapped[Optional[int]] = mapped_column(Integer)
    played_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    is_finished: Mapped[bool] = mapped_column(Boolean, default=False)

    game: Mapped["Game"] = relationship("Game", back_populates="matches")
    round: Mapped[Optional["Round"]] = relationship("Round", back_populates="matches")
    player_stats: Mapped[list["PlayerMatchStats"]] = relationship("PlayerMatchStats", back_populates="match")


class PlayerMatchStats(Base):
    __tablename__ = "player_match_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(Integer, ForeignKey("matches.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("football_players.id"), nullable=False)
    goals: Mapped[int] = mapped_column(Integer, default=0)
    assists: Mapped[int] = mapped_column(Integer, default=0)
    played: Mapped[bool] = mapped_column(Boolean, default=False)
    minutes_played: Mapped[int] = mapped_column(Integer, default=0)
    team_won: Mapped[bool] = mapped_column(Boolean, default=False)
    clean_sheet: Mapped[bool] = mapped_column(Boolean, default=False)
    computed_points: Mapped[float] = mapped_column(Float, default=0.0)

    match: Mapped["Match"] = relationship("Match", back_populates="player_stats")
    player: Mapped["FootballPlayer"] = relationship("FootballPlayer", back_populates="match_stats")

    __table_args__ = (UniqueConstraint("match_id", "player_id"),)


class PointsRule(Base):
    __tablename__ = "points_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("games.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    points: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    game: Mapped["Game"] = relationship("Game", back_populates="points_rules")


class LineupNomination(Base):
    """Per-participant, per-round lineup (11 starting players)."""
    __tablename__ = "lineup_nominations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(Integer, ForeignKey("participants.id"), nullable=False)
    round_id: Mapped[int] = mapped_column(Integer, ForeignKey("rounds.id"), nullable=False)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_by_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    participant: Mapped["Participant"] = relationship("Participant", back_populates="lineups")
    round: Mapped["Round"] = relationship("Round", back_populates="lineups")
    slots: Mapped[list["LineupSlot"]] = relationship("LineupSlot", back_populates="nomination", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("participant_id", "round_id"),)


class LineupSlot(Base):
    """One player in a nominated lineup."""
    __tablename__ = "lineup_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nomination_id: Mapped[int] = mapped_column(Integer, ForeignKey("lineup_nominations.id"), nullable=False)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("football_players.id"), nullable=False)
    is_starter: Mapped[bool] = mapped_column(Boolean, default=True)

    nomination: Mapped["LineupNomination"] = relationship("LineupNomination", back_populates="slots")
    player: Mapped["FootballPlayer"] = relationship("FootballPlayer", back_populates="lineup_slots")

    __table_args__ = (UniqueConstraint("nomination_id", "player_id"),)


class DataRefreshLog(Base):
    """Audit log for every data refresh run."""
    __tablename__ = "data_refresh_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    records_added: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0)
    last_match_external_id: Mapped[Optional[str]] = mapped_column(String(100))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
