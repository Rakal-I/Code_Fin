"""Règles métier du cahier des charges (§6, §7, §8, §11, §12)."""
from datetime import date

import pytest

from app.domain.fundamentals import is_valid_isin, potential
from app.domain.performance import performances
from app.domain.portfolio import TradeEvent, build_holding, value_holding
from app.domain.quality import applicability, badge, effective_status, is_applicable
from app.models.enums import Applicability, DataField, DataStatus, InstrumentType, OperationType

D = date(2026, 1, 15)


def ev(kind, q=None, p=None, fees=0.0, fx=1.0, day=D, ref=None):
    return TradeEvent(day=day, kind=kind, quantity=q, unit_price=p, fees=fees, fx=fx, ref=ref)


class TestPRU:
    def test_prix_de_revient_moyen_pondere_frais_inclus(self):
        state = build_holding(10, 100.0, 1.0, [ev(OperationType.ACHAT, 10, 130.0, fees=10.0)])
        assert state.quantity == 20
        assert state.pru == pytest.approx((1000 + 1300 + 10) / 20)

    def test_vente_ne_modifie_pas_le_pru_et_genere_une_plus_value_realisee(self):
        state = build_holding(20, 115.0, 1.0, [ev(OperationType.VENTE, 5, 150.0, fees=5.0)])
        assert state.quantity == 15
        assert state.pru == pytest.approx(115.0)
        assert state.realized == pytest.approx(5 * 150 - 5 - 5 * 115)

    def test_vente_superieure_a_la_quantite_est_refusee_et_visible(self):
        state = build_holding(5, 10.0, 1.0, [ev(OperationType.VENTE, 6, 12.0)])
        assert state.quantity == 5
        assert state.errors and "supérieure" in state.errors[0]

    def test_vente_totale_conserve_le_dernier_pru(self):
        state = build_holding(5, 10.0, 1.0, [ev(OperationType.VENTE, 5, 12.0)])
        assert not state.is_open
        assert state.pru == pytest.approx(10.0)
        assert state.realized == pytest.approx(10.0)

    def test_ordre_chronologique(self):
        events = [
            ev(OperationType.VENTE, 5, 20.0, day=date(2026, 3, 1), ref=2),
            ev(OperationType.ACHAT, 10, 10.0, day=date(2026, 2, 1), ref=1),
        ]
        state = build_holding(events=events)
        assert state.quantity == 5 and state.realized == pytest.approx(50.0)

    def test_correction_de_quantite_et_de_pru(self):
        events = [ev(OperationType.CORRECTION, q=2), ev(OperationType.CORRECTION, p=11.0, day=date(2026, 2, 1))]
        state = build_holding(10, 10.0, 1.0, events)
        assert state.quantity == 12
        assert state.pru == pytest.approx(11.0)


class TestValorisation:
    def test_formules_du_cahier_des_charges(self):
        state = build_holding(10, 100.0, 1.0)
        v = value_holding(state, price=120.0, fx_now=1.0)
        assert v.value == pytest.approx(1200)            # quantité × cours
        assert v.gain == pytest.approx(200)              # valeur − coût
        assert v.gain_pct == pytest.approx(20)           # (valeur / coût − 1) × 100
        assert v.fx_effect_eur == pytest.approx(0)

    def test_cours_absent_donne_une_valeur_inconnue_et_jamais_zero(self):
        v = value_holding(build_holding(10, 100.0, 1.0), price=None, fx_now=1.0)
        assert v.value is None and v.value_eur is None and v.gain is None and v.gain_pct is None

    def test_conversion_eur_et_effet_de_change(self):
        # 10 actions achetées 100 USD avec 1 EUR = 1,25 USD : coût 800 EUR.
        state = build_holding(10, 100.0, 1.25)
        # Cours 110 USD, et 1 EUR = 1,10 USD : valeur 1000 EUR.
        v = value_holding(state, price=110.0, fx_now=1.10)
        assert v.cost_eur == pytest.approx(800)
        assert v.value_eur == pytest.approx(1000)
        assert v.gain_eur == pytest.approx(200)
        assert v.market_effect_eur == pytest.approx(100 / 1.25)          # +10 USD × 10 au taux d'achat
        assert v.fx_effect_eur == pytest.approx(200 - 100 / 1.25)
        assert v.market_effect_eur + v.fx_effect_eur == pytest.approx(v.gain_eur)

    def test_taux_de_change_manquant_rend_les_montants_eur_inconnus(self):
        state = build_holding(10, 100.0, None)
        v = value_holding(state, price=110.0, fx_now=1.1)
        assert v.value_eur == pytest.approx(1000)
        assert v.cost_eur is None and v.gain_eur is None and v.fx_effect_eur is None

    def test_vente_en_devise_plus_value_realisee_eur(self):
        state = build_holding(10, 100.0, 1.25, [ev(OperationType.VENTE, 5, 120.0, fx=1.2)])
        assert state.realized == pytest.approx(100)
        assert state.realized_eur == pytest.approx(600 / 1.2 - 400)
        assert state.cost_eur == pytest.approx(400)


class TestPerformances:
    def history(self, start, days, step=1, price=100.0):
        from datetime import timedelta
        return [(start + timedelta(days=i), price + i) for i in range(0, days, step)]

    def test_historique_insuffisant_donne_na(self):
        perf = performances(self.history(date(2026, 1, 1), 60))
        assert perf["1 sem."] is not None and perf["1 mois"] is not None
        assert perf["6 mois"] is None and perf["1 an"] is None and perf["10 ans"] is None

    def test_calcul_exact(self):
        hist = [(date(2025, 1, 15), 100.0), (date(2026, 1, 15), 125.0)]
        assert performances(hist)["1 an"] == pytest.approx(25.0)

    def test_trou_dans_l_historique_donne_na_sans_approximation(self):
        hist = [(date(2020, 1, 1), 50.0), (date(2026, 1, 15), 100.0)]
        assert performances(hist)["1 an"] is None

    def test_historique_vide(self):
        assert all(v is None for v in performances([]).values())


class TestFondamentaux:
    def test_potentiel(self):
        assert potential(120.0, 100.0) == pytest.approx(20.0)
        assert potential(None, 100.0) is None
        assert potential(120.0, None) is None

    @pytest.mark.parametrize("isin,ok", [("US0378331005", True), ("FR0000121014", True),
                                         ("FR0000121015", False), ("ABC", False)])
    def test_isin(self, isin, ok):
        assert is_valid_isin(isin) is ok


class TestQualite:
    def test_matrice_d_applicabilite(self):
        assert applicability(DataField.EPS, InstrumentType.ETF) == Applicability.NON_APPLICABLE
        assert applicability(DataField.TER, InstrumentType.ETF) == Applicability.OUI
        assert not is_applicable(DataField.DIVIDEND_N, InstrumentType.INDICE)
        assert is_applicable(DataField.PRICE, InstrumentType.INDICE)
        assert not is_applicable(DataField.TER, InstrumentType.ACTION)

    def test_cours_trop_ancien_devient_obsolete(self):
        today = date(2026, 1, 20)
        assert effective_status(DataStatus.REELLE, date(2026, 1, 1), DataField.PRICE, today) == DataStatus.OBSOLETE
        assert effective_status(DataStatus.REELLE, date(2026, 1, 19), DataField.PRICE, today) == DataStatus.REELLE
        assert effective_status(DataStatus.ERREUR, date(2020, 1, 1), DataField.PRICE, today) == DataStatus.ERREUR

    def test_le_libelle_accompagne_toujours_la_couleur(self):
        for status in DataStatus:
            assert status.label in badge(status)
