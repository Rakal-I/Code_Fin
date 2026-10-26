"""Fiche instrument, ouverte dans une fenêtre depuis n'importe quel tableau."""
from __future__ import annotations

from datetime import timedelta
from html import escape

import streamlit as st

from app.services import market_data, referential
from app.ui import context, theme, views

PERIOD_DAYS = {"1 mois": 31, "6 mois": 183, "1 an": 366, "5 ans": 1827, "10 ans": 3653, "Max": None}


def render(instrument_id: int) -> None:
    prefs = context.prefs()
    with context.session() as s:
        instrument = referential.get_instrument(s, instrument_id)
        history = market_data.price_history(s, instrument.id)
        row = views.market_row(s, instrument, prefs)
        sections = views.fundamentals_sections(s, instrument, prefs)
        not_applicable = views.not_applicable_fields(instrument)
        name, archived, currency = instrument.name, instrument.archived, instrument.currency
        identity = {
            "Type": instrument.type.label + (f" · {instrument.subtype.label}" if instrument.subtype else ""),
            "Ticker": instrument.ticker or "—",
            "ISIN": instrument.isin or "—",
            "Place de cotation": instrument.exchange or "—",
            "Devise": instrument.currency,
            "Société / gestionnaire": instrument.issuer or "—",
        }

    price = row.price
    head, action = st.columns([4, 1], vertical_alignment="center")
    subtitle = " · ".join(v for v in (identity["Ticker"], identity["Place de cotation"]) if v != "—")
    head.markdown(f'<div class="anc-kicker">{escape(identity["Type"])}</div>'
                  f'<h2 style="margin:0">{escape(name)}</h2>'
                  f'<div class="anc-sub" style="margin:.1rem 0 0">{escape(subtitle)}'
                  f'{" · archivé" if archived else ""}</div>', unsafe_allow_html=True)
    if action.button("Actualiser", icon=":material/refresh:", width="stretch", disabled=archived,
                     key=f"refresh_{instrument_id}"):
        with st.spinner("Interrogation des sources…"):
            with context.session() as s:
                result = market_data.refresh_instrument(s, referential.get_instrument(s, instrument_id),
                                                        context.connectors())
        st.toast("Instrument actualisé." if result.ok else " ".join(result.messages), icon="✅" if result.ok else "⚠️")
        st.rerun(scope="fragment")

    period = st.segmented_control("Période", list(PERIOD_DAYS), default="1 an", label_visibility="collapsed",
                                  key=f"period_{instrument_id}") or "1 an"
    change = row.perf.get(period) if period != "Max" else None
    value = theme.money(price.value_num, price.point.currency) if price.has_value else price.status.label
    meta = theme.status(price.status)
    if price.point is not None:
        meta += f" · {theme.day(price.point.reference_date)} · {price.point.source}"
    delta = (f'<span style="color:{theme.tone(change)}">{theme.pct(change)}</span> '
             f'<span class="muted">sur {period} · </span>' if change is not None else "")
    theme.hero("Dernier cours", value, f'{delta}<span class="muted">{escape(meta)}</span>')

    if history:
        days = PERIOD_DAYS[period]
        last_day = history[-1][0]
        shown = [(d, c) for d, c in history if days is None or d >= last_day - timedelta(days=days)]
        st.plotly_chart(theme.line([d for d, _ in shown], [c for _, c in shown], currency=currency, height=280),
                        config=theme.CHART_CONFIG, width="stretch")
    else:
        theme.note("Aucun historique de cours : lancez une actualisation.")
    theme.perf_strip(row.perf)

    for title, frame in sections.items():
        st.markdown(f"#### {title}")
        st.dataframe(frame, hide_index=True, width="stretch")
    st.markdown("#### Identité")
    cols = st.columns(3)
    for index, (key, val) in enumerate(identity.items()):
        cols[index % 3].markdown(f'<div class="anc-kicker">{escape(key)}</div>{escape(val)}', unsafe_allow_html=True)
    if not_applicable:
        theme.note("⚫ Non applicable à ce type d'instrument : " + ", ".join(not_applicable) + ".")


@st.dialog("Fiche instrument", width="large")
def show(instrument_id: int) -> None:
    render(instrument_id)
