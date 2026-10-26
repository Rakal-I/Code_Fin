"""Revenus : dividendes, distributions, coupons (§14)."""
from collections import defaultdict

import pandas as pd
import streamlit as st

from app.models.enums import INCOME_OPERATIONS
from app.services import portfolio as pf
from app.ui import context, theme

theme.header("Revenus", "Dividendes, distributions et coupons perçus.", kicker="Patrimoine")
prefs = context.prefs()
masked = prefs.mask_amounts

with context.session() as s:
    rows = pf.incomes(s)

if not rows:
    st.info("Aucun revenu enregistré. Saisissez vos dividendes, distributions et coupons dans « Saisie ».")
    theme.link("app/pages/entry.py", "Saisie", icon=":material/edit_note:")
    st.stop()

years = sorted({r.day.year for r in rows}, reverse=True)
c1, c2 = st.columns([1, 3])
year = c1.selectbox("Année", ["Toutes"] + years)
kinds = c2.pills("Type", [t.label for t in INCOME_OPERATIONS], selection_mode="multi",
                 default=[t.label for t in INCOME_OPERATIONS])
selected = [r for r in rows if (year == "Toutes" or r.day.year == year) and r.type.label in (kinds or [])]

total = sum(r.amount_eur for r in selected if r.amount_eur is not None)
missing = sum(1 for r in selected if r.amount_eur is None)
by_type = defaultdict(float)
for r in selected:
    if r.amount_eur is not None:
        by_type[r.type.label] += r.amount_eur

m = st.columns(4)
m[0].metric("Total perçu", theme.money(total, masked=masked, decimals=0))
for col, kind in zip(m[1:], INCOME_OPERATIONS):
    col.metric(f"{kind.label}s", theme.money(by_type.get(kind.label, 0.0), masked=masked, decimals=0))
if missing:
    theme.note(f"{missing} revenu(s) sans taux de change ne sont pas inclus dans les totaux en euros.")

monthly = defaultdict(float)
for r in selected:
    if r.amount_eur is not None:
        monthly[r.day.strftime("%Y-%m")] += r.amount_eur
if monthly:
    st.subheader("Par mois")
    keys = sorted(monthly)
    labels = [f"{k[5:]}/{k[:4]}" for k in keys]
    current_year = max(k[:4] for k in keys)
    st.plotly_chart(theme.bars(labels, [monthly[k] for k in keys], masked=masked,
                               emphasis=[k[:4] == current_year for k in keys]), config=theme.CHART_CONFIG,
                    width="stretch")

st.subheader("Détail")
frame = pd.DataFrame([{
    "Date": r.day.strftime("%d/%m/%Y"),
    "Type": r.type.label,
    "Instrument": r.instrument,
    "Enveloppe": r.envelope,
    "Montant": r.amount,
    "Devise": r.currency,
    "Montant (€)": r.amount_eur,
} for r in reversed(selected)])
theme.table(frame, {
    "Montant": lambda x: theme.number(x, 2) if not masked else theme.MASK,
    "Montant (€)": lambda x: theme.money(x, masked=masked),
})
