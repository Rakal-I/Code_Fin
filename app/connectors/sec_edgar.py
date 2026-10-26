"""Source réglementaire : SEC EDGAR (BNA publiés dans les rapports annuels 10-K, sociétés américaines)."""
from __future__ import annotations

from datetime import date

import requests

from app.connectors.base import ConnectorError, FetchedBar, FetchedValue, InstrumentRef, PriceHistory
from app.models.enums import DataField, DataStatus, InstrumentType

SOURCE = "SEC EDGAR"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/EarningsPerShareDiluted.json"
US_COUNTRIES = {"US", "USA", "United States", "États-Unis", "Etats-Unis"}


class SecEdgarConnector:
    name = SOURCE

    def __init__(self, user_agent: str | None, timeout: float = 15.0):
        self._user_agent = user_agent
        self.timeout = timeout
        self._ciks: dict[str, int] | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._user_agent)

    def _get(self, url: str) -> dict:
        if not self._user_agent:
            raise ConnectorError("User-Agent SEC non configuré.")
        try:
            response = requests.get(url, timeout=self.timeout, headers={"User-Agent": self._user_agent})
        except requests.RequestException as exc:
            raise ConnectorError(f"SEC EDGAR injoignable : {type(exc).__name__}") from exc
        if response.status_code == 404:
            raise ConnectorError("Donnée absente de SEC EDGAR.")
        if response.status_code != 200:
            raise ConnectorError(f"Réponse SEC EDGAR inattendue ({response.status_code}).")
        return response.json()

    def _cik(self, symbol: str) -> int:
        if self._ciks is None:
            data = self._get(TICKERS_URL)
            self._ciks = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
        cik = self._ciks.get(symbol.upper())
        if cik is None:
            raise ConnectorError("Société introuvable dans SEC EDGAR.")
        return cik

    def price_history(self, ref: InstrumentRef, start: date) -> PriceHistory:
        raise ConnectorError("SEC EDGAR ne fournit pas de cours.")

    def fx_history(self, quote: str, start: date) -> list[FetchedBar]:
        raise ConnectorError("SEC EDGAR ne fournit pas de taux de change.")

    def fundamentals(self, ref: InstrumentRef) -> list[FetchedValue]:
        if ref.type != InstrumentType.ACTION or (ref.country or "") not in US_COUNTRIES:
            return []
        data = self._get(CONCEPT_URL.format(cik=self._cik(ref.symbol)))
        by_end: dict[date, tuple[str, float]] = {}
        for item in data.get("units", {}).get("USD/shares", []):
            if item.get("form") != "10-K" or not item.get("start") or not item.get("end"):
                continue
            start, end = date.fromisoformat(item["start"]), date.fromisoformat(item["end"])
            if (end - start).days < 340:  # exercice complet uniquement
                continue
            filed = item.get("filed", "")
            if end not in by_end or filed > by_end[end][0]:
                by_end[end] = (filed, float(item["val"]))
        return [
            FetchedValue(field=DataField.EPS, status=DataStatus.REELLE, value_num=value, currency="USD",
                         fiscal_year=end.year, reference_date=end, note=f"10-K, exercice clos le {end:%d/%m/%Y}")
            for end, (_, value) in sorted(by_end.items())[-5:]
        ]
