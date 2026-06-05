import pandas as pd
import streamlit as st
from app.state import get_db, require_active_game
from app.models.models import DataRefreshLog
from app.services.data_refresh import run_refresh

st.title("Aktualizace dat")

db = get_db()
game_id = require_active_game()
if game_id is None:
    st.stop()

# ----------------------------------------------------------------
# Live fetch — Livesport.cz
# ----------------------------------------------------------------
st.subheader("Live aktualizace — Livesport.cz")

st.info(
    "Data se stahují přímo z Livesport.cz (Flashscore). "
    "Nevyžaduje žádný API klíč. Zahrnuje: góly, asistence, minuty na hřišti."
)

with st.expander("⚙️ Nastavení", expanded=True):
    from app.providers.livesport_provider import WC_2026_TOURNAMENT_ID
    tournament_id = st.text_input(
        "Flashscore Tournament ID",
        value=WC_2026_TOURNAMENT_ID,
        help="ID turnaje na Flashscore. MS 2026 = zeSHfCx3",
    )

if st.button("🔄 Načíst nejnovější data", type="primary", use_container_width=True):
    from app.providers.livesport_provider import LivesportProvider
    provider = LivesportProvider(tournament_id=tournament_id.strip())
    with st.spinner("Načítám data z Livesport.cz…"):
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
                    "Hráči bez jakéhokoliv incidentu (bez gólu, asistence, střídání) "
                    "nejsou v datech — doplň je sestavou přes CSV import."
                )
        except Exception as e:
            st.error(f"Chyba při načítání dat: {e}")

st.divider()

# ----------------------------------------------------------------
# Bodovací pravidla (přehled)
# ----------------------------------------------------------------
with st.expander("📋 Aktuální bodovací pravidla"):
    st.markdown("""
| Událost | Body | Podmínka |
|---|---|---|
| Vstřelená branka | +30 Kč | — |
| Asistence na branku | +25 Kč | — |
| Výhra týmu (záložník) | +15 Kč | 60+ minut na hřišti |
| Výhra týmu (obránce) | +15 Kč | 60+ minut na hřišti |
| Čisté konto (obránce) | +15 Kč | 60+ minut na hřišti |
| Čisté konto (brankář) | +30 Kč | 60+ minut na hřišti |

Útočník boduje pouze za góly a asistence.
Body se přelévají — ostatní účastníci platí stejnou částku.
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
