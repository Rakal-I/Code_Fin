"""Services : référentiel, saisie, actualisation, sauvegarde, journalisation."""
from datetime import date

import pytest
from pydantic import ValidationError

from app.models.entities import DataPoint, Instrument
from app.models.enums import DataField, DataStatus, InstrumentType, OperationType
from app.models.schemas import InstrumentIn, ManualValueIn, OperationIn, PositionIn
from app.services import backup, market_data, portfolio, referential
from app.services.logging_setup import RedactingFilter
from app.services.referential import BusinessError, Preferences
from tests.conftest import TODAY, FakeConnector

PREFS = Preferences()


def position(session, env, inst, qty=10, pru=100.0, ccy="EUR", day=date(2024, 1, 2), fx=None):
    p = portfolio.create_position(session, PositionIn(
        instrument_id=inst.id, envelope_id=env.id, quantity=qty, pru=pru, currency=ccy, takeover_date=day,
        institution=env.institution, contract=env.contract, fx_rate=fx))
    session.commit()
    return p


class TestReferentiel:
    def test_isin_invalide_refuse(self):
        with pytest.raises(ValidationError):
            InstrumentIn(name="X", type=InstrumentType.ACTION, isin="FR0000121015", currency="EUR")

    def test_meme_ticker_autorise_sur_deux_places(self, session, lvmh):
        other = referential.create_instrument(session, InstrumentIn(
            name="LVMH (Milan)", type=InstrumentType.ACTION, ticker="MC", isin="FR0000121014", exchange="Milan",
            currency="EUR"))
        assert other.id != lvmh.id

    def test_doublon_isin_place_devise_refuse(self, session, lvmh):
        with pytest.raises(BusinessError):
            referential.create_instrument(session, InstrumentIn(
                name="LVMH bis", type=InstrumentType.ACTION, ticker="MC", isin="FR0000121014",
                exchange="Euronext Paris", currency="EUR"))

    def test_instrument_sans_historique_supprime(self, session):
        inst = referential.create_instrument(session, InstrumentIn(name="Test", type=InstrumentType.ETF,
                                                                   ticker="TST", currency="EUR"))
        assert referential.remove_instrument(session, inst.id) == "supprimé"

    def test_instrument_avec_position_archive_et_consultable(self, session, pea, lvmh):
        position(session, pea, lvmh)
        assert referential.remove_instrument(session, lvmh.id) == "archivé"
        session.commit()
        assert session.get(Instrument, lvmh.id).archived
        assert lvmh not in referential.list_instruments(session)
        assert lvmh in referential.list_instruments(session, include_archived=True)
        assert any(v.instrument.id == lvmh.id for v in portfolio.holdings(session, PREFS, TODAY))

    def test_indices_par_defaut_une_seule_fois(self, session):
        assert referential.seed_default_indices(session) == 6
        assert referential.seed_default_indices(session) == 0


class TestSaisie:
    def test_position_initiale_et_valorisation(self, session, pea, lvmh):
        position(session, pea, lvmh, qty=10, pru=300.0)
        market_data.refresh_instrument(session, lvmh, [FakeConnector({"MC.PA": 400.0})], TODAY)
        view = portfolio.holdings(session, PREFS, TODAY)[0]
        assert view.valuation.value_eur == pytest.approx(4000)
        assert view.valuation.gain_eur == pytest.approx(1000)
        assert view.valuation.gain_eur_pct == pytest.approx(100 / 3)

    def test_vente_superieure_au_stock_refusee(self, session, pea, lvmh):
        position(session, pea, lvmh, qty=10)
        with pytest.raises(BusinessError, match="refusée"):
            portfolio.create_operation(session, OperationIn(day=date(2026, 1, 5), type=OperationType.VENTE,
                                                            envelope_id=pea.id, instrument_id=lvmh.id, quantity=11,
                                                            unit_price=500, currency="EUR"))
        assert portfolio.list_operations(session) == []

    def test_achat_puis_vente(self, session, pea, lvmh):
        position(session, pea, lvmh, qty=10, pru=100.0)
        for t, q, p in ((OperationType.ACHAT, 10, 200.0), (OperationType.VENTE, 5, 300.0)):
            portfolio.create_operation(session, OperationIn(day=date(2026, 2, 1), type=t, envelope_id=pea.id,
                                                            instrument_id=lvmh.id, quantity=q, unit_price=p,
                                                            currency="EUR"))
        session.commit()
        view = portfolio.holdings(session, PREFS, TODAY)[0]
        assert view.state.quantity == 15
        assert view.state.pru == pytest.approx(150.0)
        assert view.state.realized == pytest.approx(750.0)

    def test_devise_incoherente_refusee(self, session, pea, lvmh):
        position(session, pea, lvmh)
        with pytest.raises(BusinessError):
            portfolio.create_operation(session, OperationIn(day=date(2026, 1, 5), type=OperationType.ACHAT,
                                                            envelope_id=pea.id, instrument_id=lvmh.id, quantity=1,
                                                            unit_price=1, currency="USD"))

    def test_revenus_convertis(self, session, cto, apple):
        connector = FakeConnector({"AAPL": 200.0}, fx={"USD": 1.25})
        portfolio.create_operation(session, OperationIn(day=date(2026, 3, 1), type=OperationType.DIVIDENDE,
                                                        envelope_id=cto.id, instrument_id=apple.id, amount=50,
                                                        currency="USD"))
        market_data.refresh_fx(session, [connector], TODAY)
        rows = portfolio.incomes(session)
        assert rows[0].amount_eur == pytest.approx(40)


class TestActualisation:
    def test_conversion_devise_et_effet_de_change(self, session, cto, apple):
        position(session, cto, apple, qty=10, pru=100.0, ccy="USD", day=date(2026, 1, 2), fx=1.25)
        connector = FakeConnector({"AAPL": 110.0}, fx={"USD": 1.10})
        market_data.refresh_all(session, [connector], TODAY)
        view = portfolio.holdings(session, PREFS, TODAY)[0]
        assert view.valuation.value_eur == pytest.approx(1000)
        assert view.valuation.cost_eur == pytest.approx(800)
        assert view.valuation.fx_effect_eur is not None and view.valuation.fx_effect_eur > 0

    def test_seule_l_identite_publique_est_transmise(self, session, pea, lvmh):
        position(session, pea, lvmh, qty=123, pru=456.0)
        connector = FakeConnector({"MC.PA": 400.0})
        market_data.refresh_instrument(session, lvmh, [connector], TODAY)
        sent = connector.calls[0].model_dump()
        assert set(sent) == {"symbol", "isin", "type", "currency", "country"}
        assert 123 not in sent.values() and 456.0 not in sent.values()

    def test_panne_visible_et_aucune_valeur_inventee(self, session, pea, lvmh):
        position(session, pea, lvmh)
        connector = FakeConnector({"MC.PA": 400.0})
        connector.failing.add("MC.PA")
        result = market_data.refresh_instrument(session, lvmh, [connector], TODAY)
        session.commit()
        assert not result.ok
        price = market_data.current_price(session, lvmh, PREFS, TODAY)
        assert price.status == DataStatus.ERREUR and price.value_num is None
        view = portfolio.holdings(session, PREFS, TODAY)[0]
        assert view.valuation.value_eur is None
        summary = portfolio.summarize([view])
        assert summary.unvalued_lines == 1 and summary.value_eur == 0

    def test_panne_apres_succes_conserve_la_derniere_valeur(self, session, lvmh):
        connector = FakeConnector({"MC.PA": 400.0})
        market_data.refresh_instrument(session, lvmh, [connector], TODAY)
        connector.failing.add("MC.PA")
        market_data.refresh_instrument(session, lvmh, [connector], TODAY)
        session.commit()
        price = market_data.current_price(session, lvmh, PREFS, TODAY)
        assert price.status == DataStatus.REELLE and price.value_num == pytest.approx(400.0)
        statuses = {p.status for p in session.query(DataPoint).filter_by(field=DataField.PRICE)}
        assert DataStatus.ERREUR in statuses  # la panne reste tracée dans l'historique

    def test_donnee_non_fournie_marquee_non_disponible(self, session, lvmh):
        market_data.refresh_instrument(session, lvmh, [FakeConnector({"MC.PA": 400.0})], TODAY)
        values = market_data.current_values(session, lvmh, PREFS, TODAY)
        n1 = values[(DataField.DIVIDEND_N1, None)]
        assert n1.status == DataStatus.NON_DISPONIBLE and n1.value_num is None
        assert values[(DataField.EPS, 2025)].value_num == 5.0
        assert (DataField.TER, None) not in values  # non applicable à une action

    def test_cours_ancien_obsolete(self, session, lvmh):
        market_data.refresh_instrument(session, lvmh, [FakeConnector({"MC.PA": 400.0})], TODAY)
        later = date(2026, 12, 1)
        assert market_data.current_price(session, lvmh, PREFS, later).status == DataStatus.OBSOLETE

    def test_saisie_manuelle_de_secours(self, session, lvmh):
        market_data.record_manual_value(session, ManualValueIn(instrument_id=lvmh.id, field=DataField.DIVIDEND_N1,
                                                               value_num=14.0, currency="EUR", fiscal_year=2027,
                                                               reference_date=TODAY))
        values = market_data.current_values(session, lvmh, PREFS, TODAY)
        assert values[(DataField.DIVIDEND_N1, 2027)].status == DataStatus.MANUELLE

    def test_historique_complet_pour_les_performances(self, session, lvmh):
        market_data.refresh_instrument(session, lvmh, [FakeConnector({"MC.PA": 400.0})], TODAY)
        history = market_data.price_history(session, lvmh.id)
        assert history[0][0] <= date(2016, 10, 23)


class TestSauvegarde:
    def test_sauvegarde_verification_restauration(self, session, db_path, tmp_path, pea, lvmh):
        position(session, pea, lvmh)
        backup_dir = tmp_path / "backups"
        entry = backup.create_backup(db_path, backup_dir)
        assert backup.verify_backup(backup_dir, entry)[0]

        portfolio.delete_position(session, portfolio.list_positions(session)[0].id)
        session.commit()
        session.close()

        safety = backup.restore_backup(db_path, backup_dir, entry)
        assert safety.kind == "avant restauration"
        from app.database.engine import session_factory
        fresh = session_factory(db_path)()
        assert len(portfolio.list_positions(fresh)) == 1
        fresh.close()
        assert len(backup.list_backups(backup_dir)) == 2

    def test_sauvegarde_corrompue_refusee(self, db_path, tmp_path):
        backup_dir = tmp_path / "backups"
        entry = backup.create_backup(db_path, backup_dir)
        with (backup_dir / entry.file).open("r+b") as handle:
            handle.seek(200)
            handle.write(b"corruption")
        ok, message = backup.verify_backup(backup_dir, entry)
        assert not ok and "Empreinte" in message
        with pytest.raises(backup.BackupError):
            backup.restore_backup(db_path, backup_dir, entry)


class TestJournalisation:
    def test_les_secrets_sont_masques(self):
        f = RedactingFilter(["ma-cle-secrete"])
        assert "ma-cle-secrete" not in f.redact("appel avec ma-cle-secrete")
        assert f.redact("GET /quote?symbol=AAPL&token=abc123") == "GET /quote?symbol=AAPL&token=***"
        assert "abc" not in f.redact("{'X-Finnhub-Token': 'abc'}")
