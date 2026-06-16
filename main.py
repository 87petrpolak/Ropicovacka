"""Streamlit entrypoint — multi-page app via st.navigation."""
import streamlit as st
from app.db import init_db


@st.cache_resource
def _init_db_once():
    init_db()


_init_db_once()

st.set_page_config(
    page_title="Ropičovačka 2026",
    page_icon="⚽",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Responzivní CSS pro mobil
st.markdown("""
<style>
/* Sloupce se skládají pod sebe na mobilech */
@media (max-width: 640px) {
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
    [data-testid="column"] {
        width: 100% !important;
        flex: none !important;
        min-width: 100% !important;
    }
}
/* Tabulky jsou vodorovně scrollovatelné */
[data-testid="stDataFrame"] { overflow-x: auto; }
</style>
""", unsafe_allow_html=True)

pages = [
    st.Page("app/pages/dashboard.py",        title="Dashboard",         icon="💰"),
    st.Page("app/pages/home.py",             title="Domů",              icon="🏠"),
    st.Page("app/pages/participants.py",     title="Účastníci",         icon="👥"),
    st.Page("app/pages/players.py",          title="Hráči",             icon="⚽"),
    st.Page("app/pages/squad_import.py",     title="Import soupisek",   icon="📋"),
    st.Page("app/pages/draft_room.py",       title="Draft",             icon="🎯"),
    st.Page("app/pages/squads.py",           title="Sestavy",           icon="🗂️"),
    st.Page("app/pages/lineup.py",           title="Nominace",          icon="📋"),
    st.Page("app/pages/predictions.py",      title="Tipy na turnaj",    icon="🎯"),
    st.Page("app/pages/match_calendar.py",   title="Kalendář zápasů",   icon="📅"),
    st.Page("app/pages/match_import.py",     title="Import statistik",  icon="📥"),
    st.Page("app/pages/data_refresh.py",     title="Aktualizace dat",   icon="🔄"),
    st.Page("app/pages/leaderboard.py",      title="Pořadí",            icon="🏆"),
    st.Page("app/pages/rules.py",            title="Pravidla",          icon="📖"),
    st.Page("app/pages/admin.py",            title="Administrace",      icon="⚙️"),
]

pg = st.navigation(pages)
pg.run()
