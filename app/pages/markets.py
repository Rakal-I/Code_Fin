"""Marchés : instruments suivis, cours, performances, fondamentaux (§6, §7, §14)."""
from datetime import timedelta

import streamlit as st

from app.domain.performance import PERIODS
from app.models.enums import DataStatus
from app.services import market_data, referential
from app.services import portfolio as pf
from app.ui import context, theme, views

theme.header("Marchés", "Cours, performances et fondamentaux. Chaque donnée indique sa source et sa date.",
             kicker="Marchés")
prefs = context.prefs()

scope = st.segmented_control("Afficher", ["Liste de surveillance", "Détenus", "Indices", "Tous", "Archivés"],
                             default="Liste de surveillance", label_visibility="collapsed")

with context.session() as s:
    instruments = referential.list_instruments(s, include_archived=True)
    held_ids = {v.instrument.id for v in pf.holdings(s, prefs)}
    if scope == "Liste de surveillance":
        chosen = [i for i in instruments if i.watchlist and not i.archived]
    elif scope == "Détenus":
        chosen = [i for i in instruments if i.id in held_ids]
    elif scope == "Indices":
        chosen = [i for i in instruments if i.type.name == "INDICE" and not i.archived]
    elif scope == "Archivés":
        chosen = [i for i in instruments if i.archived]
    else:
        chosen = [i for i in instruments if not i.archived]
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
    theme.table(frame, formats, gains=list(PERIODS) + ["Potentiel"], overrides={"Potentiel": potential_texts})
    theme.note("Performances calculées sur l'historique réel des cours : N/A si l'historique ne couvre pas la "
               "période (aucune extrapolation). Potentiel = (objectif moyen / cours − 1) × 100.")

st.divider()
st.subheader("Fiche instrument")
if not chosen:
    st.stop()
labels = {views.instrument_label(i): i.id for i in chosen}
picked = st.selectbox("Instrument", list(labels), label_visibility="collapsed")
instrument_id = labels[picked]

with context.session() as s:
    instrument = referential.get_instrument(s, instrument_id)
    left, right = st.columns([3, 1], vertical_alignment="bottom")
    left.markdown(f"### {instrument.name}")
    if right.button("Actualiser", icon=":material/refresh:", width="stretch", disabled=instrument.archived):
        with st.spinner("Interrogation des sources…"):
            result = market_data.refresh_instrument(s, instrument, context.connectors())
        if result.ok:
            st.success("Instrument actualisé.")
        else:
            st.warning(" ".join(result.messages))

    identity = {
        "Type": instrument.type.label + (f" · {instrument.subtype.label}" if instrument.subtype else ""),
        "Ticker": instrument.ticker or "—",
        "Symbole fournisseur": instrument.symbol or "—",
        "ISIN": instrument.isin or "—",
        "Place de cotation": instrument.exchange or "—",
        "Devise": instrument.currency,
        "Pays": instrument.country or "—",
        "Société / gestionnaire": instrument.issuer or "—",
        "Identifiant interne": f"#{instrument.id}",
    }
    cols = st.columns(3)
    for index, (key, value) in enumerate(identity.items()):
        cols[index % 3].markdown(f'<div class="anc-kicker">{key}</div>{value}', unsafe_allow_html=True)

    history = market_data.price_history(s, instrument.id)
    row = views.market_row(s, instrument, prefs)
    sections = views.fundamentals_sections(s, instrument, prefs)
    not_applicable = views.not_applicable_fields(instrument)

st.write("")
price = row.price
c1, c2, c3 = st.columns(3)
c1.metric("Dernier cours" if instrument.type.name in ("ACTION", "ETF", "INDICE") else "Dernière VL",
          theme.money(price.value_num, price.point.currency) if price.has_value else price.status.label)
c2.metric("Statut", theme.status(price.status))
c3.metric("Date de référence", theme.day(price.point.reference_date) if price.point else "—")
if price.point is not None:
    theme.note(f"Source : {price.point.source} · collecté le {theme.day(price.point.collected_at)} (UTC)"
               + (f" · {price.point.note}" if price.point.note else ""))

if history:
    period = st.segmented_control("Période", ["1 mois", "6 mois", "1 an", "5 ans", "10 ans", "Max"],
                                  default="1 an", label_visibility="collapsed")
    days = {"1 mois": 31, "6 mois": 183, "1 an": 366, "5 ans": 1827, "10 ans": 3653}.get(period)
    last_day = history[-1][0]
    shown = [(d, c) for d, c in history if days is None or d >= last_day - timedelta(days=days)]
    st.plotly_chart(theme.line([d for d, _ in shown], [c for _, c in shown], currency=instrument.currency),
                    config=theme.CHART_CONFIG, width="stretch")
    theme.perf_strip(row.perf)
else:
    theme.note("Aucun historique de cours : lancez une actualisation.")

for title, frame in sections.items():
    st.subheader(title)
    st.dataframe(frame, hide_index=True, width="stretch")
if not_applicable:
    theme.note("⚫ Non applicable à ce type d'instrument : " + ", ".join(not_applicable) + ".")
