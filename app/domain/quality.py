"""Qualité des données : applicabilité, fraîcheur, statuts et codes visuels."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.models.enums import (
    VALUED_STATUSES,
    Applicability,
    DataField,
    DataStatus,
    InstrumentType,
)

A, T = Applicability, InstrumentType

# Annexe A du cahier des charges. Colonnes : Action, ETF, Fonds/UC, Indice.
_MATRIX: dict[DataField, tuple[Applicability, Applicability, Applicability, Applicability]] = {
    DataField.PRICE: (A.OUI, A.OUI, A.OUI, A.OUI),
    DataField.DIVIDEND_LAST: (A.OUI, A.VARIABLE, A.VARIABLE, A.NON),
    DataField.DIVIDEND_N: (A.OUI, A.RARE, A.RARE, A.NON),
    DataField.DIVIDEND_N1: (A.OUI, A.RARE, A.RARE, A.NON),
    DataField.DIVIDEND_ANALYSTS: (A.OUI, A.RARE, A.RARE, A.NON),
    DataField.EX_DATE: (A.OUI, A.VARIABLE, A.NON, A.NON),
    DataField.PAYMENT_DATE: (A.OUI, A.VARIABLE, A.NON, A.NON),
    DataField.EPS: (A.OUI, A.NON_APPLICABLE, A.NON_APPLICABLE, A.NON_APPLICABLE),
    DataField.TARGET_MEAN: (A.OUI, A.RARE, A.NON_APPLICABLE, A.NON_APPLICABLE),
    DataField.TARGET_LOW: (A.OUI, A.RARE, A.NON_APPLICABLE, A.NON_APPLICABLE),
    DataField.TARGET_HIGH: (A.OUI, A.RARE, A.NON_APPLICABLE, A.NON_APPLICABLE),
    DataField.ANALYSTS: (A.OUI, A.RARE, A.NON_APPLICABLE, A.NON_APPLICABLE),
    DataField.TER: (A.NON_APPLICABLE, A.OUI, A.OUI, A.NON_APPLICABLE),
    DataField.AUM: (A.NON_APPLICABLE, A.OUI, A.OUI, A.NON_APPLICABLE),
    DataField.MANAGER: (A.NON_APPLICABLE, A.OUI, A.OUI, A.NON_APPLICABLE),
}
_COLUMN = {T.ACTION: 0, T.ETF: 1, T.FONDS: 2, T.UC: 2, T.INDICE: 3}


def applicability(field: DataField, instrument_type: InstrumentType) -> Applicability:
    return _MATRIX[field][_COLUMN[instrument_type]]


def is_applicable(field: DataField, instrument_type: InstrumentType) -> bool:
    return applicability(field, instrument_type) not in (A.NON, A.NON_APPLICABLE)


def applicable_fields(instrument_type: InstrumentType) -> list[DataField]:
    return [f for f in DataField if is_applicable(f, instrument_type)]


# Fraîcheur : au-delà de ce nombre de jours, une valeur devient « Obsolète ».
DEFAULT_PRICE_STALE_DAYS = 7
DEFAULT_FUNDAMENTAL_STALE_DAYS = 400


def effective_status(
    status: DataStatus,
    reference_date: date | None,
    field: DataField,
    today: date,
    price_stale_days: int = DEFAULT_PRICE_STALE_DAYS,
    fundamental_stale_days: int = DEFAULT_FUNDAMENTAL_STALE_DAYS,
) -> DataStatus:
    """Statut affiché : une valeur trop ancienne passe en « Obsolète »."""
    if status not in VALUED_STATUSES or reference_date is None:
        return status
    if field in (DataField.EPS, DataField.EX_DATE, DataField.PAYMENT_DATE, DataField.DIVIDEND_N,
                 DataField.DIVIDEND_N1, DataField.DIVIDEND_LAST):
        return status  # valeurs rattachées à un exercice ou à une date : jamais périmées par l'âge
    limit = price_stale_days if field == DataField.PRICE else fundamental_stale_days
    return DataStatus.OBSOLETE if (today - reference_date).days > limit else status


@dataclass(frozen=True)
class Badge:
    emoji: str
    meaning: str


# Codes visuels (§16). Le libellé accompagne toujours la couleur.
BADGES: dict[DataStatus, Badge] = {
    DataStatus.REELLE: Badge("🟢", "Valide"),
    DataStatus.CALCULEE: Badge("🟢", "Valide"),
    DataStatus.MANUELLE: Badge("🟢", "Valide"),
    DataStatus.ESTIMEE: Badge("🔵", "Estimation"),
    DataStatus.OBSOLETE: Badge("🟠", "Obsolète"),
    DataStatus.NON_DISPONIBLE: Badge("⚪", "Non disponible"),
    DataStatus.NON_APPLICABLE: Badge("⚫", "Non applicable"),
    DataStatus.ERREUR: Badge("🔴", "Erreur"),
}


def badge(status: DataStatus) -> str:
    return f"{BADGES[status].emoji} {status.label}"


# Ordre de préférence quand plusieurs sources proposent une valeur.
_STATUS_RANK = {
    DataStatus.REELLE: 0,
    DataStatus.MANUELLE: 1,
    DataStatus.CALCULEE: 2,
    DataStatus.ESTIMEE: 3,
    DataStatus.OBSOLETE: 4,
    DataStatus.ERREUR: 5,
    DataStatus.NON_DISPONIBLE: 6,
    DataStatus.NON_APPLICABLE: 7,
}


def status_rank(status: DataStatus) -> int:
    return _STATUS_RANK[status]
