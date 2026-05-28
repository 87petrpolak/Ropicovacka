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
        st.warning("Není vybrána žádná aktivní hra. Přejdi na **Domů** a vytvoř nebo vyber hru.")
    return gid
