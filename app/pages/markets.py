"""Marchés : instruments suivis, cours, performances, fondamentaux (§6, §7, §14)."""
import streamlit as st

from app.domain.performance import PERIODS
from app.models.enums import DataStatus
from app.services import portfolio as pf
from app.services import referential
from app.ui import context, fiche, theme, views

theme.header("Marchés", "Cours, performances et fondamentaux. Cliquez sur une ligne pour ouvrir sa fiche.",
             kicker="Marchés")
prefs = context.prefs()

left, right = st.columns([3, 2], vertical_alignment="center")
with left:
    scope = st.segmented_control("Afficher", ["Liste de surveillance", "Détenus", "Indices", "Tous", "Archivés"],
                                 default="Liste de surveillance", label_visibility="collapsed")
search = right.text_input("Rechercher", placeholder="Rechercher un nom, un ticker, un ISIN…",
                          label_visibility="collapsed", icon=":material/search:")

with context.session() as s:
    instruments = referential.list_instruments(s, include_archived=True)
    held_ids = {v.instrument.id for v in pf.holdings(s, prefs)}
    if scope == "Détenus":
        chosen = [i for i in instruments if i.id in held_ids]
    elif scope == "Indices":
        chosen = [i for i in instruments if i.type.name == "INDICE" and not i.archived]
    elif scope == "Archivés":
        chosen = [i for i in instruments if i.archived]
    elif scope == "Tous":
        chosen = [i for i in instruments if not i.archived]
    else:
        chosen = [i for i in instruments if i.watchlist and not i.archived]
    if search:
        needle = search.strip().lower()
        chosen = [i for i in chosen if needle in " ".join(filter(None, (i.name, i.ticker, i.isin))).lower()]
    rows = [views.market_row(s, i, prefs) for i in chosen]

if not rows:
    st.info("Aucun instrument dans cette vue. Ajoutez-en dans « Administration ».")
else:
    frame = views.market_frame(rows)
    pot_na = frame.pop("_pot_na")
    formats = {"Cours": lambda x: theme.number(x, 2)}
    formats.update({label: theme.pct for label in PERIODS})
    potential_texts = [
        theme.status(DataStatus.NON_APPLICABLE) if na else theme.pct(v, na=theme.status(DataStatus.NON_DISPONIBLE))
        for v, na in zip(frame["Potentiel"], pot_na)
    ]
    picked = theme.table(frame, formats, gains=list(PERIODS) + ["Potentiel"],
                         overrides={"Potentiel": potential_texts}, key="markets_table")
    theme.note("Performances calculées sur l'historique réel des cours : N/A si l'historique ne couvre pas la "
               "période (aucune extrapolation). Potentiel = (objectif moyen / cours − 1) × 100.")
    if picked is not None:
        fiche.show(rows[picked].instrument.id)
