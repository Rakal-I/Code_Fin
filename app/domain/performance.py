"""Performances historiques (cahier des charges §6) : aucune extrapolation, aucune estimation."""
from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta

import pandas as pd

# Libellé affiché -> décalage calendaire.
PERIODS: dict[str, pd.DateOffset] = {
    "1 sem.": pd.DateOffset(weeks=1),
    "1 mois": pd.DateOffset(months=1),
    "6 mois": pd.DateOffset(months=6),
    "1 an": pd.DateOffset(years=1),
    "5 ans": pd.DateOffset(years=5),
    "10 ans": pd.DateOffset(years=10),
}

# Écart maximal toléré entre la date cible et le dernier cours connu avant elle
# (week-ends, jours fériés, VL hebdomadaires). Au-delà : N/A, pas d'approximation.
MAX_GAP = timedelta(days=10)


def performances(history: list[tuple[date, float]]) -> dict[str, float | None]:
    """Variation en % entre le dernier cours et le cours à la date de début de période.

    ``None`` (affiché N/A) si l'historique ne couvre pas la période.
    """
    points = sorted((d, c) for d, c in history if c is not None and c > 0)
    if not points:
        return {label: None for label in PERIODS}
    days = [d for d, _ in points]
    last_day, last_close = points[-1]
    result: dict[str, float | None] = {}
    for label, offset in PERIODS.items():
        target = (pd.Timestamp(last_day) - offset).date()
        index = bisect_right(days, target) - 1
        if index < 0 or target - days[index] > MAX_GAP:
            result[label] = None
            continue
        start_close = points[index][1]
        result[label] = (last_close / start_close - 1) * 100
    return result
