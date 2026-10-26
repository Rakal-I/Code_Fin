"""Fixtures : base temporaire migrée et fournisseur de données simulé."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.config import settings
from app.connectors.base import ConnectorError, FetchedBar, FetchedValue, InstrumentRef, PriceHistory
from app.database import engine as db_engine
from app.database.engine import dispose_engine, session_factory, upgrade_to_head
from app.models.enums import DataField, DataStatus, EnvelopeType, InstrumentType
from app.models.schemas import EnvelopeIn, InstrumentIn
from app.services import referential, vault, workspace

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


MASTER_KEY = "5a" * 32
USER, PASSWORD = "proprietaire", "Patrimoine2026"


@pytest.fixture(autouse=True)
def _cle_maitre(monkeypatch):
    """Clé maître de test : jamais le trousseau ni ~/.ancora de la machine."""
    monkeypatch.setenv("ANCORA_MASTER_KEY", MASTER_KEY)
    vault.master_key.cache_clear()
    yield
    vault.master_key.cache_clear()


@pytest.fixture
def app_config(tmp_path: Path, monkeypatch):
    """Dossiers de l'application (données, sauvegardes, journaux) dans un répertoire temporaire."""
    monkeypatch.setenv("ANCORA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ANCORA_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("ANCORA_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ANCORA_KEY_FILE", str(tmp_path / "cle-maitre"))
    settings.get_config.cache_clear()
    yield settings.get_config()
    settings.get_config.cache_clear()
    for path in list(db_engine._engines):
        if tmp_path in path.parents:
            dispose_engine(path)


def make_account(config, username: str | None = USER, password: str = PASSWORD, **fields) -> workspace.Workspace:
    """Crée un compte (identifiant + mot de passe, ou Google / Apple seul si username=None)."""
    with workspace.directory(config) as d:
        if username is None:
            account = workspace.create_account(config, d, **fields)
        else:
            account = workspace.create_account(config, d, username=username, password=password,
                                               confirmation=password, **fields)
        return workspace.open_workspace(config, account)


@pytest.fixture
def directory(app_config):
    with workspace.directory(app_config) as d:
        yield d


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
