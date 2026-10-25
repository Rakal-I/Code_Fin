"""Saisie : positions initiales, opérations, données manuelles (§9, §10)."""
from datetime import date

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from app.connectors.registry import MANUAL_SOURCE
from app.domain.quality import applicable_fields
from app.models.enums import (
    INCOME_OPERATIONS,
    DataField,
    OperationType,
)
from app.models.schemas import ManualValueIn, OperationIn, PositionIn
from app.services import market_data, referential
from app.services import portfolio as pf
from app.services.referential import BusinessError
from app.ui import context, theme, views

theme.header("Saisie", "Positions existantes, opérations et données de secours.", kicker="Gestion")
prefs = context.prefs()
masked = prefs.mask_amounts

with context.session() as s:
    envelopes = referential.list_envelopes(s)
    instruments = [i for i in referential.list_instruments(s) if i.type.name != "INDICE"]

if not envelopes or not instruments:
    st.info("Créez d'abord au moins une enveloppe et un instrument dans « Administration ».")
    theme.link("app/pages/admin.py", "Administration", icon=":material/tune:")
    st.stop()

env_labels = {f"{e.name} · {e.institution}": e for e in envelopes}
inst_labels = {views.instrument_label(i): i for i in instruments}


def show_errors(exc: Exception) -> None:
    if isinstance(exc, ValidationError):
        for error in exc.errors():
            message = str(error.get("msg", "")).removeprefix("Value error, ")
            field = ".".join(str(x) for x in error.get("loc", ()))
            st.error(f"{message}" + (f" ({field})" if field else ""))
    else:
        st.error(str(exc))


def fx_input(currency: str, key: str) -> float | None:
    if currency == "EUR":
        return None
    value = st.number_input(f"Taux de change : 1 EUR = … {currency} (facultatif)", min_value=0.0, value=0.0,
                            format="%.6f", key=key,
                            help="Laissé à 0, le taux enregistré pour cette date est utilisé s'il est connu.")
    return value or None


tab_op, tab_pos, tab_manual, tab_journal = st.tabs(["Opération", "Position initiale", "Donnée manuelle", "Journal"])

with tab_op:
    kind = st.segmented_control("Type d'opération", [t.label for t in OperationType], default="Achat")
    op_type = next(t for t in OperationType if t.label == (kind or "Achat"))
    # Choix hors formulaire : la devise proposée et le champ de change suivent l'instrument choisi.
    c1, c2 = st.columns(2)
    envelope = env_labels[c1.selectbox("Enveloppe", list(env_labels), key="op_env")]
    needs_instrument = op_type not in (OperationType.APPORT, OperationType.RETRAIT, OperationType.FRAIS)
    options = list(inst_labels) if needs_instrument else ["—"] + list(inst_labels)
    instrument = inst_labels.get(c2.selectbox("Instrument", options, key=f"op_inst_{needs_instrument}"))
    default_ccy = instrument.currency if instrument else envelope.ref_currency
    with st.form("operation", clear_on_submit=True, border=False):
        c3, c4, c5, c6, c7 = st.columns(5)
        day = c3.date_input("Date", value=date.today(), format="DD/MM/YYYY")
        quantity = unit_price = amount = None
        if op_type in (OperationType.ACHAT, OperationType.VENTE):
            quantity = c4.number_input("Quantité", min_value=0.0, step=1.0, format="%.4f")
            unit_price = c5.number_input("Prix unitaire", min_value=0.0, format="%.4f")
        elif op_type == OperationType.CORRECTION:
            quantity = c4.number_input("Écart de quantité (±)", step=1.0, format="%.4f") or None
            unit_price = c5.number_input("Nouveau PRU (0 = inchangé)", min_value=0.0, format="%.4f") or None
        else:
            amount = c4.number_input("Montant", min_value=0.0, format="%.2f")
        currency = c6.text_input("Devise", value=default_ccy, max_chars=3, key=f"op_ccy_{default_ccy}")
        fees = c7.number_input("Frais", min_value=0.0, format="%.2f")
        fx = fx_input(default_ccy, "op_fx")
        comment = st.text_input("Commentaire")
        if st.form_submit_button("Enregistrer l'opération", type="primary"):
            try:
                data = OperationIn(day=day, type=op_type, envelope_id=envelope.id,
                                   instrument_id=instrument.id if instrument else None, quantity=quantity,
                                   unit_price=unit_price, amount=amount, currency=currency, fees=fees,
                                   fx_rate=fx, fx_source=MANUAL_SOURCE if fx else None,
                                   fx_date=day if fx else None, comment=comment)
                with context.session() as s:
                    pf.create_operation(s, data)
                st.success(f"Opération « {op_type.label} » enregistrée.")
            except (ValidationError, BusinessError) as exc:
                show_errors(exc)
    if op_type in INCOME_OPERATIONS:
        theme.note("Saisissez le montant effectivement perçu.")
    if op_type == OperationType.CORRECTION:
        theme.note("Une correction ajuste la quantité au PRU courant et/ou redéfinit le PRU de la ligne.")

with tab_pos:
    theme.note("Pour reprendre une position existante sans son historique de transactions. "
               "Tous les champs sont obligatoires, sauf le taux de change et le commentaire.")
    c1, c2 = st.columns(2)
    instrument = inst_labels[c1.selectbox("Instrument", list(inst_labels), key="pos_inst")]
    envelope = env_labels[c2.selectbox("Enveloppe", list(env_labels), key="pos_env")]
    with st.form("position", clear_on_submit=True, border=False):
        c3, c4, c5, c6 = st.columns(4)
        quantity = c3.number_input("Quantité", min_value=0.0, step=1.0, format="%.4f")
        pru = c4.number_input("PRU", min_value=0.0, format="%.4f")
        currency = c5.text_input("Devise", value=instrument.currency, max_chars=3,
                                 key=f"pos_ccy_{instrument.id}")
        takeover = c6.date_input("Date de reprise", value=date.today(), format="DD/MM/YYYY")
        c7, c8 = st.columns(2)
        institution = c7.text_input("Établissement", value=envelope.institution, key=f"pos_inst_{envelope.id}")
        contract = c8.text_input("Contrat", value=envelope.contract or "", key=f"pos_ctr_{envelope.id}")
        fx = fx_input(instrument.currency, "pos_fx")
        comment = st.text_input("Commentaire", key="pos_comment")
        if st.form_submit_button("Créer la position", type="primary"):
            try:
                data = PositionIn(instrument_id=instrument.id, envelope_id=envelope.id, quantity=quantity, pru=pru,
                                  currency=currency, takeover_date=takeover, institution=institution,
                                  contract=contract, fx_rate=fx, fx_date=takeover if fx else None,
                                  fx_source=MANUAL_SOURCE if fx else None, comment=comment)
                with context.session() as s:
                    pf.create_position(s, data)
                st.success("Position créée.")
            except (ValidationError, BusinessError) as exc:
                show_errors(exc)

with tab_manual:
    theme.note("Source de secours : la valeur est enregistrée avec le statut « Manuelle » et sa date. "
               "La valeur la plus fiable et la plus récente, toutes sources confondues, est affichée.")
    instrument = inst_labels.get(st.selectbox("Instrument", list(inst_labels), key="man_inst"))
    fields = [f for f in applicable_fields(instrument.type)]
    fld = next(f for f in fields if f.label == st.selectbox("Donnée", [f.label for f in fields]))
    with st.form("manual", clear_on_submit=True, border=False):
        c1, c2, c3 = st.columns(3)
        value_num = value_text = value_date = None
        if fld in (DataField.EX_DATE, DataField.PAYMENT_DATE):
            value_date = c1.date_input("Date", format="DD/MM/YYYY")
        elif fld == DataField.MANAGER:
            value_text = c1.text_input("Valeur")
        else:
            value_num = c1.number_input("Valeur", format="%.4f")
        currency = c2.text_input("Devise", value=instrument.currency, max_chars=3, key="man_ccy")
        fiscal_year = c3.number_input("Exercice fiscal (0 = sans objet)", min_value=0, max_value=2200,
                                      value=0, step=1)
        reference = st.date_input("Date de référence", value=date.today(), format="DD/MM/YYYY")
        note = st.text_input("Remarque (origine de l'information)")
        if st.form_submit_button("Enregistrer la donnée", type="primary"):
            try:
                data = ManualValueIn(instrument_id=instrument.id, field=fld, value_num=value_num,
                                     value_text=value_text, value_date=value_date, currency=currency,
                                     fiscal_year=fiscal_year or None, reference_date=reference, note=note)
                with context.session() as s:
                    market_data.record_manual_value(s, data)
                st.success("Donnée manuelle enregistrée.")
            except (ValidationError, ValueError) as exc:
                show_errors(exc)

with tab_journal:
    with context.session() as s:
        operations = pf.list_operations(s)
        positions = pf.list_positions(s)
        op_rows = [{
            "id": op.id, "Date": op.day.strftime("%d/%m/%Y"), "Type": op.type.label, "Enveloppe": op.envelope.name,
            "Instrument": op.instrument.name if op.instrument else "—",
            "Quantité": theme.qty(op.quantity, masked), "Prix": theme.number(op.unit_price, 4),
            "Montant": theme.MASK if masked and op.amount is not None else theme.number(op.amount, 2),
            "Devise": op.currency, "Frais": theme.number(op.fees, 2), "Commentaire": op.comment or "",
        } for op in operations]
        pos_rows = [{
            "id": p.id, "Reprise": p.takeover_date.strftime("%d/%m/%Y"), "Instrument": p.instrument.name,
            "Enveloppe": p.envelope.name, "Quantité": theme.qty(p.quantity, masked), "PRU": theme.number(p.pru, 4),
            "Devise": p.currency, "Établissement": p.institution, "Contrat": p.contract,
        } for p in positions]

    st.subheader("Opérations")
    if op_rows:
        st.dataframe(pd.DataFrame(op_rows).drop(columns="id"), hide_index=True, width="stretch")
        with st.expander("Supprimer une opération saisie par erreur"):
            labels = {f"{r['Date']} · {r['Type']} · {r['Instrument']} · {r['Enveloppe']}": r["id"] for r in op_rows}
            picked = st.selectbox("Opération", list(labels), key="del_op")
            if st.button("Supprimer cette opération", key="del_op_btn"):
                with context.session() as s:
                    pf.delete_operation(s, labels[picked])
                st.rerun()
            theme.note("Pour une rectification qui doit rester tracée, préférez une opération « Correction ».")
    else:
        theme.note("Aucune opération.")

    st.subheader("Positions initiales")
    if pos_rows:
        st.dataframe(pd.DataFrame(pos_rows).drop(columns="id"), hide_index=True, width="stretch")
        with st.expander("Supprimer une position initiale saisie par erreur"):
            labels = {f"{r['Instrument']} · {r['Enveloppe']}": r["id"] for r in pos_rows}
            picked = st.selectbox("Position", list(labels), key="del_pos")
            if st.button("Supprimer cette position", key="del_pos_btn"):
                with context.session() as s:
                    pf.delete_position(s, labels[picked])
                st.rerun()
    else:
        theme.note("Aucune position initiale.")
