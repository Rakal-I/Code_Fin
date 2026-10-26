"""Référentiel : instruments, enveloppes, paramètres."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.quality import DEFAULT_FUNDAMENTAL_STALE_DAYS, DEFAULT_PRICE_STALE_DAYS
from app.models.entities import (
    DataPoint,
    Envelope,
    Instrument,
    Operation,
    Position,
    PriceBar,
    Setting,
    utcnow,
)
from app.models.enums import InstrumentType
from app.models.schemas import EnvelopeIn, InstrumentIn


class BusinessError(ValueError):
    """Règle métier non respectée (message affichable tel quel)."""


# --------------------------------------------------------------------------
# Instruments
# --------------------------------------------------------------------------

def list_instruments(session: Session, include_archived: bool = False) -> list[Instrument]:
    query = select(Instrument).order_by(Instrument.type, Instrument.name)
    if not include_archived:
        query = query.where(Instrument.archived.is_(False))
    return list(session.scalars(query))


def get_instrument(session: Session, instrument_id: int) -> Instrument:
    instrument = session.get(Instrument, instrument_id)
    if instrument is None:
        raise BusinessError("Instrument introuvable.")
    return instrument


def _check_duplicate(session: Session, data: InstrumentIn, exclude_id: int | None = None) -> None:
    """Un même ISIN peut être coté sur plusieurs places : le doublon, c'est ISIN + place + devise."""
    if not data.isin:
        return
    query = select(Instrument).where(
        Instrument.isin == data.isin,
        func.coalesce(Instrument.exchange, "") == (data.exchange or ""),
        Instrument.currency == data.currency,
    )
    if exclude_id is not None:
        query = query.where(Instrument.id != exclude_id)
    if session.scalars(query).first():
        raise BusinessError("Cet instrument existe déjà (même ISIN, même place de cotation, même devise).")


def create_instrument(session: Session, data: InstrumentIn) -> Instrument:
    _check_duplicate(session, data)
    instrument = Instrument(**data.model_dump())
    session.add(instrument)
    session.flush()
    return instrument


def update_instrument(session: Session, instrument_id: int, data: InstrumentIn) -> Instrument:
    instrument = get_instrument(session, instrument_id)
    _check_duplicate(session, data, exclude_id=instrument_id)
    for key, value in data.model_dump().items():
        setattr(instrument, key, value)
    session.flush()
    return instrument


def instrument_has_history(session: Session, instrument_id: int) -> bool:
    """Position, opération ou historique : l'instrument ne peut plus être supprimé (§15)."""
    for model, column in ((Position, Position.instrument_id), (Operation, Operation.instrument_id),
                          (PriceBar, PriceBar.instrument_id), (DataPoint, DataPoint.instrument_id)):
        if session.scalar(select(func.count()).select_from(model).where(column == instrument_id)):
            return True
    return False


def archive_instrument(session: Session, instrument_id: int) -> None:
    instrument = get_instrument(session, instrument_id)
    instrument.archived = True
    instrument.archived_at = utcnow()
    instrument.watchlist = False


def unarchive_instrument(session: Session, instrument_id: int) -> None:
    instrument = get_instrument(session, instrument_id)
    instrument.archived = False
    instrument.archived_at = None


def remove_instrument(session: Session, instrument_id: int) -> str:
    """Supprime un instrument sans historique ; sinon l'archive. Renvoie l'action effectuée."""
    if instrument_has_history(session, instrument_id):
        archive_instrument(session, instrument_id)
        return "archivé"
    session.delete(get_instrument(session, instrument_id))
    return "supprimé"


DEFAULT_INDICES = [
    ("CAC 40", "^FCHI", "EUR", "France"),
    ("Euro Stoxx 50", "^STOXX50E", "EUR", "Zone euro"),
    ("S&P 500", "^GSPC", "USD", "États-Unis"),
    ("Nasdaq Composite", "^IXIC", "USD", "États-Unis"),
    ("MSCI World", "^990100-USD-STRD", "USD", "Monde"),
    ("MSCI Emerging Markets", "^891800-USD-STRD", "USD", "Émergents"),
]


def seed_default_indices(session: Session) -> int:
    """Ajoute les indices de référence au premier lancement uniquement."""
    if get_setting(session, "indices_seeded") == "1":
        return 0
    added = 0
    for name, symbol, currency, country in DEFAULT_INDICES:
        exists = session.scalars(select(Instrument).where(Instrument.ticker == symbol)).first()
        if not exists:
            session.add(Instrument(name=name, type=InstrumentType.INDICE, ticker=symbol, currency=currency,
                                   country=country, watchlist=True))
            added += 1
    set_setting(session, "indices_seeded", "1")
    return added


# --------------------------------------------------------------------------
# Enveloppes
# --------------------------------------------------------------------------

def list_envelopes(session: Session, include_archived: bool = False) -> list[Envelope]:
    query = select(Envelope).order_by(Envelope.type, Envelope.name)
    if not include_archived:
        query = query.where(Envelope.archived.is_(False))
    return list(session.scalars(query))


def get_envelope(session: Session, envelope_id: int) -> Envelope:
    envelope = session.get(Envelope, envelope_id)
    if envelope is None:
        raise BusinessError("Enveloppe introuvable.")
    return envelope


def create_envelope(session: Session, data: EnvelopeIn) -> Envelope:
    envelope = Envelope(**data.model_dump())
    session.add(envelope)
    session.flush()
    return envelope


def update_envelope(session: Session, envelope_id: int, data: EnvelopeIn) -> Envelope:
    envelope = get_envelope(session, envelope_id)
    for key, value in data.model_dump().items():
        setattr(envelope, key, value)
    session.flush()
    return envelope


def set_envelope_archived(session: Session, envelope_id: int, archived: bool) -> None:
    get_envelope(session, envelope_id).archived = archived


# --------------------------------------------------------------------------
# Paramètres
# --------------------------------------------------------------------------

def get_setting(session: Session, key: str, default: str | None = None) -> str | None:
    setting = session.get(Setting, key)
    return setting.value if setting else default


def set_setting(session: Session, key: str, value: str) -> None:
    setting = session.get(Setting, key)
    if setting:
        setting.value = value
    else:
        session.add(Setting(key=key, value=value))


@dataclass(frozen=True)
class Preferences:
    mask_amounts: bool = False
    price_stale_days: int = DEFAULT_PRICE_STALE_DAYS
    fundamental_stale_days: int = DEFAULT_FUNDAMENTAL_STALE_DAYS


def get_preferences(session: Session) -> Preferences:
    return Preferences(
        mask_amounts=get_setting(session, "mask_amounts", "0") == "1",
        price_stale_days=int(get_setting(session, "price_stale_days", str(DEFAULT_PRICE_STALE_DAYS))),
        fundamental_stale_days=int(get_setting(session, "fundamental_stale_days",
                                               str(DEFAULT_FUNDAMENTAL_STALE_DAYS))),
    )


def save_preferences(session: Session, prefs: Preferences) -> None:
    set_setting(session, "mask_amounts", "1" if prefs.mask_amounts else "0")
    set_setting(session, "price_stale_days", str(max(1, prefs.price_stale_days)))
    set_setting(session, "fundamental_stale_days", str(max(1, prefs.fundamental_stale_days)))
