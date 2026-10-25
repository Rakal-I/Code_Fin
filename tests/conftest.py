"""Fixtures : base temporaire migrée et fournisseur de données simulé."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.connectors.base import ConnectorError, FetchedBar, FetchedValue, InstrumentRef, PriceHistory
from app.database.engine import dispose_engine, session_factory, upgrade_to_head
from app.models.enums import DataField, DataStatus, EnvelopeType, InstrumentType
from app.models.schemas import EnvelopeIn, InstrumentIn
from app.services import referential

TODAY = date(2026, 10, 23)


class FakeConnector:
    """Fournisseur simulé : cours linéaires, fondamentaux fixes, pannes à la demande."""

    name = "Fournisseur test"
    enabled = True

    def __init__(self, prices: dict[str, float] | None = None, fx: dict[str, float] | None = None):
        self.prices = prices or {}
        self.fx = fx or {}
        self.failing: set[str] = set()
        self.calls: list[InstrumentRef] = []

    def price_history(self, ref: InstrumentRef, start: date) -> PriceHistory:
        self.calls.append(ref)
        if ref.symbol in self.failing or ref.symbol not in self.prices:
            raise ConnectorError("symbole inconnu")
        last = self.prices[ref.symbol]
        days = max((TODAY - start).days, 1)
        bars = [FetchedBar(day=TODAY - timedelta(days=i), close=last * (1 - 0.0001 * i)) for i in range(days)]
        return PriceHistory(currency=ref.currency, bars=bars)

    def fx_history(self, quote: str, start: date) -> list[FetchedBar]:
        if quote not in self.fx:
            raise ConnectorError("devise inconnue")
        return [FetchedBar(day=start + timedelta(days=i), close=self.fx[quote])
                for i in range((TODAY - start).days + 1)]

    def fundamentals(self, ref: InstrumentRef) -> list[FetchedValue]:
        if ref.symbol in self.failing or ref.symbol not in self.prices:
            raise ConnectorError("panne")
        if ref.type != InstrumentType.ACTION:
            return []
        return [
            FetchedValue(field=DataField.TARGET_MEAN, status=DataStatus.ESTIMEE,
                         value_num=self.prices[ref.symbol] * 1.2, currency=ref.currency, reference_date=TODAY),
            FetchedValue(field=DataField.EPS, status=DataStatus.REELLE, value_num=5.0, fiscal_year=2025,
                         reference_date=date(2025, 12, 31)),
        ]


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "ancora.db"
    upgrade_to_head(path)
    yield path
    dispose_engine(path)


@pytest.fixture
def session(db_path):
    s = session_factory(db_path)()
    yield s
    s.close()


@pytest.fixture
def pea(session):
    env = referential.create_envelope(session, EnvelopeIn(name="PEA Bourse", type=EnvelopeType.PEA,
                                                          institution="Banque A", contract="PEA-001"))
    session.commit()
    return env


@pytest.fixture
def cto(session):
    env = referential.create_envelope(session, EnvelopeIn(name="CTO", type=EnvelopeType.CTO,
                                                          institution="Courtier B", contract="CTO-9"))
    session.commit()
    return env


@pytest.fixture
def lvmh(session):
    inst = referential.create_instrument(session, InstrumentIn(
        name="LVMH", type=InstrumentType.ACTION, ticker="MC", provider_symbol="MC.PA", isin="FR0000121014",
        exchange="Euronext Paris", currency="EUR", country="France"))
    session.commit()
    return inst


@pytest.fixture
def apple(session):
    inst = referential.create_instrument(session, InstrumentIn(
        name="Apple", type=InstrumentType.ACTION, ticker="AAPL", isin="US0378331005", exchange="Nasdaq",
        currency="USD", country="États-Unis"))
    session.commit()
    return inst
