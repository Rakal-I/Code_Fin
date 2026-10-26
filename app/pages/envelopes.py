"""Enveloppes : vue par enveloppe et par contrat (§5, §14)."""
from collections import defaultdict

import pandas as pd
import streamlit as st

from app.services import portfolio as pf
from app.services import referential
from app.ui import context, theme

theme.header("Enveloppes", "PEA, assurance-vie, PER, CTO… vus séparément.", kicker="Patrimoine")
prefs = context.prefs()
masked = prefs.mask_amounts

mode = st.segmented_control("Vue", ["Par enveloppe", "Par contrat"], default="Par enveloppe",
                            label_visibility="collapsed")

with context.session() as s:
    envelopes = referential.list_envelopes(s, include_archived=True)
    views = pf.holdings(s, prefs)
    flows = {e.id: pf.cash_flows(s, e.id) for e in envelopes}

if not envelopes:
    st.info("Aucune enveloppe. Créez-en une dans « Administration ».")
    theme.link("app/pages/admin.py", "Administration", icon=":material/tune:")
    st.stop()


def lines_table(lines) -> None:
    if not lines:
        theme.note("Aucune position ouverte.")
        return
    frame = pd.DataFrame([{
        "Instrument": v.instrument.name,
        "Quantité": v.state.quantity,
        "PRU": v.state.pru,
        "Devise": v.currency,
        "Valeur (€)": v.valuation.value_eur,
        "Plus-value (€)": v.valuation.gain_eur,
        "Plus-value %": v.valuation.gain_eur_pct,
        "Cours": theme.status(v.price_status),
    } for v in lines])
    theme.table(frame, {
        "Quantité": lambda x: theme.qty(x, masked),
        "PRU": lambda x: theme.number(x, 2),
        "Valeur (€)": lambda x: theme.money(x, masked=masked),
        "Plus-value (€)": lambda x: theme.money(x, masked=masked, signed=True),
        "Plus-value %": theme.pct,
    }, gains=["Plus-value (€)", "Plus-value %"])


def totals(lines) -> tuple[float, float, int]:
    valued = [v for v in lines if v.valuation.value_eur is not None and v.valuation.gain_eur is not None]
    return (sum(v.valuation.value_eur for v in valued), sum(v.valuation.gain_eur for v in valued),
            len(lines) - len(valued))


if mode == "Par contrat":
    groups = defaultdict(list)
    for v in views:
        groups[(v.envelope.institution, v.envelope.contract or "Sans numéro")].append(v)
    for (institution, contract), lines in sorted(groups.items()):
        value, gain, missing = totals(lines)
        st.markdown(f'<div class="anc-kicker">{institution}</div>', unsafe_allow_html=True)
        st.subheader(f"Contrat {contract}")
        c1, c2 = st.columns(2)
        c1.metric("Valorisation", theme.money(value, masked=masked, decimals=0))
        c2.metric("Plus-value latente", theme.money(gain, masked=masked, decimals=0, signed=True))
        if missing:
            theme.note(f"{missing} ligne(s) non valorisée(s), exclue(s) du total.")
        lines_table(lines)
        st.divider()
    if not groups:
        theme.note("Aucune position ouverte.")
else:
    for envelope in envelopes:
        lines = [v for v in views if v.envelope.id == envelope.id]
        if envelope.archived and not lines:
            continue
        value, gain, missing = totals(lines)
        flow = flows[envelope.id]
        archived = " · archivée" if envelope.archived else ""
        st.markdown(f'<div class="anc-kicker">{envelope.type.label} · {envelope.institution}'
                    f'{" · " + envelope.contract if envelope.contract else ""}{archived}</div>',
                    unsafe_allow_html=True)
        st.subheader(envelope.name)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Valorisation", theme.money(value, masked=masked, decimals=0))
        c2.metric("Plus-value latente", theme.money(gain, masked=masked, decimals=0, signed=True))
        c3.metric("Apports nets", theme.money(flow.contributions_eur - flow.withdrawals_eur, masked=masked,
                                               decimals=0))
        c4.metric("Frais", theme.money(flow.fees_eur, masked=masked, decimals=0))
        if missing:
            theme.note(f"{missing} ligne(s) non valorisée(s), exclue(s) du total.")
        if flow.unconverted:
            theme.note(f"{flow.unconverted} flux sans taux de change non inclus.")
        if envelope.comment:
            theme.note(envelope.comment)
        lines_table(lines)
        st.divider()
