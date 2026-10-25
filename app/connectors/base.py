"""Contrat commun aux fournisseurs de données.

Un connecteur ne reçoit que l'identité publique d'un instrument
(symbole, ISIN, type, devise) : aucune position ni montant ne lui est transmis.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol

from pydantic import BaseModel

from app.models.enums import DataField, DataStatus, InstrumentType


class ConnectorError(Exception):
    """Échec d'un fournisseur (réseau, accès refusé, symbole inconnu…)."""


class InstrumentRef(BaseModel):
    symbol: str
    isin: str | None = None
    type: InstrumentType
    currency: str
    country: str | None = None


class FetchedValue(BaseModel):
    field: DataField
    status: DataStatus
    value_num: float | None = None
    value_text: str | None = None
    value_date: date | None = None
    currency: str | None = None
    fiscal_year: int | None = None
    reference_date: date | None = None
    note: str | None = None


class FetchedBar(BaseModel):
    day: date
    close: float


class PriceHistory(BaseModel):
    currency: str
    bars: list[FetchedBar]


class Connector(Protocol):
    name: str

    @property
    def enabled(self) -> bool: ...

    def price_history(self, ref: InstrumentRef, start: date) -> PriceHistory: ...

    def fundamentals(self, ref: InstrumentRef) -> list[FetchedValue]: ...

    def fx_history(self, quote: str, start: date) -> list[FetchedBar]: ...
