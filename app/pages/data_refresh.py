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

tab_live, tab_history = st.tabs(["🔴 Live (MS 2026)", "📂 Historický import (testování)"])

# ----------------------------------------------------------------
# TAB 1: Live fetch — MS 2026
# ----------------------------------------------------------------
with tab_live:
    st.subheader("Live aktualizace — Livesport.cz")
    st.info(
        "Stahuje výsledky aktuálního turnaje z Livesport.cz. "
        "Nevyžaduje API klíč. Spusť po každém odehraném kole."
    )

    from app.providers.livesport_provider import WC_2026_TOURNAMENT_ID
    tournament_id = st.text_input(
        "Flashscore Tournament ID",
        value=WC_2026_TOURNAMENT_ID,
        help="MS 2026 = zeSHfCx3",
    )

    if st.button("🔄 Načíst nejnovější data", type="primary", use_container_width=True):
        from app.providers.livesport_provider import LivesportProvider
        provider = LivesportProvider(tournament_id=tournament_id.strip())
        with st.spinner("Načítám data z Livesport.cz…"):
            try:
                result = run_refresh(db, provider, game_id, import_players=False, import_matches=True)
                _show_result(result) if False else None  # volá se níže
                if result.errors:
                    st.error("Chyby:\n\n" + "\n".join(f"- {e}" for e in result.errors))
                else:
                    parts = []
                    if result.matches_added: parts.append(f"{result.matches_added} zápasů přidáno")
                    if result.matches_updated: parts.append(f"{result.matches_updated} aktualizováno")
                    if result.stats_added: parts.append(f"{result.stats_added} statistik přidáno")
                    if result.stats_updated: parts.append(f"{result.stats_updated} statistik aktualizováno")
                    st.success("Hotovo — " + (", ".join(parts) or "nic nového"))
            except Exception as e:
                st.error(f"Chyba: {e}")

# ----------------------------------------------------------------
# TAB 2: Historický import (PL testování)
# ----------------------------------------------------------------
with tab_history:
    st.subheader("Historický import konkrétních zápasů")
    st.info(
        "Zadej Flashscore Match ID zápasů (každé ID na nový řádek). "
        "Použij pro testování s historickými výsledky PL nebo jiné soutěže."
    )

    # Přednastavená kola 36-38 PL 2025/26
    PL_ROUNDS = {
        "PL 36. kolo": "nclkvV1t\n8Cxbx9Wh\nUmvdMdte\nMed3KzB7\nxWhvMmnC\n4IfWN9Ha\nYLpmOIBr\n2iZkrv3E\ndY8uKRGO\n8j1NPVnm",
        "PL 37. kolo": "Uu6uknGb\nrkXMW40U\nGxt6zm15\nz1yE3oVi\nMF2Xj8on\njeflmQpB\nOM7eo4FN\nWSUM1Pa4\nr7lSurwo\nAyZEYQVH",
        "PL 38. kolo": "xQXUa3UG\nbuMwbsaT\nUNC9hLMj\npWfdGOEc\nIqg4E2qA\nzLXUefTr\nroywfYce\n40PohCS7\nW6HXFFKE\nCGPuEgkR",
    }

    preset = st.selectbox("Přednastavená kola PL 2025/26", ["— vlastní —"] + list(PL_ROUNDS.keys()))

    default_ids = PL_ROUNDS.get(preset, "") if preset != "— vlastní —" else ""
    match_ids_raw = st.text_area(
        "Match ID (jedno na řádek)",
        value=default_ids,
        height=200,
        placeholder="xQXUa3UG\nbuMwbsaT\n...",
    )

    if st.button("📥 Importovat zápasy", type="primary", use_container_width=True):
        match_ids = [m.strip() for m in match_ids_raw.strip().splitlines() if m.strip()]
        if not match_ids:
            st.warning("Zadej alespoň jedno Match ID.")
        else:
            from app.providers.livesport_provider import LivesportProvider
            provider = LivesportProvider(match_ids=match_ids)
            with st.spinner(f"Importuji {len(match_ids)} zápasů…"):
                try:
                    result = run_refresh(db, provider, game_id, import_players=False, import_matches=True)
                    if result.errors:
                        st.error("Chyby:\n\n" + "\n".join(f"- {e}" for e in result.errors))
                    else:
                        parts = []
                        if result.matches_added: parts.append(f"{result.matches_added} zápasů přidáno")
                        if result.matches_updated: parts.append(f"{result.matches_updated} aktualizováno")
                        if result.stats_added: parts.append(f"{result.stats_added} statistik přidáno")
                        if result.stats_updated: parts.append(f"{result.stats_updated} statistik aktualizováno")
                        st.success("Hotovo — " + (", ".join(parts) or "nic nového"))
                        st.info(
                            "Hráči bez gólu/asistence/střídání se v datech neobjeví — "
                            "pro plné bodování je potřeba sestavy ze zápasů."
                        )
                except Exception as e:
                    st.error(f"Chyba: {e}")

st.divider()

# ----------------------------------------------------------------
# Bodovací pravidla
# ----------------------------------------------------------------
with st.expander("📋 Bodovací pravidla"):
    st.markdown("""
| Událost | Body | Podmínka |
|---|---|---|
| Vstřelená branka | +30 Kč | — |
| Asistence | +25 Kč | — |
| Výhra týmu (záložník) | +15 Kč | 60+ minut |
| Výhra týmu (obránce) | +15 Kč | 60+ minut |
| Čisté konto (obránce) | +15 Kč | 60+ minut |
| Čisté konto (brankář) | +30 Kč | 60+ minut |

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
