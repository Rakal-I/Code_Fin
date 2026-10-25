"""Données de marché : actualisation, sélection de la valeur courante, taux de change.

Règles (cahier des charges §8, §13, §21) :
- chaque collecte est historisée avec sa source, ses dates et son statut ;
- une donnée applicable que personne ne fournit est enregistrée « Non disponible », jamais 0 ;
- un échec de fournisseur est enregistré « Erreur » et reste visible ;
- l'interface ne dépend jamais d'un fournisseur : elle lit la base locale.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.settings import CONSOLIDATION_CURRENCY
from app.connectors.base import Connector, ConnectorError, FetchedValue, InstrumentRef
from app.connectors.registry import MANUAL_SOURCE
from app.domain.quality import applicable_fields, effective_status, status_rank
from app.models.entities import (
    DataPoint,
    FxRate,
    Instrument,
    Operation,
    Position,
    PriceBar,
    RefreshLog,
    utcnow,
)
from app.models.enums import VALUED_STATUSES, DataField, DataStatus
from app.models.schemas import ManualValueIn
from app.services.referential import Preferences

log = logging.getLogger(__name__)

HISTORY_YEARS = 10
FX_MAX_GAP_DAYS = 7


def today_utc() -> date:
    return datetime.now(UTC).date()


# --------------------------------------------------------------------------
# Lecture : valeur courante d'un champ
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CurrentValue:
    point: DataPoint | None
    status: DataStatus            # statut affiché (obsolescence comprise)
    field: DataField
    fiscal_year: int | None = None

    @property
    def value_num(self) -> float | None:
        return self.point.value_num if self.point and self.status in VALUED_STATUSES + (DataStatus.OBSOLETE,) else None

    @property
    def has_value(self) -> bool:
        return self.point is not None and self.status in VALUED_STATUSES + (DataStatus.OBSOLETE,)


def current_values(session: Session, instrument: Instrument, prefs: Preferences,
                   today: date | None = None) -> dict[tuple[DataField, int | None], CurrentValue]:
    """Meilleure valeur par (champ, exercice) parmi les sources.

    Pour chaque source on retient sa dernière valeur exploitable (sinon sa dernière
    tentative), puis on départage : statut, date de référence, date de collecte.
    """
    today = today or today_utc()
    points = session.scalars(
        select(DataPoint).where(DataPoint.instrument_id == instrument.id).order_by(DataPoint.collected_at, DataPoint.id)
    ).all()
    per_source: dict[tuple, DataPoint] = {}
    for p in points:
        key = (p.field, p.fiscal_year, p.source)
        previous = per_source.get(key)
        if previous is None or p.status in VALUED_STATUSES or previous.status not in VALUED_STATUSES:
            per_source[key] = p

    best: dict[tuple[DataField, int | None], CurrentValue] = {}
    for (fld, year, _source), p in per_source.items():
        status = effective_status(p.status, p.reference_date, fld, today,
                                  prefs.price_stale_days, prefs.fundamental_stale_days)
        candidate = CurrentValue(point=p, status=status, field=fld, fiscal_year=year)
        current = best.get((fld, year))
        if current is None or _better(candidate, current):
            best[(fld, year)] = candidate

    # Un « Non disponible » sans exercice n'a plus lieu d'être si un exercice a une valeur.
    valued_fields = {f for (f, y), cv in best.items() if y is not None and cv.has_value}
    return {k: v for k, v in best.items() if not (k[1] is None and k[0] in valued_fields and not v.has_value)}


def _better(a: CurrentValue, b: CurrentValue) -> bool:
    def key(cv: CurrentValue):
        p = cv.point
        return (status_rank(cv.status), -(p.reference_date or date.min).toordinal(),
                -p.collected_at.timestamp())
    return key(a) < key(b)


def current_price(session: Session, instrument: Instrument, prefs: Preferences,
                  today: date | None = None) -> CurrentValue:
    values = current_values(session, instrument, prefs, today)
    return values.get((DataField.PRICE, None)) or CurrentValue(None, DataStatus.NON_DISPONIBLE, DataField.PRICE)


def price_history(session: Session, instrument_id: int) -> list[tuple[date, float]]:
    rows = session.execute(
        select(PriceBar.day, PriceBar.close).where(PriceBar.instrument_id == instrument_id).order_by(PriceBar.day)
    ).all()
    return [(d, c) for d, c in rows]


def data_history(session: Session, instrument_id: int) -> list[DataPoint]:
    return list(session.scalars(
        select(DataPoint).where(DataPoint.instrument_id == instrument_id).order_by(DataPoint.collected_at.desc())
    ))


# --------------------------------------------------------------------------
# Taux de change (1 EUR = rate devise)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FxQuote:
    rate: float
    day: date | None
    source: str


def fx_on(session: Session, currency: str, day: date) -> FxQuote | None:
    """Taux connu le jour donné ou dans les jours ouvrés qui précèdent ; sinon inconnu."""
    if currency == CONSOLIDATION_CURRENCY:
        return FxQuote(1.0, day, "Identité")
    row = session.scalars(
        select(FxRate).where(FxRate.quote == currency, FxRate.day <= day,
                             FxRate.day >= day - timedelta(days=FX_MAX_GAP_DAYS)).order_by(FxRate.day.desc())
    ).first()
    return FxQuote(row.rate, row.day, row.source) if row else None


def latest_fx(session: Session, currency: str) -> FxQuote | None:
    if currency == CONSOLIDATION_CURRENCY:
        return FxQuote(1.0, None, "Identité")
    row = session.scalars(select(FxRate).where(FxRate.quote == currency).order_by(FxRate.day.desc())).first()
    return FxQuote(row.rate, row.day, row.source) if row else None


# --------------------------------------------------------------------------
# Écriture
# --------------------------------------------------------------------------

def _store_value(session: Session, instrument: Instrument, value: FetchedValue, source: str) -> None:
    """Ajoute la valeur à l'historique, sauf si elle est identique à la dernière de cette source."""
    same_year = (DataPoint.fiscal_year.is_(None) if value.fiscal_year is None
                 else DataPoint.fiscal_year == value.fiscal_year)
    last = session.scalars(
        select(DataPoint).where(
            DataPoint.instrument_id == instrument.id, DataPoint.field == value.field, same_year,
            DataPoint.source == source,
        ).order_by(DataPoint.collected_at.desc(), DataPoint.id.desc())
    ).first()
    same = last is not None and (
        last.status == value.status and last.value_num == value.value_num and last.value_text == value.value_text
        and last.value_date == value.value_date and last.reference_date == value.reference_date
    )
    if same:
        last.collected_at = utcnow()
        last.note = value.note
        return
    session.add(DataPoint(
        instrument_id=instrument.id, field=value.field, fiscal_year=value.fiscal_year, value_num=value.value_num,
        value_text=value.value_text, value_date=value.value_date, currency=value.currency, source=source,
        reference_date=value.reference_date, status=value.status, note=value.note, collected_at=utcnow(),
    ))


def _has_valued(session: Session, instrument_id: int, fld: DataField) -> bool:
    return bool(session.scalar(select(func.count()).select_from(DataPoint).where(
        DataPoint.instrument_id == instrument_id, DataPoint.field == fld,
        DataPoint.status.in_(VALUED_STATUSES))))


def _upsert_bars(session: Session, instrument: Instrument, bars, currency: str, source: str) -> int:
    if not bars:
        return 0
    first = min(b.day for b in bars)
    existing = {pb.day: pb for pb in session.scalars(
        select(PriceBar).where(PriceBar.instrument_id == instrument.id, PriceBar.day >= first))}
    for bar in bars:
        if bar.day in existing:
            existing[bar.day].close = bar.close
            existing[bar.day].currency = currency
            existing[bar.day].source = source
        else:
            session.add(PriceBar(instrument_id=instrument.id, day=bar.day, close=bar.close, currency=currency,
                                 source=source, collected_at=utcnow()))
    return len(bars)


@dataclass
class RefreshResult:
    instrument: str
    ok: bool = True
    messages: list[str] = field(default_factory=list)


def instrument_ref(instrument: Instrument) -> InstrumentRef:
    """Seule l'identité publique de l'instrument est transmise aux fournisseurs."""
    return InstrumentRef(symbol=instrument.symbol or instrument.isin or "", isin=instrument.isin,
                         type=instrument.type, currency=instrument.currency, country=instrument.country)


def refresh_instrument(session: Session, instrument: Instrument, connectors: list[Connector],
                       today: date | None = None) -> RefreshResult:
    today = today or today_utc()
    result = RefreshResult(instrument=instrument.name)
    log_row = RefreshLog(instrument_id=instrument.id, started_at=utcnow())
    session.add(log_row)
    active = [c for c in connectors if c.enabled]
    ref = instrument_ref(instrument)

    if not ref.symbol:
        result.ok = False
        result.messages.append("Aucun symbole : renseignez un ticker ou une saisie manuelle.")
    else:
        _refresh_price(session, instrument, ref, active, today, result)
        _refresh_fundamentals(session, instrument, ref, active, today, result)

    log_row.finished_at = utcnow()
    log_row.ok = result.ok
    log_row.message = " ".join(result.messages) or "Actualisation réussie."
    if not result.ok:
        log.warning("Actualisation incomplète pour l'instrument #%s : %s", instrument.id, log_row.message)
    return result


def _refresh_price(session, instrument, ref, connectors, today, result) -> None:
    last_day = session.scalar(select(func.max(PriceBar.day)).where(PriceBar.instrument_id == instrument.id))
    if last_day:
        start = last_day - timedelta(days=7)
    else:
        start = today.replace(year=today.year - HISTORY_YEARS) - timedelta(days=15)
    errors = []
    for connector in connectors:
        try:
            history = connector.price_history(ref, start)
        except ConnectorError as exc:
            errors.append(f"{connector.name} : {exc}")
            continue
        if not history.bars:
            errors.append(f"{connector.name} : aucun cours.")
            continue
        _upsert_bars(session, instrument, history.bars, history.currency, connector.name)
        last = max(history.bars, key=lambda b: b.day)
        note = None
        if history.currency != instrument.currency:
            note = f"Cotation en {history.currency} (instrument déclaré en {instrument.currency})."
        _store_value(session, instrument, FetchedValue(
            field=DataField.PRICE, status=DataStatus.REELLE, value_num=last.close, currency=history.currency,
            reference_date=last.day, note=note), connector.name)
        return
    result.ok = False
    message = " ; ".join(errors) or "Aucun fournisseur actif."
    result.messages.append(f"Cours : {message}")
    _store_value(session, instrument, FetchedValue(field=DataField.PRICE, status=DataStatus.ERREUR,
                                                   reference_date=today, note=message),
                 connectors[0].name if connectors else MANUAL_SOURCE)


def _refresh_fundamentals(session, instrument, ref, connectors, today, result) -> None:
    fields = [f for f in applicable_fields(instrument.type) if f != DataField.PRICE]
    if not fields:
        return
    provided: set[DataField] = set()
    failures: list[str] = []
    for connector in connectors:
        try:
            values = connector.fundamentals(ref)
        except ConnectorError as exc:
            failures.append(f"{connector.name} : {exc}")
            continue
        for value in values:
            if value.field in fields:
                _store_value(session, instrument, value, connector.name)
                provided.add(value.field)
    primary_failed = bool(failures) and connectors and failures[0].startswith(connectors[0].name)
    if primary_failed:
        result.ok = False
        result.messages.append(f"Fondamentaux : {failures[0]}")
    for fld in fields:
        if fld in provided or _has_valued(session, instrument.id, fld):
            continue
        if primary_failed:
            value = FetchedValue(field=fld, status=DataStatus.ERREUR, reference_date=today, note=failures[0])
        else:
            value = FetchedValue(field=fld, status=DataStatus.NON_DISPONIBLE, reference_date=today,
                                 note="Non fourni par les sources gratuites configurées.")
        _store_value(session, instrument, value, connectors[0].name if connectors else MANUAL_SOURCE)


def needed_currencies(session: Session) -> dict[str, date]:
    """Devises à suivre et date de début nécessaire (plus ancienne position ou opération)."""
    needed: dict[str, date] = {}
    today = today_utc()

    def need(currency: str, day: date):
        if currency and currency != CONSOLIDATION_CURRENCY:
            needed[currency] = min(needed.get(currency, day), day)

    for inst in session.scalars(select(Instrument).where(Instrument.archived.is_(False))):
        need(inst.currency, today - timedelta(days=30))
    for pos in session.scalars(select(Position)):
        need(pos.currency, pos.takeover_date)
    for op in session.scalars(select(Operation)):
        need(op.currency, op.day)
    return needed


def refresh_fx(session: Session, connectors: list[Connector], today: date | None = None) -> list[str]:
    today = today or today_utc()
    errors = []
    for currency, first_day in needed_currencies(session).items():
        last_day = session.scalar(select(func.max(FxRate.day)).where(FxRate.quote == currency))
        first_known = session.scalar(select(func.min(FxRate.day)).where(FxRate.quote == currency))
        if last_day and first_known and first_known <= first_day:
            start = last_day - timedelta(days=7)
        else:
            start = first_day - timedelta(days=FX_MAX_GAP_DAYS + 3)
        last_error = f"Taux EUR/{currency} : aucun fournisseur actif."
        for connector in [c for c in connectors if c.enabled]:
            try:
                bars = connector.fx_history(currency, start)
            except ConnectorError as exc:
                last_error = f"Taux EUR/{currency} ({connector.name}) : {exc}"
                continue
            existing = {r.day: r for r in session.scalars(
                select(FxRate).where(FxRate.quote == currency, FxRate.day >= start))}
            for bar in bars:
                if bar.day in existing:
                    existing[bar.day].rate = bar.close
                else:
                    session.add(FxRate(base=CONSOLIDATION_CURRENCY, quote=currency, day=bar.day, rate=bar.close,
                                       source=connector.name, collected_at=utcnow()))
            break
        else:
            errors.append(last_error)
    if errors:
        session.add(RefreshLog(instrument_id=None, ok=False, message=" ; ".join(errors), finished_at=utcnow()))
    return errors


def refresh_all(session: Session, connectors: list[Connector], today: date | None = None,
                progress: Callable[[int, int, str], None] | None = None) -> list[RefreshResult]:
    instruments = list(session.scalars(select(Instrument).where(Instrument.archived.is_(False))))
    results = []
    fx_errors = refresh_fx(session, connectors, today)
    session.commit()
    for index, instrument in enumerate(instruments, start=1):
        if progress:
            progress(index, len(instruments), instrument.name)
        results.append(refresh_instrument(session, instrument, connectors, today))
        session.commit()  # chaque instrument est enregistré même si le suivant échoue
    if fx_errors:
        results.append(RefreshResult(instrument="Taux de change", ok=False, messages=fx_errors))
    return results


def record_manual_value(session: Session, data: ManualValueIn) -> None:
    instrument = session.get(Instrument, data.instrument_id)
    if instrument is None:
        raise ValueError("Instrument introuvable.")
    _store_value(session, instrument, FetchedValue(
        field=data.field, status=DataStatus.MANUELLE, value_num=data.value_num, value_text=data.value_text,
        value_date=data.value_date, currency=data.currency, fiscal_year=data.fiscal_year,
        reference_date=data.reference_date, note=data.note), MANUAL_SOURCE)


def stale_prices(session: Session, prefs: Preferences, today: date | None = None) -> list[Instrument]:
    """Instruments dont le cours n'est pas à jour (vérification au démarrage)."""
    today = today or today_utc()
    stale = []
    for instrument in session.scalars(select(Instrument).where(Instrument.archived.is_(False))):
        price = current_price(session, instrument, prefs, today)
        if price.status not in VALUED_STATUSES:
            stale.append(instrument)
    return stale


def last_refresh(session: Session) -> datetime | None:
    return session.scalar(select(func.max(RefreshLog.finished_at)))
