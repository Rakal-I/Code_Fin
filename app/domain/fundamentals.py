"""Indicateurs fondamentaux calculés."""
from __future__ import annotations

import re


def potential(target_mean: float | None, price: float | None) -> float | None:
    """Potentiel = (objectif moyen / cours actuel − 1) × 100. ``None`` si une donnée manque."""
    if target_mean is None or price is None or price <= 0 or target_mean <= 0:
        return None
    return (target_mean / price - 1) * 100


_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def is_valid_isin(isin: str) -> bool:
    """Contrôle du format et de la clé de l'ISIN (algorithme de Luhn)."""
    isin = isin.strip().upper()
    if not _ISIN.match(isin):
        return False
    digits = "".join(str(int(ch, 36)) for ch in isin[:-1])
    total = 0
    for index, ch in enumerate(reversed(digits)):
        n = int(ch)
        if index % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (10 - total % 10) % 10 == int(isin[-1])
