"""Formats à la française, partagés par l'interface ordinateur et l'interface téléphone.

Une valeur absente s'affiche avec un libellé (« — », « N/A », « Non disponible ») :
elle n'est jamais remplacée par 0.
"""
from __future__ import annotations

import math
from datetime import date, datetime

from app.domain.quality import badge
from app.models.enums import DataStatus

MASK = "••••"


def missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def number(value: float | None, decimals: int = 2, na: str = "—") -> str:
    if missing(value):
        return na
    text = f"{value:,.{decimals}f}"
    return text.replace(",", " ").replace(".", ",")


def money(value: float | None, currency: str = "EUR", masked: bool = False, decimals: int = 2,
          na: str = "—", signed: bool = False) -> str:
    if missing(value):
        return na
    if masked:
        return f"{MASK} {symbol(currency)}"
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{number(value, decimals)} {symbol(currency)}"


def symbol(currency: str) -> str:
    return {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF", "JPY": "¥"}.get(currency, currency)


def pct(value: float | None, decimals: int = 2, na: str = "N/A", signed: bool = True) -> str:
    if missing(value):
        return na
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{number(value, decimals)} %"


def qty(value: float | None, masked: bool = False) -> str:
    if missing(value):
        return "—"
    if masked:
        return MASK
    return number(value, 0 if float(value).is_integer() else 4)


def day(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    return value.strftime("%d/%m/%Y")


def status(value: DataStatus) -> str:
    return badge(value)
