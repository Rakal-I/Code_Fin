"""Crée une base de démonstration (positions fictives, cours réels) pour découvrir Ancora.

Usage :
    python scripts/demo_data.py data/demo.db
    ANCORA_DB_PATH=data/demo.db streamlit run app/main.py

N'utilisez jamais votre base réelle comme cible : ce script ajoute des positions fictives.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_config  # noqa: E402
from app.connectors.registry import build_connectors  # noqa: E402
from app.database.engine import session_scope, upgrade_to_head  # noqa: E402
from app.models.enums import EnvelopeType, InstrumentSubtype, InstrumentType, OperationType  # noqa: E402
from app.models.schemas import EnvelopeIn, InstrumentIn, OperationIn, PositionIn  # noqa: E402
from app.services import market_data, portfolio, referential  # noqa: E402


def main(target: Path) -> None:
    if target.exists():
        sys.exit(f"{target} existe déjà : choisissez un nouveau fichier.")
    upgrade_to_head(target)
    with session_scope(target) as s:
        referential.seed_default_indices(s)
        pea = referential.create_envelope(s, EnvelopeIn(name="PEA", type=EnvelopeType.PEA,
                                                        institution="Banque Exemple", contract="PEA-0001"))
        av = referential.create_envelope(s, EnvelopeIn(name="Assurance-vie", type=EnvelopeType.ASSURANCE_VIE,
                                                       institution="Assureur Exemple", contract="AV-2201"))
        cto = referential.create_envelope(s, EnvelopeIn(name="Compte-titres", type=EnvelopeType.CTO,
                                                        institution="Courtier Exemple", contract="CTO-77"))

        def instrument(**kw):
            return referential.create_instrument(s, InstrumentIn(**kw))

        lvmh = instrument(name="LVMH", type=InstrumentType.ACTION, ticker="MC", provider_symbol="MC.PA",
                          isin="FR0000121014", exchange="Euronext Paris", currency="EUR", country="France",
                          issuer="LVMH Moët Hennessy Louis Vuitton")
        ai = instrument(name="Air Liquide", type=InstrumentType.ACTION, ticker="AI", provider_symbol="AI.PA",
                        isin="FR0000120073", exchange="Euronext Paris", currency="EUR", country="France")
        tte = instrument(name="TotalEnergies", type=InstrumentType.ACTION, ticker="TTE", provider_symbol="TTE.PA",
                         isin="FR0014000MR3", exchange="Euronext Paris", currency="EUR", country="France")
        cw8 = instrument(name="Amundi MSCI World", type=InstrumentType.ETF, subtype=InstrumentSubtype.CAPITALISANT,
                         ticker="CW8", provider_symbol="CW8.PA", isin="LU1681043599", exchange="Euronext Paris",
                         currency="EUR", issuer="Amundi")
        aapl = instrument(name="Apple", type=InstrumentType.ACTION, ticker="AAPL", isin="US0378331005",
                          exchange="Nasdaq", currency="USD", country="États-Unis")
        msft = instrument(name="Microsoft", type=InstrumentType.ACTION, ticker="MSFT", isin="US5949181045",
                          exchange="Nasdaq", currency="USD", country="États-Unis")
        instrument(name="ASML", type=InstrumentType.ACTION, ticker="ASML", provider_symbol="ASML.AS",
                   isin="NL0010273215", exchange="Euronext Amsterdam", currency="EUR", country="Pays-Bas")

        start = date(2023, 1, 3)
        for inst, env, qty, pru in ((lvmh, pea, 12, 610.0), (ai, pea, 40, 138.5), (tte, pea, 80, 54.2),
                                    (cw8, av, 30, 395.0), (aapl, cto, 25, 128.0), (msft, cto, 10, 241.0)):
            portfolio.create_position(s, PositionIn(instrument_id=inst.id, envelope_id=env.id, quantity=qty, pru=pru,
                                                    currency=inst.currency, takeover_date=start,
                                                    institution=env.institution, contract=env.contract))
        ops = [
            (date(2024, 3, 12), OperationType.ACHAT, pea, lvmh, 3, 820.0, None),
            (date(2025, 6, 2), OperationType.VENTE, pea, tte, 30, 58.9, None),
            (date(2025, 4, 28), OperationType.DIVIDENDE, pea, lvmh, None, None, 195.0),
            (date(2026, 4, 28), OperationType.DIVIDENDE, pea, lvmh, None, None, 112.5),
            (date(2026, 5, 20), OperationType.DIVIDENDE, pea, ai, None, None, 132.0),
            (date(2026, 6, 25), OperationType.DIVIDENDE, pea, tte, None, None, 42.5),
            (date(2026, 8, 14), OperationType.DIVIDENDE, cto, aapl, None, None, 6.5),
            (date(2026, 1, 15), OperationType.APPORT, av, None, None, None, 5000.0),
        ]
        for day, kind, env, inst, qty, price, amount in ops:
            portfolio.create_operation(s, OperationIn(
                day=day, type=kind, envelope_id=env.id, instrument_id=inst.id if inst else None, quantity=qty,
                unit_price=price, amount=amount, currency=inst.currency if inst else "EUR"))
        s.commit()
        print("Actualisation des cours (réseau)…")
        results = market_data.refresh_all(s, build_connectors(get_config()),
                                          progress=lambda i, n, name: print(f"  {i}/{n} {name}"))
        failed = [r for r in results if not r.ok]
        print(f"Terminé : {len(results) - len(failed)} actualisé(s), {len(failed)} en erreur.")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "data/demo.db"))
