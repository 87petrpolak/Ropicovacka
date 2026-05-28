import io
import streamlit as st
from app.state import get_db, require_active_game
from app.providers.csv_provider import CsvFootballDataProvider
from app.services.data_refresh import run_refresh

st.title("Import statistik")

db = get_db()
game_id = require_active_game()
if game_id is None:
    st.stop()

st.markdown("""
Importuj výsledky zápasů a statistiky hráčů přes CSV soubory.

### matches.csv
Povinné: `home_team`, `away_team`, `home_score`, `away_score`
Volitelné: `played_at` (RRRR-MM-DD nebo RRRR-MM-DD HH:MM), `external_id`, `round_name`, `round_number`, `is_finished`

### stats.csv
Povinné: `player_name`, `match_external_id`, `goals`, `assists`, `played`, `team_won`, `clean_sheet`
Volitelné: `player_external_id`

### players.csv (volitelné)
Povinné: `name`, `country`, `position`
Volitelné: `club`, `external_id`

Vzorové soubory najdeš ve složce `data/samples/`.
""")

st.divider()

col1, col2 = st.columns(2)
with col1:
    matches_file = st.file_uploader("matches.csv", type="csv", key="matches_upload")
with col2:
    stats_file = st.file_uploader("stats.csv", type="csv", key="stats_upload")

with st.expander("Importovat také hráče"):
    players_file = st.file_uploader("players.csv", type="csv", key="players_upload")

if st.button("🚀 Importovat", type="primary"):
    if not any([matches_file, stats_file, players_file]):
        st.warning("Nahraj alespoň jeden soubor.")
    else:
        matches_src = io.StringIO(matches_file.read().decode()) if matches_file else None
        stats_src = io.StringIO(stats_file.read().decode()) if stats_file else None
        players_src = io.StringIO(players_file.read().decode()) if players_file else None

        provider = CsvFootballDataProvider(
            players_csv=players_src,
            matches_csv=matches_src,
            stats_csv=stats_src,
        )

        with st.spinner("Importuji…"):
            result = run_refresh(
                db,
                provider,
                game_id,
                import_players=players_src is not None,
                import_matches=matches_src is not None,
            )

        if result.errors:
            st.error("Chyby při importu:\n\n" + "\n".join(f"- {e}" for e in result.errors))
        else:
            parts = []
            if result.players_added:
                parts.append(f"{result.players_added} hráčů přidáno")
            if result.matches_added:
                parts.append(f"{result.matches_added} zápasů přidáno")
            if result.matches_updated:
                parts.append(f"{result.matches_updated} zápasů aktualizováno")
            if result.stats_added:
                parts.append(f"{result.stats_added} statistik přidáno")
            if result.stats_updated:
                parts.append(f"{result.stats_updated} statistik aktualizováno")
            st.success("Import dokončen — " + (", ".join(parts) or "nic nového"))
