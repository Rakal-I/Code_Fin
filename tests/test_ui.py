"""Chaque page s'affiche sans erreur, base vide comme base remplie."""
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.models.enums import EnvelopeType, InstrumentType, OperationType
from app.models.schemas import EnvelopeIn, InstrumentIn, OperationIn, PositionIn
from app.services import market_data, portfolio, referential
from app.services.workspace import Workspace
from app.ui.context import ACCOUNT_KEY
from tests.conftest import PASSWORD, USER, FakeConnector, make_account

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted((ROOT / "app" / "pages").glob("*.py"))


def populate(ws: Workspace) -> None:
    with ws.session() as s:
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
def app_env(request, app_config):
    ws = make_account(app_config)
    if request.param == "remplie":
        populate(ws)
    return ws


def run_as(at: AppTest, ws: Workspace) -> AppTest:
    """Session déjà connectée au compte de ws."""
    at.session_state[ACCOUNT_KEY] = ws.account_id
    return at.run()


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_page_sans_exception(app_env, page):
    at = run_as(AppTest.from_file(str(page), default_timeout=60), app_env)
    assert not at.exception, [e.value for e in at.exception]


def test_point_d_entree(app_env):
    at = run_as(_main(), app_env)
    assert not at.exception, [e.value for e in at.exception]


def test_masquage_des_montants(app_env):
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "dashboard.py"), default_timeout=60)
    at.session_state["mask_amounts"] = True
    run_as(at, app_env)
    values = [m.value for m in at.metric]
    if values:
        assert all("••••" in v for v in values)


def _fiche_lvmh():
    from app.ui import fiche
    fiche.render(7)


def test_fiche_instrument(app_config):
    ws = make_account(app_config)
    populate(ws)
    at = run_as(AppTest.from_function(_fiche_lvmh, default_timeout=60), ws)
    assert not at.exception, [e.value for e in at.exception]
    assert any("LVMH" in m.value for m in at.markdown)


def test_anneau_dans_la_da_du_logo():
    import re

    from app.ui.theme import ring_svg

    svg = ring_svg([50, 30, 20], uid="t")
    assert re.findall(r'stroke-opacity="([\d.]+)"', svg) == ["1.0", "0.62", "0.34"]  # opacités du logo
    assert svg.count('stroke-linecap="round"') == 3


def _main() -> AppTest:
    return AppTest.from_file(str(ROOT / "interface.py"), default_timeout=60)


def _button(at: AppTest, label: str):
    return next(b for b in at.button if label in b.label)


def test_connexion_ordinateur(app_config):
    """Premier lancement : création d'un compte ; ensuite, connexion obligatoire."""
    at = _main().run()
    assert not at.exception
    assert any("Créer mon compte" in b.label for b in at.button)
    assert not any("Tableau de bord" in t.value for t in at.title)  # aucune donnée avant connexion
    at.text_input[0].input(USER)
    at.text_input[1].input(PASSWORD)
    at.text_input[2].input(PASSWORD)
    _button(at, "Créer mon compte").click().run()
    assert not at.exception
    assert at.session_state[ACCOUNT_KEY] is not None

    # Nouvelle session navigateur : il faut se connecter.
    at = _main().run()
    assert any("Se connecter" in b.label for b in at.button)
    at.text_input[0].input(USER)
    at.text_input[1].input("mauvais")
    _button(at, "Se connecter").click().run()
    assert any("incorrect" in e.value for e in at.error)
    at.text_input[1].input(PASSWORD)
    _button(at, "Se connecter").click().run()
    assert not at.exception and at.session_state[ACCOUNT_KEY] is not None

    # Un second compte se crée depuis l'écran de connexion, avec ses propres données.
    at = _main().run()
    _button(at, "Créer un compte").click().run()
    at.text_input[0].input("conjoint")
    at.text_input[1].input("Conjoint2026")
    at.text_input[2].input("Conjoint2026")
    _button(at, "Créer mon compte").click().run()
    assert not at.exception
