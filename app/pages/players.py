import io
import streamlit as st
import pandas as pd
from app.state import get_db
from app.models.models import FootballPlayer, Position
from app.providers.csv_provider import CsvFootballDataProvider

st.title("Hráči")

db = get_db()

# ------------------------------------------------------------------
# Filtry
# ------------------------------------------------------------------
all_players = db.query(FootballPlayer).order_by(
    FootballPlayer.country, FootballPlayer.name
).all()

col1, col2, col3 = st.columns(3)
with col1:
    countries = sorted({p.country for p in all_players})
    sel_country = st.multiselect("Reprezentace", countries)
with col2:
    sel_pos = st.multiselect("Pozice", [p.value for p in Position])
with col3:
    search = st.text_input("Hledat podle jména")

filtered = all_players
if sel_country:
    filtered = [p for p in filtered if p.country in sel_country]
if sel_pos:
    filtered = [p for p in filtered if p.position in sel_pos]
if search:
    filtered = [p for p in filtered if search.lower() in p.name.lower()]

st.caption(f"Zobrazeno {len(filtered)} z {len(all_players)} hráčů")

if filtered:
    rows = [
        {
            "ID": p.id,
            "Jméno": p.name,
            "Reprezentace": p.country,
            "Pozice": p.position,
            "Klub": p.club or "—",
            "Externí ID": p.external_id or "—",
        }
        for p in filtered
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("Žádní hráči neodpovídají filtrům.")

st.divider()

# ------------------------------------------------------------------
# Přidat hráče ručně
# ------------------------------------------------------------------
with st.expander("➕ Přidat hráče ručně"):
    with st.form("add_player"):
        p_name = st.text_input("Jméno")
        p_country = st.text_input("Reprezentace")
        p_pos = st.selectbox("Pozice", [p.value for p in Position])
        p_club = st.text_input("Klub (volitelné)")
        p_ext = st.text_input("Externí ID (volitelné)")
        submitted = st.form_submit_button("Přidat hráče")
        if submitted:
            if not p_name.strip() or not p_country.strip():
                st.error("Jméno a reprezentace jsou povinné.")
            else:
                db.add(FootballPlayer(
                    name=p_name.strip(),
                    country=p_country.strip(),
                    position=p_pos,
                    club=p_club.strip() or None,
                    external_id=p_ext.strip() or None,
                ))
                db.commit()
                st.success(f"Hráč {p_name} byl přidán.")
                st.rerun()

# ------------------------------------------------------------------
# Import z CSV
# ------------------------------------------------------------------
with st.expander("📥 Importovat hráče z CSV"):
    st.markdown("""
**Povinné sloupce:** `name`, `country`, `position`
**Volitelné sloupce:** `club`, `external_id`
**Hodnoty pozice:** `GK`, `DEF`, `MID`, `FWD`
""")
    uploaded = st.file_uploader("Nahraj soubor players.csv", type="csv", key="players_csv")
    if uploaded:
        provider = CsvFootballDataProvider(
            players_csv=io.StringIO(uploaded.read().decode())
        )
        players_data = provider.fetch_players()
        st.write(f"Nalezeno {len(players_data)} řádků v CSV.")

        if st.button("Importovat hráče"):
            added = 0
            skipped = 0
            errors = []
            for pd_row in players_data:
                try:
                    existing = None
                    if pd_row.external_id:
                        existing = db.query(FootballPlayer).filter(
                            FootballPlayer.external_id == pd_row.external_id
                        ).first()
                    if existing is None:
                        existing = db.query(FootballPlayer).filter(
                            FootballPlayer.name == pd_row.name,
                            FootballPlayer.country == pd_row.country,
                        ).first()
                    if existing is None:
                        db.add(FootballPlayer(
                            name=pd_row.name,
                            country=pd_row.country,
                            position=pd_row.position,
                            club=pd_row.club,
                            external_id=pd_row.external_id,
                        ))
                        added += 1
                    else:
                        skipped += 1
                except Exception as e:
                    errors.append(str(e))
            db.commit()
            st.success(f"Hotovo — {added} přidáno, {skipped} přeskočeno.")
            if errors:
                st.error("\n".join(errors))
            st.rerun()
