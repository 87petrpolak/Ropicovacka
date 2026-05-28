"""Streamlit entrypoint — multi-page app via st.navigation."""
import streamlit as st
from app.db import init_db

init_db()

st.set_page_config(
    page_title="Ropičovačka 2026",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

pages = [
    st.Page("app/pages/home.py",             title="Domů",              icon="🏠"),
    st.Page("app/pages/participants.py",     title="Účastníci",         icon="👥"),
    st.Page("app/pages/players.py",          title="Hráči",             icon="⚽"),
    st.Page("app/pages/draft_room.py",       title="Draft",             icon="🎯"),
    st.Page("app/pages/squads.py",           title="Sestavy",           icon="🗂️"),
    st.Page("app/pages/lineup.py",           title="Nominace",          icon="📋"),
    st.Page("app/pages/match_import.py",     title="Import statistik",  icon="📥"),
    st.Page("app/pages/data_refresh.py",     title="Aktualizace dat",   icon="🔄"),
    st.Page("app/pages/leaderboard.py",      title="Pořadí",            icon="🏆"),
    st.Page("app/pages/rules.py",            title="Pravidla",          icon="📖"),
    st.Page("app/pages/admin.py",            title="Administrace",      icon="⚙️"),
]

pg = st.navigation(pages)
pg.run()
