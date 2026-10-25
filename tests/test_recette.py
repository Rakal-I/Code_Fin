"""Critères de recette du cahier des charges (§23), un test par critère."""
from datetime import date

import pytest

from app.database.engine import dispose_engine, session_factory
from app.domain.performance import performances
from app.models.entities import Instrument
from app.models.enums import DataField, DataStatus, InstrumentType, OperationType
from app.models.schemas import InstrumentIn, OperationIn, PositionIn
from app.services import backup, market_data, portfolio, referential
from app.services.referential import Preferences
from tests.conftest import TODAY, FakeConnector

PREFS = Preferences()


def test_01_un_instrument_peut_etre_cree_et_suivi(session):
    inst = referential.create_instrument(session, InstrumentIn(name="Air Liquide", type=InstrumentType.ACTION,
                                                               ticker="AI", provider_symbol="AI.PA",
                                                               isin="FR0000120073", currency="EUR"))
    market_data.refresh_instrument(session, inst, [FakeConnector({"AI.PA": 170.0})], TODAY)
    assert market_data.current_price(session, inst, PREFS, TODAY).value_num == pytest.approx(170.0)


def test_02_une_position_initiale_peut_etre_creee(session, pea, lvmh):
    portfolio.create_position(session, PositionIn(instrument_id=lvmh.id, envelope_id=pea.id, quantity=10, pru=600,
                                                  currency="EUR", takeover_date=date(2024, 1, 2),
                                                  institution="Banque A", contract="PEA-001"))
    assert portfolio.holdings(session, PREFS, TODAY)[0].state.quantity == 10


def test_03_une_operation_peut_etre_enregistree(session, pea, lvmh):
    portfolio.create_operation(session, OperationIn(day=date(2026, 1, 5), type=OperationType.ACHAT,
                                                    envelope_id=pea.id, instrument_id=lvmh.id, quantity=3,
                                                    unit_price=500, fees=2, currency="EUR"))
    assert portfolio.list_operations(session)[0].amount == pytest.approx(1500)


def test_04_les_performances_sont_calculees_correctement():
    history = [(date(2016, 1, 4), 50.0), (date(2025, 10, 23), 80.0), (date(2026, 4, 23), 90.0),
               (date(2026, 9, 23), 95.0), (date(2026, 10, 16), 98.0), (date(2026, 10, 23), 100.0)]
    perf = performances(history)
    assert perf["1 an"] == pytest.approx(25.0)
    assert perf["6 mois"] == pytest.approx(100 / 90 * 100 - 100)
    assert perf["1 mois"] == pytest.approx(100 / 95 * 100 - 100)
    assert perf["1 sem."] == pytest.approx(100 / 98 * 100 - 100)
    assert perf["5 ans"] is None and perf["10 ans"] is None  # pas de cours autour de la date de départ


def test_05_la_valorisation_est_correcte(session, pea, lvmh):
    test_02_une_position_initiale_peut_etre_creee(session, pea, lvmh)
    market_data.refresh_instrument(session, lvmh, [FakeConnector({"MC.PA": 400.0})], TODAY)
    view = portfolio.holdings(session, PREFS, TODAY)[0]
    assert view.valuation.value_eur == pytest.approx(10 * 400.0)
    assert view.valuation.gain_eur == pytest.approx(4000 - 6000)


def test_06_les_devises_sont_correctement_converties(session, cto, apple):
    portfolio.create_position(session, PositionIn(instrument_id=apple.id, envelope_id=cto.id, quantity=10, pru=100,
                                                  currency="USD", takeover_date=date(2026, 1, 2),
                                                  institution="Courtier B", contract="CTO-9", fx_rate=1.25))
    market_data.refresh_all(session, [FakeConnector({"AAPL": 120.0}, fx={"USD": 1.2})], TODAY)
    v = portfolio.holdings(session, PREFS, TODAY)[0].valuation
    assert v.value_eur == pytest.approx(1200 / 1.2)
    assert v.cost_eur == pytest.approx(1000 / 1.25)
    assert v.market_effect_eur + v.fx_effect_eur == pytest.approx(v.gain_eur)


def test_07_les_erreurs_sont_visibles(session, lvmh):
    connector = FakeConnector()
    result = market_data.refresh_instrument(session, lvmh, [connector], TODAY)
    assert not result.ok and result.messages
    assert market_data.current_price(session, lvmh, PREFS, TODAY).status == DataStatus.ERREUR


def test_08_les_sources_sont_consultables(session, lvmh):
    market_data.refresh_instrument(session, lvmh, [FakeConnector({"MC.PA": 400.0})], TODAY)
    for cv in market_data.current_values(session, lvmh, PREFS, TODAY).values():
        assert cv.point.source and cv.point.collected_at and cv.point.reference_date


def test_09_les_sauvegardes_fonctionnent(db_path, tmp_path):
    entry = backup.create_backup(db_path, tmp_path / "b")
    assert backup.verify_backup(tmp_path / "b", entry) == (True, "Intégrité vérifiée.")


def test_10_la_restauration_fonctionne(session, db_path, tmp_path, lvmh):
    entry = backup.create_backup(db_path, tmp_path / "b")
    referential.remove_instrument(session, lvmh.id)
    session.commit()
    session.close()
    backup.restore_backup(db_path, tmp_path / "b", entry)
    fresh = session_factory(db_path)()
    assert fresh.get(Instrument, lvmh.id) is not None
    fresh.close()


def test_11_les_donnees_persistent_apres_redemarrage(session, db_path, pea, lvmh):
    test_02_une_position_initiale_peut_etre_creee(session, pea, lvmh)
    session.commit()
    session.close()
    dispose_engine(db_path)  # simule la fermeture de l'application
    reopened = session_factory(db_path)()
    assert len(portfolio.list_positions(reopened)) == 1
    reopened.close()


def test_12_aucune_donnee_n_est_inventee(session, pea, lvmh):
    test_02_une_position_initiale_peut_etre_creee(session, pea, lvmh)
    market_data.refresh_instrument(session, lvmh, [FakeConnector({"MC.PA": 400.0})], TODAY)
    values = market_data.current_values(session, lvmh, PREFS, TODAY)
    for (fld, _), cv in values.items():
        if cv.status in (DataStatus.NON_DISPONIBLE, DataStatus.ERREUR):
            assert cv.value_num is None, fld
    assert values[(DataField.DIVIDEND_N1, None)].status == DataStatus.NON_DISPONIBLE
    # Sans cours, la ligne n'est pas valorisée : jamais 0.
    other = referential.create_instrument(session, InstrumentIn(name="Sans cours", type=InstrumentType.ACTION,
                                                                ticker="NOPE", currency="EUR"))
    portfolio.create_position(session, PositionIn(instrument_id=other.id, envelope_id=pea.id, quantity=1, pru=10,
                                                  currency="EUR", takeover_date=date(2024, 1, 2),
                                                  institution="Banque A", contract="PEA-001"))
    view = next(v for v in portfolio.holdings(session, PREFS, TODAY) if v.instrument.id == other.id)
    assert view.valuation.value_eur is None


def test_13_un_instrument_archive_reste_consultable(session, pea, lvmh):
    test_02_une_position_initiale_peut_etre_creee(session, pea, lvmh)
    assert referential.remove_instrument(session, lvmh.id) == "archivé"
    session.commit()
    archived = [i for i in referential.list_instruments(session, include_archived=True) if i.archived]
    assert archived == [lvmh]
    assert portfolio.holdings(session, PREFS, TODAY)[0].instrument.archived
