"""Schémas de saisie validés (Pydantic)."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.fundamentals import is_valid_isin
from app.models.enums import (
    SUBTYPES_BY_TYPE,
    DataField,
    EnvelopeType,
    InstrumentSubtype,
    InstrumentType,
    OperationType,
)


def _currency(value: str) -> str:
    value = (value or "").strip().upper()
    if len(value) != 3 or not value.isalpha():
        raise ValueError("La devise doit être un code ISO à 3 lettres (EUR, USD…).")
    return value


def _blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class EnvelopeIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: EnvelopeType
    institution: str = Field(min_length=1, max_length=120)
    contract: str | None = None
    ref_currency: str = "EUR"
    comment: str | None = None

    _blank = field_validator("contract", "comment", mode="before")(_blank_to_none)
    _ccy = field_validator("ref_currency")(_currency)


class InstrumentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: InstrumentType
    subtype: InstrumentSubtype | None = None
    ticker: str | None = None
    provider_symbol: str | None = None
    isin: str | None = None
    exchange: str | None = None
    currency: str
    country: str | None = None
    issuer: str | None = None
    watchlist: bool = True

    _blank = field_validator("subtype", "ticker", "provider_symbol", "isin", "exchange", "country", "issuer",
                             mode="before")(_blank_to_none)
    _ccy = field_validator("currency")(_currency)

    @field_validator("isin")
    @classmethod
    def _isin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not is_valid_isin(value):
            raise ValueError("ISIN invalide (format ou clé de contrôle).")
        return value

    @model_validator(mode="after")
    def _coherence(self):
        if self.subtype is not None and self.subtype not in SUBTYPES_BY_TYPE[self.type]:
            raise ValueError(f"Le sous-type « {self.subtype.label} » ne correspond pas au type « {self.type.label} ».")
        if not (self.ticker or self.provider_symbol or self.isin):
            raise ValueError("Renseignez au moins un ticker, un symbole fournisseur ou un ISIN.")
        return self


class PositionIn(BaseModel):
    """Position existante sans historique : tous les champs du §9 sont obligatoires."""

    instrument_id: int
    envelope_id: int
    quantity: float = Field(gt=0)
    pru: float = Field(ge=0)
    currency: str
    takeover_date: date
    institution: str = Field(min_length=1)
    contract: str = Field(min_length=1)
    fx_rate: float | None = Field(default=None, gt=0)
    fx_date: date | None = None
    fx_source: str | None = None
    comment: str | None = None

    _ccy = field_validator("currency")(_currency)
    _blank = field_validator("fx_source", "comment", mode="before")(_blank_to_none)


class OperationIn(BaseModel):
    day: date
    type: OperationType
    envelope_id: int
    instrument_id: int | None = None
    quantity: float | None = None
    unit_price: float | None = Field(default=None, ge=0)
    amount: float | None = None
    currency: str
    fees: float = Field(default=0.0, ge=0)
    fx_rate: float | None = Field(default=None, gt=0)
    fx_date: date | None = None
    fx_source: str | None = None
    comment: str | None = None

    _ccy = field_validator("currency")(_currency)
    _blank = field_validator("fx_source", "comment", mode="before")(_blank_to_none)

    @model_validator(mode="after")
    def _coherence(self):
        t = self.type
        if t in (OperationType.ACHAT, OperationType.VENTE):
            if self.instrument_id is None:
                raise ValueError("Un achat ou une vente porte sur un instrument.")
            if not self.quantity or self.quantity <= 0 or self.unit_price is None:
                raise ValueError("Quantité (> 0) et prix unitaire obligatoires.")
            self.amount = self.quantity * self.unit_price
        elif t in (OperationType.DIVIDENDE, OperationType.DISTRIBUTION, OperationType.COUPON):
            if self.instrument_id is None:
                raise ValueError("Un revenu est rattaché à un instrument.")
            if self.amount is None or self.amount <= 0:
                raise ValueError("Montant perçu (> 0) obligatoire.")
        elif t in (OperationType.APPORT, OperationType.RETRAIT, OperationType.FRAIS):
            if self.amount is None or self.amount <= 0:
                raise ValueError("Montant (> 0) obligatoire.")
        elif t == OperationType.CORRECTION:
            if self.instrument_id is None:
                raise ValueError("Une correction porte sur un instrument.")
            if not self.quantity and self.unit_price is None:
                raise ValueError("Indiquez un écart de quantité et/ou un nouveau PRU.")
        return self


class ManualValueIn(BaseModel):
    """Saisie manuelle (source de secours)."""

    instrument_id: int
    field: DataField
    value_num: float | None = None
    value_text: str | None = None
    value_date: date | None = None
    currency: str | None = None
    fiscal_year: int | None = Field(default=None, ge=1900, le=2200)
    reference_date: date
    note: str | None = None

    _blank = field_validator("value_text", "currency", "note", mode="before")(_blank_to_none)

    @model_validator(mode="after")
    def _has_value(self):
        if self.value_num is None and self.value_text is None and self.value_date is None:
            raise ValueError("Saisissez une valeur.")
        if self.field == DataField.EPS and self.fiscal_year is None:
            raise ValueError("Un BNA doit être associé à son exercice fiscal.")
        return self
