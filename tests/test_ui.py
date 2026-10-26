"""Chaque page s'affiche sans erreur, base vide comme base remplie."""
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.config import settings
from app.database.engine import dispose_engine, session_scope, upgrade_to_head
from app.models.enums import EnvelopeType, InstrumentType, OperationType
from app.models.schemas import EnvelopeIn, InstrumentIn, OperationIn, PositionIn
from app.services import market_data, portfolio, referential
from tests.conftest import FakeConnector

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted((ROOT / "app" / "pages").glob("*.py"))


def populate(db_path: Path) -> None:
    with session_scope(db_path) as s:
        referential.seed_default_indices(s)
        pea = referential.create_envelope(s, EnvelopeIn(name="PEA", type=EnvelopeType.PEA, institution="Banque",
                                                        contract="P-1"))
        cto = referential.create_envelope(s, EnvelopeIn(name="CTO", type=EnvelopeType.CTO, institution="Courtier",
                                                        contract="C-1"))
        lvmh = referential.create_instrument(s, InstrumentIn(name="LVMH", type=InstrumentType.ACTION, ticker="MC",
                                                             provider_symbol="MC.PA", isin="FR0000121014",
                                                             currency="EUR"))
        apple = referential.create_instrument(s, InstrumentIn(name="Apple", type=InstrumentType.ACTION,
                                                              ticker="AAPL", currency="USD"))
        etf = referential.create_instrument(s, InstrumentIn(name="MSCI World", type=InstrumentType.ETF,
                                                            ticker="CW8.PA", currency="EUR"))
        portfolio.create_position(s, PositionIn(instrument_id=lvmh.id, envelope_id=pea.id, quantity=10, pru=500,
                                                currency="EUR", takeover_date=date(2025, 1, 2), institution="Banque",
                                                contract="P-1"))
        portfolio.create_position(s, PositionIn(instrument_id=apple.id, envelope_id=cto.id, quantity=5, pru=150,
                                                currency="USD", takeover_date=date(2025, 1, 2),
                                                institution="Courtier", contract="C-1", fx_rate=1.04))
        portfolio.create_operation(s, OperationIn(day=date(2026, 4, 30), type=OperationType.DIVIDENDE,
                                                  envelope_id=pea.id, instrument_id=lvmh.id, amount=75,
                                                  currency="EUR"))
        portfolio.create_operation(s, OperationIn(day=date(2026, 2, 1), type=OperationType.VENTE,
                                                  envelope_id=pea.id, instrument_id=lvmh.id, quantity=2,
                                                  unit_price=600, currency="EUR"))
        connector = FakeConnector({"MC.PA": 380.0, "AAPL": 340.0}, fx={"USD": 1.12})
        connector.failing.add("CW8.PA")
        market_data.refresh_all(s, [connector])
        referential.archive_instrument(s, etf.id)


@pytest.fixture(params=["vide", "remplie"])
def app_env(request, tmp_path, monkeypatch):
    db = tmp_path / "ancora.db"
    monkeypatch.setenv("ANCORA_DB_PATH", str(db))
    monkeypatch.setenv("ANCORA_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("ANCORA_LOG_DIR", str(tmp_path / "logs"))
    settings.get_config.cache_clear()
    upgrade_to_head(db)
    if request.param == "remplie":
        populate(db)
    yield db
    settings.get_config.cache_clear()
    dispose_engine(db)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_page_sans_exception(app_env, page):
    at = AppTest.from_file(str(page), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]


def test_point_d_entree(app_env):
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]


def test_masquage_des_montants(app_env):
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "dashboard.py"), default_timeout=60)
    at.session_state["mask_amounts"] = True
    at.run()
    values = [m.value for m in at.metric]
    if values:
        assert all("••••" in v for v in values)


def _fiche_lvmh():
    from app.ui import fiche
    fiche.render(7)


def test_fiche_instrument(tmp_path, monkeypatch):
    db = tmp_path / "ancora.db"
    monkeypatch.setenv("ANCORA_DB_PATH", str(db))
    monkeypatch.setenv("ANCORA_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("ANCORA_LOG_DIR", str(tmp_path / "logs"))
    settings.get_config.cache_clear()
    upgrade_to_head(db)
    populate(db)
    try:
        at = AppTest.from_function(_fiche_lvmh, default_timeout=60).run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("LVMH" in m.value for m in at.markdown)
    finally:
        settings.get_config.cache_clear()
        dispose_engine(db)


def test_anneau_dans_la_da_du_logo():
    import re

    from app.ui.theme import ring_svg

    svg = ring_svg([50, 30, 20], uid="t")
    assert re.findall(r'stroke-opacity="([\d.]+)"', svg) == ["1.0", "0.62", "0.34"]  # opacités du logo
    assert svg.count('stroke-linecap="round"') == 3


def _main() -> AppTest:
    return AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)


def test_connexion_ordinateur(tmp_path, monkeypatch):
    """Premier lancement : création de l'accès ; ensuite, connexion obligatoire."""
    db = tmp_path / "ancora.db"
    monkeypatch.setenv("ANCORA_DB_PATH", str(db))
    monkeypatch.setenv("ANCORA_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("ANCORA_LOG_DIR", str(tmp_path / "logs"))
    settings.get_config.cache_clear()
    try:
        at = _main().run()
        assert not at.exception
        assert any("Créer mon accès" in b.label for b in at.button)
        assert not any("Tableau de bord" in t.value for t in at.title)  # aucune donnée avant connexion
        at.text_input[0].input("proprietaire")
        at.text_input[1].input("Patrimoine2026")
        at.text_input[2].input("Patrimoine2026")
        at.button[0].click().run()
        assert not at.exception
        assert at.session_state["auth_user"] == "proprietaire"

        # Nouvelle session navigateur : il faut se connecter.
        at = _main().run()
        assert any("Se connecter" in b.label for b in at.button)
        at.text_input[0].input("proprietaire")
        at.text_input[1].input("mauvais")
        at.button[0].click().run()
        assert any("incorrect" in e.value for e in at.error)
        at.text_input[1].input("Patrimoine2026")
        at.button[0].click().run()
        assert not at.exception and at.session_state["auth_user"] == "proprietaire"
    finally:
        settings.get_config.cache_clear()
        dispose_engine(db)
