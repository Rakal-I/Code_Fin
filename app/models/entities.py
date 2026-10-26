"""Modèles persistants (SQLAlchemy 2)."""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.models.enums import (
    DataField,
    DataStatus,
    EnvelopeType,
    InstrumentSubtype,
    InstrumentType,
    OperationType,
)


def utcnow() -> datetime:
    """Horodatage UTC naïf (SQLite ne stocke pas les fuseaux)."""
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


class Base(DeclarativeBase):
    pass


class Envelope(Base):
    """Enveloppe d'investissement (PEA, assurance-vie, CTO…)."""

    __tablename__ = "envelopes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[EnvelopeType] = mapped_column(Enum(EnvelopeType))
    institution: Mapped[str] = mapped_column(String(120))
    contract: Mapped[str | None] = mapped_column(String(120))
    ref_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    comment: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    positions: Mapped[list[Position]] = relationship(back_populates="envelope")
    operations: Mapped[list[Operation]] = relationship(back_populates="envelope")


class Instrument(Base):
    """Instrument suivi. L'identifiant interne est la seule clé : jamais le ticker."""

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[InstrumentType] = mapped_column(Enum(InstrumentType))
    subtype: Mapped[InstrumentSubtype | None] = mapped_column(Enum(InstrumentSubtype))
    ticker: Mapped[str | None] = mapped_column(String(40))
    provider_symbol: Mapped[str | None] = mapped_column(String(60))
    isin: Mapped[str | None] = mapped_column(String(12))
    exchange: Mapped[str | None] = mapped_column(String(60))
    currency: Mapped[str] = mapped_column(String(3))
    country: Mapped[str | None] = mapped_column(String(60))
    issuer: Mapped[str | None] = mapped_column(String(200))
    watchlist: Mapped[bool] = mapped_column(Boolean, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    data_points: Mapped[list[DataPoint]] = relationship(back_populates="instrument")
    prices: Mapped[list[PriceBar]] = relationship(back_populates="instrument")

    @property
    def symbol(self) -> str | None:
        """Symbole transmis aux fournisseurs (jamais aucune position)."""
        return self.provider_symbol or self.ticker


class DataPoint(Base):
    """Une valeur tracée : valeur, source, date de référence, date de collecte, statut.

    Chaque collecte ajoute une ligne : l'historique est conservé.
    """

    __tablename__ = "data_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    field: Mapped[DataField] = mapped_column(Enum(DataField))
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    value_num: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(String(200))
    value_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(60))
    reference_date: Mapped[date | None] = mapped_column(Date)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[DataStatus] = mapped_column(Enum(DataStatus))
    note: Mapped[str | None] = mapped_column(Text)

    instrument: Mapped[Instrument] = relationship(back_populates="data_points")


class PriceBar(Base):
    """Historique de cours de clôture (ou de VL)."""

    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("instrument_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    close: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(60))
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    instrument: Mapped[Instrument] = relationship(back_populates="prices")


class FxRate(Base):
    """Taux de change : 1 EUR = ``rate`` unités de ``quote``."""

    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("quote", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    base: Mapped[str] = mapped_column(String(3), default="EUR")
    quote: Mapped[str] = mapped_column(String(3), index=True)
    day: Mapped[date] = mapped_column(Date)
    rate: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(60))
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Position(Base):
    """Position existante reprise sans historique de transactions."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("envelope_id", "instrument_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    envelope_id: Mapped[int] = mapped_column(ForeignKey("envelopes.id"))
    quantity: Mapped[float] = mapped_column(Float)
    pru: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    takeover_date: Mapped[date] = mapped_column(Date)
    institution: Mapped[str] = mapped_column(String(120))
    contract: Mapped[str] = mapped_column(String(120))
    fx_rate: Mapped[float | None] = mapped_column(Float)
    fx_date: Mapped[date | None] = mapped_column(Date)
    fx_source: Mapped[str | None] = mapped_column(String(60))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    instrument: Mapped[Instrument] = relationship()
    envelope: Mapped[Envelope] = relationship(back_populates="positions")


class Operation(Base):
    """Opération enregistrée après la reprise."""

    __tablename__ = "operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    type: Mapped[OperationType] = mapped_column(Enum(OperationType))
    envelope_id: Mapped[int] = mapped_column(ForeignKey("envelopes.id"))
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"))
    quantity: Mapped[float | None] = mapped_column(Float)
    unit_price: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    fx_rate: Mapped[float | None] = mapped_column(Float)
    fx_date: Mapped[date | None] = mapped_column(Date)
    fx_source: Mapped[str | None] = mapped_column(String(60))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    instrument: Mapped[Instrument | None] = relationship()
    envelope: Mapped[Envelope] = relationship(back_populates="operations")


class RefreshLog(Base):
    """Journal des actualisations (consultable dans « Qualité des données »)."""

    __tablename__ = "refresh_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    message: Mapped[str | None] = mapped_column(Text)

    instrument: Mapped[Instrument | None] = relationship()


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Account(Base):
    """Compte unique du propriétaire. Le mot de passe n'est jamais stocké, seulement son empreinte."""

    __tablename__ = "account"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuthSession(Base):
    """Session de l'application téléphone. Seule l'empreinte du jeton est conservée."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    device: Mapped[str | None] = mapped_column(String(120))
