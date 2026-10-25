"""Calculs patrimoniaux (cahier des charges §11 et §12).

Conventions :
- PRU : prix de revient moyen pondéré, frais d'achat inclus.
- Vente : diminue la quantité, ne modifie pas le PRU, génère une plus-value réalisée.
- Taux de change : 1 EUR = ``fx`` unités de la devise (montant en EUR = montant / fx).
- Une valeur inconnue reste ``None`` : jamais remplacée par 0 ni estimée.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.models.enums import OperationType

EPSILON = 1e-9


@dataclass(frozen=True)
class TradeEvent:
    """Mouvement de titres : achat, vente ou correction."""

    day: date
    kind: OperationType
    quantity: float | None = None
    unit_price: float | None = None
    fees: float = 0.0
    fx: float | None = None  # devise par EUR à la date de l'opération
    ref: int | None = None   # identifiant de l'opération d'origine


@dataclass
class HoldingState:
    """État d'une ligne (un instrument dans une enveloppe)."""

    quantity: float = 0.0
    cost: float = 0.0               # coût d'acquisition restant, devise de l'actif
    cost_eur: float | None = 0.0    # même coût en EUR, None si un taux manque
    realized: float = 0.0           # plus-values réalisées, devise de l'actif
    realized_eur: float | None = 0.0
    last_pru: float | None = None   # PRU conservé après clôture de la ligne
    errors: list[str] = field(default_factory=list)

    @property
    def pru(self) -> float | None:
        if self.quantity > EPSILON:
            return self.cost / self.quantity
        return self.last_pru

    @property
    def is_open(self) -> bool:
        return self.quantity > EPSILON


def _to_eur(amount: float, fx: float | None) -> float | None:
    if fx is None or fx <= 0:
        return None
    return amount / fx


def build_holding(
    initial_quantity: float | None = None,
    initial_pru: float | None = None,
    initial_fx: float | None = None,
    events: list[TradeEvent] | None = None,
) -> HoldingState:
    """Rejoue la position initiale puis les opérations dans l'ordre chronologique."""
    state = HoldingState()
    if initial_quantity:
        state.quantity = initial_quantity
        state.cost = initial_quantity * (initial_pru or 0.0)
        state.cost_eur = _to_eur(state.cost, initial_fx)
        state.last_pru = initial_pru

    for event in sorted(events or [], key=lambda e: (e.day, e.ref or 0)):
        if event.kind == OperationType.ACHAT:
            _buy(state, event)
        elif event.kind == OperationType.VENTE:
            _sell(state, event)
        elif event.kind == OperationType.CORRECTION:
            _correct(state, event)
    return state


def _buy(state: HoldingState, event: TradeEvent) -> None:
    if not event.quantity or event.quantity <= 0 or event.unit_price is None or event.unit_price < 0:
        state.errors.append(f"Achat du {event.day:%d/%m/%Y} ignoré : quantité ou prix invalide.")
        return
    gross = event.quantity * event.unit_price + (event.fees or 0.0)
    state.quantity += event.quantity
    state.cost += gross
    gross_eur = _to_eur(gross, event.fx)
    state.cost_eur = None if state.cost_eur is None or gross_eur is None else state.cost_eur + gross_eur
    state.last_pru = state.cost / state.quantity


def _sell(state: HoldingState, event: TradeEvent) -> None:
    if not event.quantity or event.quantity <= 0 or event.unit_price is None:
        state.errors.append(f"Vente du {event.day:%d/%m/%Y} ignorée : quantité ou prix invalide.")
        return
    if event.quantity > state.quantity + EPSILON:
        state.errors.append(
            f"Vente du {event.day:%d/%m/%Y} ignorée : quantité vendue supérieure à la quantité détenue."
        )
        return
    pru = state.cost / state.quantity
    share = event.quantity / state.quantity
    proceeds = event.quantity * event.unit_price - (event.fees or 0.0)
    cost_sold = event.quantity * pru
    state.realized += proceeds - cost_sold

    proceeds_eur = _to_eur(proceeds, event.fx)
    if state.cost_eur is None or proceeds_eur is None or state.realized_eur is None:
        state.realized_eur = None
        cost_sold_eur = None
    else:
        cost_sold_eur = state.cost_eur * share
        state.realized_eur += proceeds_eur - cost_sold_eur

    state.quantity -= event.quantity
    state.cost -= cost_sold
    if state.cost_eur is not None:
        state.cost_eur = state.cost_eur - (cost_sold_eur if cost_sold_eur is not None else state.cost_eur * share)
    if state.quantity <= EPSILON:  # ligne soldée : on évite les résidus d'arrondi
        state.quantity, state.cost = 0.0, 0.0
        state.cost_eur = 0.0 if state.cost_eur is not None else None
    state.last_pru = pru  # le PRU de la quantité restante est inchangé


def _correct(state: HoldingState, event: TradeEvent) -> None:
    """Correction : ajuste la quantité (au PRU courant) et/ou redéfinit le PRU."""
    pru = state.pru or 0.0
    avg_fx = state.cost / state.cost_eur if state.cost_eur else None
    if event.quantity:
        new_quantity = state.quantity + event.quantity
        if new_quantity < -EPSILON:
            state.errors.append(f"Correction du {event.day:%d/%m/%Y} ignorée : quantité négative.")
            return
        state.quantity = max(new_quantity, 0.0)
        state.cost = state.quantity * pru
    if event.unit_price is not None:
        pru = event.unit_price
        state.cost = state.quantity * pru
        state.last_pru = pru
        avg_fx = event.fx or avg_fx
    if state.cost_eur is not None:
        state.cost_eur = _to_eur(state.cost, avg_fx) if state.cost else 0.0


@dataclass(frozen=True)
class Valuation:
    quantity: float
    price: float | None
    value: float | None          # devise de l'actif
    value_eur: float | None
    cost: float
    cost_eur: float | None
    gain: float | None           # plus-value latente, devise de l'actif
    gain_pct: float | None       # (valeur / coût − 1) × 100, devise de l'actif
    gain_eur: float | None
    gain_eur_pct: float | None
    market_effect_eur: float | None
    fx_effect_eur: float | None


def value_holding(state: HoldingState, price: float | None, fx_now: float | None) -> Valuation:
    """Valorisation = quantité × cours. Plus-value = valeur − coût d'acquisition.

    En EUR, la plus-value se décompose en effet de marché (variation du cours,
    convertie au taux moyen d'acquisition) et effet de change (le reste).
    """
    quantity = state.quantity
    value = quantity * price if price is not None else None
    value_eur = _to_eur(value, fx_now) if value is not None else None
    gain = value - state.cost if value is not None else None
    gain_pct = (value / state.cost - 1) * 100 if value is not None and state.cost > EPSILON else None

    gain_eur = gain_eur_pct = market = fx_effect = None
    if value_eur is not None and state.cost_eur is not None:
        gain_eur = value_eur - state.cost_eur
        if state.cost_eur > EPSILON:
            gain_eur_pct = (value_eur / state.cost_eur - 1) * 100
            market = gain * state.cost_eur / state.cost if gain is not None and state.cost > EPSILON else None
            fx_effect = gain_eur - market if market is not None else None

    return Valuation(
        quantity=quantity,
        price=price,
        value=value,
        value_eur=value_eur,
        cost=state.cost,
        cost_eur=state.cost_eur,
        gain=gain,
        gain_pct=gain_pct,
        gain_eur=gain_eur,
        gain_eur_pct=gain_eur_pct,
        market_effect_eur=market,
        fx_effect_eur=fx_effect,
    )
