import streamlit as st
from app.state import get_db, set_active_game_id, get_active_game_id
from app.models.models import Game
from app.db import init_db

st.title("Ropičovačka 2026")
st.caption("Fantasy draft hra — Mistrovství světa ve fotbale 2026")

db = get_db()

# ------------------------------------------------------------------
# Výběr aktivní hry
# ------------------------------------------------------------------
games = db.query(Game).order_by(Game.created_at.desc()).all()

if games:
    game_names = {g.id: f"{g.name} ({g.season})" for g in games}
    current_id = get_active_game_id()
    default_idx = 0
    if current_id and current_id in game_names:
        default_idx = list(game_names.keys()).index(current_id)

    selected_id = st.selectbox(
        "Aktivní hra",
        options=list(game_names.keys()),
        format_func=lambda gid: game_names[gid],
        index=default_idx,
    )
    set_active_game_id(selected_id)

    game = db.get(Game, selected_id)
    cols = st.columns(3)
    cols[0].metric("Účastníci", len(game.participants))
    cols[1].metric("Zápasy", len(game.matches))
    cols[2].metric("Kola", len(game.rounds))
else:
    st.info("Žádná hra ještě neexistuje. Vytvoř první níže.")

st.divider()

# ------------------------------------------------------------------
# Vytvoření nové hry
# ------------------------------------------------------------------
with st.expander("➕ Vytvořit novou hru", expanded=not bool(games)):
    with st.form("new_game"):
        name = st.text_input("Název hry", placeholder="MS 2026 — Přátelský draft")
        season = st.text_input("Sezóna", value="2026")
        submitted = st.form_submit_button("Vytvořit hru")
        if submitted:
            if not name.strip():
                st.error("Název hry je povinný.")
            else:
                g = Game(name=name.strip(), season=season.strip())
                db.add(g)
                db.commit()
                db.refresh(g)
                set_active_game_id(g.id)
                st.success(f"Hra '{g.name}' byla vytvořena!")
                st.rerun()

st.divider()
st.markdown("""
### Jak začít
1. **Vytvoř hru** výše nebo vyber existující.
2. Přejdi na **Účastníci** a přidej hráče.
3. Přejdi na **Hráči** a importuj seznam fotbalistů (CSV).
4. Otevři **Draft** a proveď výběr hráčů.
5. Před každým kolem přejdi na **Nominace** a vyber svých 11.
6. Importuj výsledky přes **Import statistik** nebo **Aktualizace dat**.
7. Sleduj **Pořadí** a zjisti, kdo vede.
""")
