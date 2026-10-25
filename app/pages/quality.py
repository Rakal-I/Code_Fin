"""Qualité des données : origine, fraîcheur, erreurs, historique (§8, §14)."""
from collections import Counter

import pandas as pd
import streamlit as st
from sqlalchemy import select

from app.domain.quality import BADGES
from app.models.entities import RefreshLog
from app.models.enums import DataStatus
from app.services import market_data, referential
from app.ui import context, theme, views

theme.header("Qualité des données", "D'où vient chaque chiffre, de quand il date, et ce qui manque.",
             kicker="Marchés")
prefs = context.prefs()

with context.session() as s:
    instruments = referential.list_instruments(s)
    records = []
    for instrument in instruments:
        for (fld, year), cv in market_data.current_values(s, instrument, prefs).items():
            p = cv.point
            records.append({
                "Instrument": views.instrument_label(instrument),
                "Donnée": fld.label,
                "Exercice": str(year) if year else "—",
                "Valeur": views.format_value(cv),
                "Statut": theme.status(cv.status),
                "_status": cv.status,
                "Source": p.source if p else "—",
                "Date de référence": theme.day(p.reference_date) if p else "—",
                "Collecte (UTC)": theme.day(p.collected_at) if p else "—",
                "Remarque": (p.note or "") if p else "",
            })
    logs = s.scalars(select(RefreshLog).where(RefreshLog.ok.is_(False))
                     .order_by(RefreshLog.started_at.desc()).limit(50)).all()
    log_rows = [{
        "Date (UTC)": theme.day(log.started_at),
        "Instrument": log.instrument.name if log.instrument else "Taux de change",
        "Message": log.message,
    } for log in logs]

counts = Counter(r["_status"] for r in records)
statuses_list = list(BADGES)
for start in (0, 4):
    for col, status in zip(st.columns(4), statuses_list[start:start + 4]):
        col.metric(theme.status(status), counts.get(status, 0))
theme.note("Codes : 🟢 valide (réelle, calculée ou manuelle) · 🔵 estimation · 🟠 obsolète · "
           "⚪ non disponible · ⚫ non applicable · 🔴 erreur. Le libellé accompagne toujours la couleur.")

tab_values, tab_errors, tab_history = st.tabs(["Valeurs en vigueur", "Erreurs", "Historique"])

with tab_values:
    if not records:
        st.info("Aucune donnée collectée : lancez une actualisation.")
    else:
        c1, c2 = st.columns(2)
        statuses = c1.multiselect("Statut", [s.label for s in DataStatus], placeholder="Tous les statuts")
        names = c2.multiselect("Instrument", sorted({r["Instrument"] for r in records}),
                               placeholder="Tous les instruments")
        frame = pd.DataFrame(records)
        if statuses:
            frame = frame[frame["_status"].map(lambda st_: st_.label in statuses)]
        if names:
            frame = frame[frame["Instrument"].isin(names)]
        st.dataframe(frame.drop(columns="_status"), hide_index=True, width="stretch")

with tab_errors:
    if log_rows:
        st.dataframe(pd.DataFrame(log_rows), hide_index=True, width="stretch")
    else:
        st.success("Aucune erreur d'actualisation enregistrée.")

with tab_history:
    if not instruments:
        theme.note("Aucun instrument.")
    else:
        labels = {views.instrument_label(i): i.id for i in instruments}
        picked = st.selectbox("Instrument", list(labels), key="history_instrument")
        with context.session() as s:
            points = market_data.data_history(s, labels[picked])
            history = pd.DataFrame([{
                "Collecte (UTC)": theme.day(p.collected_at),
                "Donnée": p.field.label,
                "Exercice": str(p.fiscal_year) if p.fiscal_year else "—",
                "Valeur": theme.number(p.value_num, 4) if p.value_num is not None
                else (p.value_text or (theme.day(p.value_date) if p.value_date else "—")),
                "Devise": p.currency or "—",
                "Statut": theme.status(p.status),
                "Source": p.source,
                "Date de référence": theme.day(p.reference_date),
                "Remarque": p.note or "",
            } for p in points])
        if history.empty:
            theme.note("Aucune collecte pour cet instrument.")
        else:
            st.dataframe(history, hide_index=True, width="stretch")
