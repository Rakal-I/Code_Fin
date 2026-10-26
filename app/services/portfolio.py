"""Positions, opérations et vues consolidées du patrimoine."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.portfolio import HoldingState, TradeEvent, Valuation, build_holding, value_holding
from app.models.entities import Envelope, Instrument, Operation, Position
from app.models.enums import INCOME_OPERATIONS, TRADE_OPERATIONS, DataStatus, OperationType
from app.models.schemas import OperationIn, PositionIn
from app.services.market_data import FxQuote, current_price, fx_on, latest_fx, today_utc
from app.services.referential import BusinessError, Preferences, get_envelope, get_instrument

# --------------------------------------------------------------------------
# Saisie
# --------------------------------------------------------------------------


def _line_currency(session: Session, envelope_id: int, instrument_id: int) -> str | None:
    position = session.scalars(select(Position).where(
        Position.envelope_id == envelope_id, Position.instrument_id == instrument_id)).first()
    if position:
        return position.currency
    op = session.scalars(select(Operation).where(
        Operation.envelope_id == envelope_id, Operation.instrument_id == instrument_id,
        Operation.type.in_(TRADE_OPERATIONS)).order_by(Operation.day, Operation.id)).first()
    return op.currency if op else None


def create_position(session: Session, data: PositionIn) -> Position:
    get_instrument(session, data.instrument_id)
    get_envelope(session, data.envelope_id)
    exists = session.scalars(select(Position).where(
        Position.envelope_id == data.envelope_id, Position.instrument_id == data.instrument_id)).first()
    if exists:
        raise BusinessError("Une position initiale existe déjà pour cet instrument dans cette enveloppe.")
    currency = _line_currency(session, data.envelope_id, data.instrument_id)
    if currency and currency != data.currency:
        raise BusinessError(f"Cette ligne est déjà suivie en {currency}.")
    position = Position(**data.model_dump())
    session.add(position)
    session.flush()
    return position


def delete_position(session: Session, position_id: int) -> None:
    position = session.get(Position, position_id)
    if position is None:
        raise BusinessError("Position introuvable.")
    session.delete(position)


def create_operation(session: Session, data: OperationIn) -> Operation:
    get_envelope(session, data.envelope_id)
    if data.instrument_id is not None:
        get_instrument(session, data.instrument_id)
    errors_before: list[str] = []
    if data.type in TRADE_OPERATIONS:
        currency = _line_currency(session, data.envelope_id, data.instrument_id)
        if currency and currency != data.currency:
            raise BusinessError(f"Cette ligne est suivie en {currency} : saisissez l'opération dans cette devise.")
        errors_before = _state_for(session, data.envelope_id, data.instrument_id).errors
    operation = Operation(**data.model_dump())
    session.add(operation)
    session.flush()
    if data.type in TRADE_OPERATIONS:
        new_errors = [e for e in _state_for(session, data.envelope_id, data.instrument_id).errors
                      if e not in errors_before]
        if new_errors:
            # L'opération rendrait l'historique incohérent (ex. vente supérieure au stock) : refusée.
            session.delete(operation)
            session.flush()
            raise BusinessError(new_errors[0].replace(" ignorée", " refusée").replace(" ignoré", " refusé"))
    return operation


def delete_operation(session: Session, operation_id: int) -> None:
    operation = session.get(Operation, operation_id)
    if operation is None:
        raise BusinessError("Opération introuvable.")
    session.delete(operation)


def list_operations(session: Session) -> list[Operation]:
    return list(session.scalars(select(Operation).order_by(Operation.day.desc(), Operation.id.desc())))


def list_positions(session: Session) -> list[Position]:
    return list(session.scalars(select(Position).order_by(Position.envelope_id, Position.instrument_id)))


# --------------------------------------------------------------------------
# Lignes du portefeuille
# --------------------------------------------------------------------------


def _fx_for(session: Session, explicit: float | None, currency: str, day: date) -> float | None:
    if explicit:
        return explicit
    quote = fx_on(session, currency, day)
    return quote.rate if quote else None


def _events(session: Session, envelope_id: int, instrument_id: int) -> list[Operation]:
    return list(session.scalars(select(Operation).where(
        Operation.envelope_id == envelope_id, Operation.instrument_id == instrument_id,
        Operation.type.in_(TRADE_OPERATIONS))))


def _state_for(session: Session, envelope_id: int, instrument_id: int) -> HoldingState:
    position = session.scalars(select(Position).where(
        Position.envelope_id == envelope_id, Position.instrument_id == instrument_id)).first()
    return _build_state(session, position, _events(session, envelope_id, instrument_id))


def _build_state(session: Session, position: Position | None, ops: list[Operation]) -> HoldingState:
    events = [TradeEvent(day=op.day, kind=op.type, quantity=op.quantity, unit_price=op.unit_price, fees=op.fees or 0.0,
                         fx=_fx_for(session, op.fx_rate, op.currency, op.day), ref=op.id) for op in ops]
    if position is None:
        return build_holding(events=events)
    initial_fx = _fx_for(session, position.fx_rate, position.currency, position.takeover_date)
    return build_holding(position.quantity, position.pru, initial_fx, events)


@dataclass
class HoldingView:
    envelope: Envelope
    instrument: Instrument
    currency: str
    state: HoldingState
    valuation: Valuation
    price_status: DataStatus
    price_date: date | None
    price_source: str | None
    fx_now: FxQuote | None
    issues: list[str] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.state.is_open


def _convert(session: Session, amount: float, from_ccy: str, to_ccy: str) -> float | None:
    if from_ccy == to_ccy:
        return amount
    a, b = latest_fx(session, from_ccy), latest_fx(session, to_ccy)
    if a is None or b is None:
        return None
    return amount / a.rate * b.rate


def holdings(session: Session, prefs: Preferences, today: date | None = None,
             include_closed: bool = False) -> list[HoldingView]:
    today = today or today_utc()
    lines: dict[tuple[int, int], dict] = defaultdict(lambda: {"position": None, "ops": []})
    for position in session.scalars(select(Position)):
        lines[(position.envelope_id, position.instrument_id)]["position"] = position
    for op in session.scalars(select(Operation).where(Operation.type.in_(TRADE_OPERATIONS))):
        lines[(op.envelope_id, op.instrument_id)]["ops"].append(op)

    views: list[HoldingView] = []
    for (envelope_id, instrument_id), line in lines.items():
        envelope, instrument = session.get(Envelope, envelope_id), session.get(Instrument, instrument_id)
        position, ops = line["position"], line["ops"]
        currency = position.currency if position else sorted(ops, key=lambda o: (o.day, o.id))[0].currency
        state = _build_state(session, position, ops)
        issues = list(state.errors)

        price_cv = current_price(session, instrument, prefs, today)
        price = price_cv.value_num
        if price is not None and price_cv.point.currency and price_cv.point.currency != currency:
            converted = _convert(session, price, price_cv.point.currency, currency)
            issues.append(f"Cours coté en {price_cv.point.currency}, converti en {currency}.")
            price = converted
        if price is None:
            issues.append("Cours indisponible : ligne non valorisée.")
        fx_now = latest_fx(session, currency)
        if fx_now is None:
            issues.append(f"Taux EUR/{currency} inconnu : montants en EUR non disponibles.")
        if state.cost_eur is None:
            issues.append(f"Taux EUR/{currency} manquant à une date d'achat : coût en EUR non disponible.")
        valuation = value_holding(state, price, fx_now.rate if fx_now else None)
        view = HoldingView(envelope=envelope, instrument=instrument, currency=currency, state=state,
                           valuation=valuation, price_status=price_cv.status,
                           price_date=price_cv.point.reference_date if price_cv.point else None,
                           price_source=price_cv.point.source if price_cv.point else None,
                           fx_now=fx_now, issues=issues)
        if view.is_open or include_closed:
            views.append(view)
    return sorted(views, key=lambda v: (v.envelope.name, v.instrument.name))


@dataclass
class Summary:
    value_eur: float = 0.0
    cost_eur: float = 0.0
    gain_eur: float = 0.0
    realized_eur: float = 0.0
    unvalued_lines: int = 0
    lines: int = 0
    by_envelope: dict[str, float] = field(default_factory=dict)
    by_type: dict[str, float] = field(default_factory=dict)

    @property
    def gain_pct(self) -> float | None:
        return (self.value_eur / self.cost_eur - 1) * 100 if self.cost_eur > 0 else None


def summarize(views: list[HoldingView]) -> Summary:
    """Totaux consolidés en EUR. Une ligne non valorisable est comptée à part, jamais à 0."""
    summary = Summary()
    for view in views:
        if view.state.realized_eur is not None:
            summary.realized_eur += view.state.realized_eur
        if not view.is_open:
            continue
        summary.lines += 1
        v = view.valuation
        if v.value_eur is None or v.cost_eur is None:
            summary.unvalued_lines += 1
            continue
        summary.value_eur += v.value_eur
        summary.cost_eur += v.cost_eur
        summary.gain_eur += v.gain_eur
        envelope_label = f"{view.envelope.name}"
        summary.by_envelope[envelope_label] = summary.by_envelope.get(envelope_label, 0.0) + v.value_eur
        type_label = view.instrument.type.label
        summary.by_type[type_label] = summary.by_type.get(type_label, 0.0) + v.value_eur
    return summary


# --------------------------------------------------------------------------
# Revenus et flux
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class IncomeRow:
    day: date
    type: OperationType
    envelope: str
    instrument: str
    amount: float
    currency: str
    amount_eur: float | None


def incomes(session: Session) -> list[IncomeRow]:
    rows = []
    for op in session.scalars(select(Operation).where(Operation.type.in_(INCOME_OPERATIONS)).order_by(Operation.day)):
        fx = _fx_for(session, op.fx_rate, op.currency, op.day)
        rows.append(IncomeRow(day=op.day, type=op.type, envelope=op.envelope.name,
                              instrument=op.instrument.name if op.instrument else "—", amount=op.amount,
                              currency=op.currency, amount_eur=op.amount / fx if fx else None))
    return rows


@dataclass
class CashFlows:
    contributions_eur: float = 0.0
    withdrawals_eur: float = 0.0
    fees_eur: float = 0.0
    unconverted: int = 0


def cash_flows(session: Session, envelope_id: int) -> CashFlows:
    flows = CashFlows()
    for op in session.scalars(select(Operation).where(
            Operation.envelope_id == envelope_id,
            Operation.type.in_((OperationType.APPORT, OperationType.RETRAIT, OperationType.FRAIS)))):
        fx = _fx_for(session, op.fx_rate, op.currency, op.day)
        if not fx:
            flows.unconverted += 1
            continue
        amount = op.amount / fx
        if op.type == OperationType.APPORT:
            flows.contributions_eur += amount
        elif op.type == OperationType.RETRAIT:
            flows.withdrawals_eur += amount
        else:
            flows.fees_eur += amount
    return flows

