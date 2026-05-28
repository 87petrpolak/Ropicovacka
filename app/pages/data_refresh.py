import pandas as pd
import streamlit as st
from app.state import get_db, require_active_game
from app.models.models import DataRefreshLog

st.title("Aktualizace dat")

db = get_db()
game_id = require_active_game()
if game_id is None:
    st.stop()

st.markdown("""
Tato stránka spustí automatickou aktualizaci dat z live zdroje, jakmile bude live konektor nakonfigurován.

**Aktuální stav:** MVP režim — nahrej data ručně přes **Import statistik**.
""")

if st.button("🔄 Aktualizovat nejnovější data zápasů"):
    st.info(
        "Žádný live datový zdroj zatím není nakonfigurován. "
        "Nahrej data ručně přes **Import statistik**."
    )

st.divider()
st.subheader("Audit log aktualizací")

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
