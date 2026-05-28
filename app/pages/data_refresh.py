import pandas as pd
import streamlit as st
from app.state import get_db, require_active_game
from app.models.models import DataRefreshLog
from app.providers.football_data_org_provider import COMPETITION_NAMES
from app.services.data_refresh import run_refresh

st.title("Aktualizace dat")

db = get_db()
game_id = require_active_game()
if game_id is None:
    st.stop()

# ----------------------------------------------------------------
# Live fetch — football-data.org
# ----------------------------------------------------------------
st.subheader("Live aktualizace — football-data.org")

with st.expander("⚙️ Nastavení připojení", expanded=True):
    api_key = st.text_input(
        "API klíč (football-data.org)",
        type="password",
        placeholder="Zadej svůj API klíč z football-data.org",
        help="Zaregistruj se zdarma na football-data.org a klíč najdeš v profilu.",
    )

    comp_code = st.selectbox(
        "Soutěž",
        options=list(COMPETITION_NAMES.keys()),
        format_func=lambda c: f"{c} — {COMPETITION_NAMES[c]}",
        index=0,
    )

    col1, col2 = st.columns(2)
    with col1:
        matchday = st.number_input(
            "Kolo (0 = všechna dokončená)", min_value=0, step=1, value=0
        )
    with col2:
        season = st.number_input(
            "Sezóna (0 = aktuální)", min_value=0, step=1, value=0
        )

if st.button("🔄 Načíst nejnovější data", type="primary", disabled=not api_key):
    if not api_key.strip():
        st.warning("Zadej API klíč.")
    else:
        from app.providers.football_data_org_provider import FootballDataOrgProvider
        provider = FootballDataOrgProvider(
            api_key=api_key.strip(),
            competition_code=comp_code,
            matchday=int(matchday) if matchday else None,
            season=int(season) if season else None,
        )
        with st.spinner("Načítám data z football-data.org…"):
            try:
                result = run_refresh(
                    db,
                    provider,
                    game_id,
                    import_players=False,
                    import_matches=True,
                )
                if result.errors:
                    st.error("Chyby při importu:\n\n" + "\n".join(f"- {e}" for e in result.errors))
                else:
                    parts = []
                    if result.matches_added:
                        parts.append(f"{result.matches_added} zápasů přidáno")
                    if result.matches_updated:
                        parts.append(f"{result.matches_updated} zápasů aktualizováno")
                    if result.stats_added:
                        parts.append(f"{result.stats_added} statistik přidáno")
                    if result.stats_updated:
                        parts.append(f"{result.stats_updated} statistik aktualizováno")
                    st.success("Hotovo — " + (", ".join(parts) or "nic nového"))
                    st.info(
                        "**Tip:** Hráči bez gólu/asistence v tomto kole nemají statistiky "
                        "(free tier API nemá sestavy). Pro plné bodování importuj sestavy přes CSV."
                    )
            except Exception as e:
                st.error(f"Chyba při komunikaci s API: {e}")

st.divider()

st.markdown("""
**Jak získat API klíč zdarma:**
1. Jdi na [football-data.org/client/register](https://www.football-data.org/client/register)
2. Zadej email a heslo
3. Klíč přijde emailem do pár minut
4. Free tier zahrnuje: Premier League, Bundesliga, Serie A, La Liga, Ligue 1, MS

**Omezení free tieru:** Hráče bez gólu nebo asistence nelze detekovat (API nevrací sestavy).
Tito hráči budou mít `played=False` a nebudou bodovat za výhru týmu.
Řešení: importuj sestavy ručně přes CSV nebo přejdi na placený tier.
""")

st.divider()

# ----------------------------------------------------------------
# Audit log
# ----------------------------------------------------------------
st.subheader("Historie aktualizací")

logs = (
    db.query(DataRefreshLog)
    .order_by(DataRefreshLog.run_at.desc())
    .limit(50)
    .all()
)

if logs:
    rows = [
        {
            "Čas (UTC)": log.run_at.strftime("%Y-%m-%d %H:%M:%S"),
            "Zdroj": log.provider,
            "Přidáno": log.records_added,
            "Aktualizováno": log.records_updated,
            "Přeskočeno": log.records_skipped,
            "Stav": "✅ OK" if log.success else "❌ Chyba",
            "Poznámky": log.notes or "—",
        }
        for log in logs
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("Zatím žádné aktualizace.")
