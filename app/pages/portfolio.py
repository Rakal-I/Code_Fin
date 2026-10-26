"""Portefeuille : positions, valorisation, gains et pertes (§11, §12, §14)."""
import pandas as pd
import streamlit as st

from app.services import portfolio as pf
from app.ui import context, fiche, theme

theme.header("Portefeuille", "Chaque ligne : quantité, PRU, valorisation et plus-value, en devise et en euros.",
             kicker="Patrimoine")
prefs = context.prefs()
masked = prefs.mask_amounts

with context.session() as s:
    views = pf.holdings(s, prefs, include_closed=True)

open_views = [v for v in views if v.is_open]
if not open_views:
    st.info("Aucune position ouverte.")
    theme.link("app/pages/entry.py", "Saisir une position initiale ou une opération", icon=":material/edit_note:")

if open_views:
    frame = pd.DataFrame([{
        "Enveloppe": v.envelope.name,
        "Instrument": v.instrument.name + (" · archivé" if v.instrument.archived else ""),
        "Quantité": v.state.quantity,
        "PRU": v.state.pru,
        "Cours": v.valuation.price,
        "Devise": v.currency,
        "Statut du cours": theme.status(v.price_status),
        "Valeur (€)": v.valuation.value_eur,
        "Plus-value (€)": v.valuation.gain_eur,
        "Plus-value %": v.valuation.gain_eur_pct,
        "Effet marché (€)": v.valuation.market_effect_eur,
        "Effet change (€)": v.valuation.fx_effect_eur,
    } for v in open_views])
    money = lambda x: theme.money(x, masked=masked)  # noqa: E731
    signed = lambda x: theme.money(x, masked=masked, signed=True)  # noqa: E731
    theme.hint("Cliquez sur une ligne pour ouvrir la fiche de l'instrument.")
    picked = theme.table(frame, {
        "Quantité": lambda x: theme.qty(x, masked),
        "PRU": lambda x: theme.number(x, 2),
        "Cours": lambda x: theme.number(x, 2),
        "Valeur (€)": money,
        "Plus-value (€)": signed,
        "Plus-value %": theme.pct,
        "Effet marché (€)": signed,
        "Effet change (€)": signed,
    }, gains=["Plus-value (€)", "Plus-value %", "Effet marché (€)", "Effet change (€)"], key="portfolio_lines")
    if picked is not None:
        fiche.show(open_views[picked].instrument.id)
    theme.note("Plus-value = valeur actuelle − coût d'acquisition. En euros, elle se décompose en effet de marché "
               "(variation du cours, au taux de change d'achat) et effet de change. « — » : donnée indisponible, "
               "jamais remplacée par zéro.")

    issues = [(v, i) for v in open_views for i in v.issues]
    if issues:
        with st.expander(f"⚠️ {len(issues)} point(s) d'attention"):
            for view, issue in issues:
                st.markdown(f"- **{view.instrument.name}** ({view.envelope.name}) : {issue}")

st.subheader("Plus-values réalisées")
realized = [v for v in views if abs(v.state.realized) > 1e-9]
if realized:
    frame = pd.DataFrame([{
        "Enveloppe": v.envelope.name,
        "Instrument": v.instrument.name,
        "Ligne": "Ouverte" if v.is_open else "Soldée",
        "Réalisé (devise)": v.state.realized,
        "Devise": v.currency,
        "Réalisé (€)": v.state.realized_eur,
    } for v in realized])
    theme.table(frame, {
        "Réalisé (devise)": lambda x: theme.number(x, 2) if not masked else theme.MASK,
        "Réalisé (€)": lambda x: theme.money(x, masked=masked, signed=True),
    }, gains=["Réalisé (devise)", "Réalisé (€)"])
else:
    theme.note("Aucune vente enregistrée.")
