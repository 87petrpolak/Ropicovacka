import streamlit as st
import pandas as pd
from app.state import get_db, require_active_game
from app.models.models import Participant

st.title("Účastníci")

db = get_db()
game_id = require_active_game()
if game_id is None:
    st.stop()

participants = db.query(Participant).filter(
    Participant.game_id == game_id
).order_by(Participant.draft_order).all()

if participants:
    rows = [
        {
            "ID": p.id,
            "Jméno": p.name,
            "E-mail": p.email or "—",
            "Pořadí v draftu": p.draft_order or "—",
        }
        for p in participants
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("Zatím žádní účastníci.")

st.divider()

# ------------------------------------------------------------------
# Přidat účastníka
# ------------------------------------------------------------------
with st.expander("➕ Přidat účastníka", expanded=not bool(participants)):
    with st.form("add_participant"):
        name = st.text_input("Jméno")
        email = st.text_input("E-mail (volitelné)")
        draft_order = st.number_input(
            "Pořadí v draftu", min_value=1, step=1, value=len(participants) + 1
        )
        submitted = st.form_submit_button("Přidat")
        if submitted:
            if not name.strip():
                st.error("Jméno je povinné.")
            elif db.query(Participant).filter(
                Participant.game_id == game_id,
                Participant.name == name.strip(),
            ).first():
                st.error("Účastník s tímto jménem již existuje.")
            else:
                db.add(Participant(
                    game_id=game_id,
                    name=name.strip(),
                    email=email.strip() or None,
                    draft_order=int(draft_order),
                ))
                db.commit()
                st.success(f"Účastník {name} byl přidán!")
                st.rerun()

# ------------------------------------------------------------------
# Upravit / smazat
# ------------------------------------------------------------------
if participants:
    st.divider()
    with st.expander("✏️ Upravit / odstranit účastníka"):
        sel_name = st.selectbox("Vyber účastníka", [p.name for p in participants])
        sel = next(p for p in participants if p.name == sel_name)

        with st.form("edit_participant"):
            new_name = st.text_input("Jméno", value=sel.name)
            new_email = st.text_input("E-mail", value=sel.email or "")
            new_order = st.number_input(
                "Pořadí v draftu", min_value=1, step=1, value=sel.draft_order or 1
            )
            col1, col2 = st.columns(2)
            save = col1.form_submit_button("Uložit změny")
            delete = col2.form_submit_button("Smazat", type="secondary")

        if save:
            sel.name = new_name.strip()
            sel.email = new_email.strip() or None
            sel.draft_order = int(new_order)
            db.commit()
            st.success("Uloženo.")
            st.rerun()

        if delete:
            db.delete(sel)
            db.commit()
            st.success(f"Účastník {sel_name} byl odstraněn.")
            st.rerun()
