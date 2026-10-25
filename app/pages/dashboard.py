"""Tableau de bord global (§14)."""
from datetime import timedelta

import pandas as pd
import streamlit as st

from app.services import portfolio as pf
from app.services.market_data import today_utc
from app.ui import context, theme

theme.header("Tableau de bord", "Votre patrimoine consolidé en euros.", kicker="Patrimoine")
prefs = context.prefs()
masked = prefs.mask_amounts

with context.session() as s:
    all_views = pf.holdings(s, prefs, include_closed=True)
    open_views = [v for v in all_views if v.is_open]
    summary = pf.summarize(all_views)
    income_rows = pf.incomes(s)

if not all_views:
    st.info("Aucune position pour l'instant. Commencez par créer une enveloppe et un instrument, "
            "puis saisissez vos positions existantes.")
    c1, c2 = st.columns(2)
    theme.link("app/pages/admin.py", "Administration : enveloppes et instruments", icon=":material/tune:", container=c1)
    theme.link("app/pages/entry.py", "Saisie : positions initiales", icon=":material/edit_note:", container=c2)
    st.stop()

year_ago = today_utc() - timedelta(days=365)
recent = [r for r in income_rows if r.day >= year_ago]
income_12m = sum(r.amount_eur for r in recent if r.amount_eur is not None)
income_missing = sum(1 for r in recent if r.amount_eur is None)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Valorisation totale", theme.money(summary.value_eur, masked=masked, decimals=0))
c2.metric("Plus-value latente", theme.money(summary.gain_eur, masked=masked, decimals=0, signed=True),
          delta=theme.pct(summary.gain_pct) if summary.gain_pct is not None else None,
          delta_color="normal")
c3.metric("Plus-values réalisées", theme.money(summary.realized_eur, masked=masked, decimals=0, signed=True))
c4.metric("Revenus sur 12 mois", theme.money(income_12m, masked=masked, decimals=0))

if summary.unvalued_lines:
    st.warning(f"{summary.unvalued_lines} ligne(s) sur {summary.lines} ne sont pas valorisées (cours ou taux de "
               "change indisponible) : elles sont exclues des totaux, jamais comptées pour zéro. "
               "Détail dans « Portefeuille ».")
if income_missing:
    theme.note(f"{income_missing} revenu(s) sans taux de change ne sont pas inclus dans le total sur 12 mois.")

st.write("")
left, right = st.columns(2, gap="large")
for column, title, values in ((left, "Répartition par enveloppe", summary.by_envelope),
                              (right, "Répartition par type d'actifs", summary.by_type)):
    with column:
        st.subheader(title)
        if values:
            ordered = dict(sorted(values.items(), key=lambda kv: kv[1], reverse=True))
            chart, legend = st.columns([1, 1], vertical_alignment="center")
            chart.plotly_chart(theme.ring(ordered, masked=masked, height=260), config=theme.CHART_CONFIG,
                               width="stretch")
            with legend:
                theme.legend(ordered)
        else:
            theme.note("Aucune ligne valorisée.")

st.subheader("Principales lignes")
top = sorted([v for v in open_views if v.valuation.value_eur is not None],
             key=lambda v: v.valuation.value_eur, reverse=True)[:8]
if top:
    total = summary.value_eur or 1
    frame = pd.DataFrame([{
        "Instrument": v.instrument.name,
        "Enveloppe": v.envelope.name,
        "Valeur": v.valuation.value_eur,
        "Poids": v.valuation.value_eur / total * 100,
        "Plus-value": v.valuation.gain_eur,
        "Plus-value %": v.valuation.gain_eur_pct,
        "Cours": theme.status(v.price_status),
    } for v in top])
    theme.table(frame, {
        "Valeur": lambda x: theme.money(x, masked=masked),
        "Poids": lambda x: theme.pct(x, 1, signed=False),
        "Plus-value": lambda x: theme.money(x, masked=masked, signed=True),
        "Plus-value %": theme.pct,
    }, gains=["Plus-value", "Plus-value %"])
else:
    theme.note("Aucune ligne valorisée pour l'instant : lancez une actualisation.")
