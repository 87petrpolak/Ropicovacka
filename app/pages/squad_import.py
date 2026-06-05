"""Import soupisek týmů z Livesport.cz do databáze hráčů."""
import streamlit as st
from app.state import get_db
from app.models.models import FootballPlayer
from app.providers.livesport_provider import scrape_squad

st.title("Import soupisek z Livesport.cz")

db = get_db()

# Přednastavené týmy — přidej další dle potřeby
PRESET_TEAMS = {
    "Arsenal": ("arsenal", "hA1Zm19f"),
    "Manchester Utd": ("manchester-utd", "ppjDR086"),
    "Liverpool": ("liverpool", "lId4TMwf"),
    "Manchester City": ("manchester-city", "dea09qJB"),
    "Chelsea": ("chelsea", "h0IFzgMi"),
    "Tottenham": ("tottenham-hotspur", "CpNDWYUn"),
}

st.markdown(
    "Stáhne soupisku týmu ze stránky Livesport.cz a importuje hráče do databáze. "
    "Existující hráči (podle Flashscore ID) se přeskočí."
)

col1, col2 = st.columns([2, 1])

with col1:
    selected = st.multiselect(
        "Vyber týmy k importu",
        options=list(PRESET_TEAMS.keys()),
        default=["Arsenal", "Manchester Utd", "Liverpool"],
    )

with col2:
    st.markdown("**Vlastní tým**")
    custom_name = st.text_input("Název", placeholder="Real Madrid")
    custom_slug = st.text_input("Slug (z URL)", placeholder="real-madrid")
    custom_id = st.text_input("Flashscore ID", placeholder="lOWLa8rW")

if st.button("⬇️ Importovat soupisky", type="primary", use_container_width=True):
    teams_to_import = [(name, *PRESET_TEAMS[name]) for name in selected]
    if custom_name and custom_slug and custom_id:
        teams_to_import.append((custom_name, custom_slug, custom_id))

    if not teams_to_import:
        st.warning("Vyber alespoň jeden tým.")
    else:
        total_added = 0
        total_skipped = 0
        errors = []

        for team_name, slug, team_id in teams_to_import:
            with st.spinner(f"Stahuji soupisku {team_name}…"):
                try:
                    players = scrape_squad(slug, team_id, team_name)
                    added = 0
                    skipped = 0
                    for p in players:
                        existing = db.query(FootballPlayer).filter(
                            FootballPlayer.external_id == p.external_id
                        ).first() if p.external_id else None

                        if existing is None:
                            existing = db.query(FootballPlayer).filter(
                                FootballPlayer.name == p.name,
                                FootballPlayer.club == team_name,
                            ).first()

                        if existing is None:
                            db.add(FootballPlayer(
                                name=p.name,
                                country=p.country,
                                position=p.position,
                                club=p.club,
                                external_id=p.external_id,
                            ))
                            added += 1
                        else:
                            # Aktualizuj external_id pokud chybí
                            if not existing.external_id and p.external_id:
                                existing.external_id = p.external_id
                            skipped += 1

                    db.commit()
                    st.success(f"**{team_name}**: {added} přidáno, {skipped} přeskočeno")
                    total_added += added
                    total_skipped += skipped
                except Exception as e:
                    errors.append(f"{team_name}: {e}")
                    st.error(f"Chyba při importu {team_name}: {e}")

        if not errors:
            st.info(f"Celkem: **{total_added}** hráčů přidáno, **{total_skipped}** přeskočeno.")

st.divider()

# Přehled aktuálně importovaných hráčů
st.subheader("Hráči v databázi")

import pandas as pd
players_db = db.query(FootballPlayer).order_by(FootballPlayer.club, FootballPlayer.position, FootballPlayer.name).all()

if players_db:
    rows = [
        {
            "Jméno": p.name,
            "Klub": p.club or "—",
            "Post": p.position,
            "Flashscore ID": p.external_id or "—",
        }
        for p in players_db
    ]
    clubs = sorted(set(r["Klub"] for r in rows))
    selected_club = st.selectbox("Filtruj klub", ["Vše"] + clubs)
    if selected_club != "Vše":
        rows = [r for r in rows if r["Klub"] == selected_club]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"Celkem {len(players_db)} hráčů v databázi.")
else:
    st.info("Databáze hráčů je prázdná. Importuj soupisky výše.")
