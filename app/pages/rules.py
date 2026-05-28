import streamlit as st

st.title("Pravidla")

st.markdown("""
## Ropičovačka 2026 — MS ve fotbale

---

### Kádr
Každý účastník si nadraftuje kádr **18 hráčů**: 11 základních + 7 náhradníků.

---

### Požadavky na základní sestavu
| Pozice | Počet |
|--------|-------|
| Brankář | přesně 1 |
| Obránci | 3–5 |
| Záložníci | 3–5 |
| Útočníci | 1–3 |

---

### Draft
- **Snake draft** — pořadí výběru se v každém kole otočí
- Každý hráč může být draftnutý pouze jedním účastníkem
- 18 kol draftu (jedno za každého hráče v kádru)
- Administrátor může vrátit poslední pick

---

### Nominace sestavy
Před každým kolem turnaje každý účastník nominuje **11 hráčů** ze svého 18-hráčového kádru.

- Body získávají pouze nominovaní hráči
- Náhradníci automaticky **nenaskakují** — žádná automatická střídání
- Pokud nominovaný hráč nenastoupí, účastník za něj dostane 0 bodů
- Nominaci je nutné podat před **deadlinem** kola
- Po deadlinu je nominace zamknutá
- Administrátor může nominaci výjimečně odemknout

---

### Bodování
| Událost | Pozice | Body |
|---------|--------|------|
| Gól | Všichni | **25** |
| Asistence | Všichni | **20** |
| Výhra týmu | Všichni | **10** |
| Čisté konto | Brankář | **25** |
| Čisté konto | Obránce | **10** |

> Čisté konto = tým nedostal žádný gól v daném zápase.
> Záložníci a útočníci za čisté konto body **nedostávají**.

---

### Přestupy
**Žádné.** Co si nadraftuješ, s tím hraješ celý turnaj.

---

### Žádná automatická střídání
Náhradníci slouží pouze jako záloha pro draft — dávají ti větší výběr při nominaci. Pokud chceš místo zraněného hráče nominovat náhradníka, musíš to sám udělat před dalším deadlinem.
""")
