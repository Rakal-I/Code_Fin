"""Tableau de bord global (§14)."""
from datetime import timedelta

import pandas as pd
import streamlit as st

from app.services import portfolio as pf
from app.services.market_data import today_utc
from app.ui import context, fiche, theme

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

gain_color = theme.tone(summary.gain_eur)
theme.hero(
    "Valorisation totale",
    theme.money(summary.value_eur, masked=masked, decimals=0),
    f'<span style="color:{gain_color}">{theme.money(summary.gain_eur, masked=masked, decimals=0, signed=True)} '
    f'({theme.pct(summary.gain_pct)})</span> <span class="muted">plus-value latente</span>',
    side=[
        ("Plus-values réalisées", theme.money(summary.realized_eur, masked=masked, decimals=0, signed=True),
         theme.tone(summary.realized_eur)),
        ("Revenus sur 12 mois", theme.money(income_12m, masked=masked, decimals=0), theme.INK),
        ("Lignes", str(summary.lines), theme.INK),
    ],
)

if summary.unvalued_lines:
    st.warning(f"{summary.unvalued_lines} ligne(s) sur {summary.lines} ne sont pas valorisées (cours ou taux de "
               "change indisponible) : elles sont exclues des totaux, jamais comptées pour zéro. "
               "Détail dans « Portefeuille ».")
if income_missing:
    theme.note(f"{income_missing} revenu(s) sans taux de change ne sont pas inclus dans le total sur 12 mois.")

left, right = st.columns(2, gap="medium")
for column, title, values, caption, uid in (
        (left, "Par enveloppe", summary.by_envelope, "enveloppes", "env"),
        (right, "Par type d'actifs", summary.by_type, "types d'actifs", "typ")):
    with column:
        st.markdown(f"#### {title}")
        if values:
            theme.ring_card(values, masked, f"{len(values)} {caption}", uid)
        else:
            theme.note("Aucune ligne valorisée.")

st.markdown("#### Principales lignes")
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
    theme.hint("Cliquez sur une ligne pour ouvrir la fiche de l'instrument.")
    picked = theme.table(frame, {
        "Valeur": lambda x: theme.money(x, masked=masked),
        "Poids": lambda x: theme.pct(x, 1, signed=False),
        "Plus-value": lambda x: theme.money(x, masked=masked, signed=True),
        "Plus-value %": theme.pct,
    }, gains=["Plus-value", "Plus-value %"], key="dashboard_top")
    if picked is not None:
        fiche.show(top[picked].instrument.id)
else:
    theme.note("Aucune ligne valorisée pour l'instant : lancez une actualisation.")
