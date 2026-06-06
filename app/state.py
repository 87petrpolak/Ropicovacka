"""Shared Streamlit session-state helpers."""
from __future__ import annotations
import streamlit as st
from sqlalchemy.orm import Session
from app.db import SessionLocal


def get_db() -> Session:
    if "db" not in st.session_state:
        st.session_state["db"] = SessionLocal()
    return st.session_state["db"]


def get_active_game_id() -> int | None:
    return st.session_state.get("active_game_id")


def set_active_game_id(game_id: int):
    st.session_state["active_game_id"] = game_id


def get_active_draft_session_id() -> int | None:
    return st.session_state.get("active_draft_session_id")


def set_active_draft_session_id(session_id: int):
    st.session_state["active_draft_session_id"] = session_id


def is_admin() -> bool:
    return st.session_state.get("is_admin", False)


def require_active_game() -> int | None:
    gid = get_active_game_id()
    if gid is None:
        # Automaticky vyber aktivní hru
        from app.models.models import Game
        db = get_db()
        game = db.query(Game).filter(Game.is_active == True).order_by(Game.created_at.desc()).first()
        if game is None:
            game = db.query(Game).order_by(Game.created_at.desc()).first()
        if game:
            set_active_game_id(game.id)
            return game.id
        st.warning("Není vybrána žádná aktivní hra. Přejdi na **Domů** a vytvoř nebo vyber hru.")
    return gid
