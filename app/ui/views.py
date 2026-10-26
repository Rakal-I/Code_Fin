"""Briques d'affichage partagées entre les pages."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from app.domain.fundamentals import potential
from app.domain.performance import PERIODS, performances
from app.domain.quality import applicability, is_applicable
from app.models.entities import Instrument
from app.models.enums import VALUED_STATUSES, Applicability, DataField, DataStatus
from app.services.market_data import CurrentValue, current_values, price_history
from app.services.referential import Preferences
from app.ui import formatting as fmt

COMPUTED_SOURCE = "Calcul Ancora"


def instrument_label(instrument: Instrument) -> str:
    code = instrument.ticker or instrument.isin or ""
    suffix = " · archivé" if instrument.archived else ""
    return f"{instrument.name} ({code}){suffix}" if code else f"{instrument.name}{suffix}"


def format_value(cv: CurrentValue, masked: bool = False) -> str:
    """Valeur lisible ; sans valeur, le statut est affiché à la place (jamais 0)."""
    p = cv.point
    if not cv.has_value or p is None:
        return cv.status.label
    if cv.field == DataField.TER:
        return fmt.pct(p.value_num, signed=False)
    if cv.field in (DataField.ANALYSTS, DataField.DIVIDEND_ANALYSTS):
        return fmt.number(p.value_num, 0)
    if cv.field == DataField.AUM:
        return f"{fmt.number(p.value_num / 1e6, 0)} M{fmt.symbol(p.currency or '')}"
    if p.value_date is not None:
        return fmt.day(p.value_date)
    if p.value_text is not None:
        return p.value_text
    return fmt.money(p.value_num, p.currency or "", masked=False)


@dataclass
class MarketRow:
    instrument: Instrument
    price: CurrentValue
    perf: dict[str, float | None]
    target: CurrentValue | None
    potential: float | None


def market_row(session: Session, instrument: Instrument, prefs: Preferences, today: date | None = None) -> MarketRow:
    values = current_values(session, instrument, prefs, today)
    price = values.get((DataField.PRICE, None)) or CurrentValue(None, DataStatus.NON_DISPONIBLE, DataField.PRICE)
    target = values.get((DataField.TARGET_MEAN, None))
    pot = None
    if target and target.has_value and price.has_value and target.point.currency == price.point.currency:
        pot = potential(target.value_num, price.value_num)
    return MarketRow(instrument=instrument, price=price, perf=performances(price_history(session, instrument.id)),
                     target=target, potential=pot)


def market_frame(rows: list[MarketRow]) -> pd.DataFrame:
    records = []
    for r in rows:
        p = r.price.point
        target_applicable = is_applicable(DataField.TARGET_MEAN, r.instrument.type)
        record = {
            "Instrument": instrument_label(r.instrument),
            "Type": r.instrument.type.label,
            "Cours": r.price.value_num,
            "Devise": (p.currency if p and p.currency else r.instrument.currency),
            "Date": fmt.day(p.reference_date) if p and r.price.has_value else "—",
            "Statut": fmt.status(r.price.status),
        }
        for label in PERIODS:
            record[label] = r.perf[label]
        record["Potentiel"] = r.potential if target_applicable else None
        record["_pot_na"] = not target_applicable
        records.append(record)
    return pd.DataFrame(records)


def fundamentals_sections(session: Session, instrument: Instrument, prefs: Preferences,
                          today: date | None = None) -> dict[str, pd.DataFrame]:
    """Tableaux par thème : chaque ligne porte valeur, statut, source et dates."""
    values = current_values(session, instrument, prefs, today)
    t = instrument.type

    def row(label: str, cv: CurrentValue | None, fld: DataField, year: int | None = None) -> dict:
        if cv is None:
            status = DataStatus.NON_APPLICABLE if not is_applicable(fld, t) else DataStatus.NON_DISPONIBLE
            cv = CurrentValue(None, status, fld, year)
        p = cv.point
        return {
            "Donnée": label,
            "Exercice": str(year or (p.fiscal_year if p and p.fiscal_year else "")) or "—",
            "Valeur": format_value(cv),
            "Statut": fmt.status(cv.status),
            "Source": p.source if p else "—",
            "Date de référence": fmt.day(p.reference_date) if p else "—",
            "Collecte": fmt.day(p.collected_at) if p else "—",
            "Remarque": (p.note or "") if p else "",
        }

    sections: dict[str, pd.DataFrame] = {}
    if is_applicable(DataField.DIVIDEND_N, t):
        rows = []
        for fld in (DataField.DIVIDEND_LAST, DataField.DIVIDEND_N, DataField.DIVIDEND_N1, DataField.DIVIDEND_ANALYSTS,
                    DataField.EX_DATE, DataField.PAYMENT_DATE):
            matches = [cv for (f, _y), cv in values.items() if f == fld]
            rows.append(row(fld.label, max(matches, key=_freshness) if matches else None, fld))
        sections["Dividendes"] = pd.DataFrame(rows)

    if is_applicable(DataField.EPS, t):
        eps = {y: cv for (f, y), cv in values.items() if f == DataField.EPS and y is not None}
        estimated = [y for y, cv in eps.items() if cv.status == DataStatus.ESTIMEE]
        reported = [y for y, cv in eps.items() if cv.status in VALUED_STATUSES and cv.status != DataStatus.ESTIMEE]
        if estimated:
            current_year = min(estimated)
        else:
            current_year = max(reported) + 1 if reported else (today or date.today()).year
        rows = []
        for offset in (-3, -2, -1, 0, 1):
            year = current_year + offset
            label = "Y" if offset == 0 else f"Y{offset:+d}"
            rows.append(row(f"BNA {label}", eps.get(year), DataField.EPS, year))
        sections["Bénéfice net par action"] = pd.DataFrame(rows)

    if is_applicable(DataField.TARGET_MEAN, t):
        rows = [row(f.label, values.get((f, None)), f) for f in
                (DataField.TARGET_MEAN, DataField.TARGET_LOW, DataField.TARGET_HIGH, DataField.ANALYSTS)]
        price = values.get((DataField.PRICE, None))
        target = values.get((DataField.TARGET_MEAN, None))
        pot = None
        if target and target.has_value and price and price.has_value and target.point.currency == price.point.currency:
            pot = potential(target.value_num, price.value_num)
        rows.append({
            "Donnée": "Potentiel", "Exercice": "—",
            "Valeur": fmt.pct(pot, na=DataStatus.NON_DISPONIBLE.label),
            "Statut": fmt.status(DataStatus.CALCULEE if pot is not None else DataStatus.NON_DISPONIBLE),
            "Source": COMPUTED_SOURCE if pot is not None else "—", "Date de référence": "—", "Collecte": "—",
            "Remarque": "(Objectif moyen / cours actuel − 1) × 100",
        })
        sections["Consensus des analystes"] = pd.DataFrame(rows)

    if is_applicable(DataField.TER, t):
        rows = [row(f.label, values.get((f, None)), f) for f in (DataField.TER, DataField.AUM, DataField.MANAGER)]
        sections["Caractéristiques du fonds"] = pd.DataFrame(rows)
    return sections


def _freshness(cv: CurrentValue):
    p = cv.point
    return (cv.status in VALUED_STATUSES, p.reference_date or date.min if p else date.min)


def not_applicable_fields(instrument: Instrument) -> list[str]:
    return [f.label for f in DataField
            if applicability(f, instrument.type) in (Applicability.NON, Applicability.NON_APPLICABLE)]
