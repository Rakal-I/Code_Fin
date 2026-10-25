"""Source secondaire : Finnhub (clé API requise, offre gratuite limitée)."""
from __future__ import annotations

from datetime import UTC, date, datetime

import requests

from app.connectors.base import ConnectorError, FetchedBar, FetchedValue, InstrumentRef, PriceHistory
from app.models.enums import DataField, DataStatus, InstrumentType

SOURCE = "Finnhub"
BASE_URL = "https://finnhub.io/api/v1"


class FinnhubConnector:
    name = SOURCE

    def __init__(self, api_key: str | None, timeout: float = 15.0):
        self._api_key = api_key
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def _get(self, path: str, **params) -> dict:
        if not self._api_key:
            raise ConnectorError("Clé Finnhub non configurée.")
        try:
            # La clé passe dans un en-tête, jamais dans l'URL (qui peut finir dans des journaux).
            response = requests.get(f"{BASE_URL}{path}", params=params, timeout=self.timeout,
                                    headers={"X-Finnhub-Token": self._api_key})
        except requests.RequestException as exc:
            raise ConnectorError(f"Finnhub injoignable : {type(exc).__name__}") from exc
        if response.status_code in (401, 403):
            raise ConnectorError("Accès Finnhub refusé (clé invalide ou donnée réservée à l'offre payante).")
        if response.status_code != 200:
            raise ConnectorError(f"Réponse Finnhub inattendue ({response.status_code}).")
        return response.json() or {}

    def price_history(self, ref: InstrumentRef, start: date) -> PriceHistory:
        data = self._get("/quote", symbol=ref.symbol)
        price, timestamp = data.get("c"), data.get("t")
        if not price or not timestamp:
            raise ConnectorError("Aucun cours Finnhub pour ce symbole.")
        day = datetime.fromtimestamp(timestamp, UTC).date()
        return PriceHistory(currency=ref.currency, bars=[FetchedBar(day=day, close=float(price))])

    def fx_history(self, quote: str, start: date) -> list[FetchedBar]:
        raise ConnectorError("Taux de change non pris en charge par ce connecteur.")

    def fundamentals(self, ref: InstrumentRef) -> list[FetchedValue]:
        if ref.type != InstrumentType.ACTION:
            return []
        data = self._get("/stock/price-target", symbol=ref.symbol)
        today = datetime.now(UTC).date()
        updated = data.get("lastUpdated")
        reference = date.fromisoformat(updated[:10]) if updated else today
        values = []
        for field, key in ((DataField.TARGET_MEAN, "targetMean"), (DataField.TARGET_LOW, "targetLow"),
                           (DataField.TARGET_HIGH, "targetHigh")):
            if data.get(key):
                values.append(FetchedValue(field=field, status=DataStatus.ESTIMEE, value_num=float(data[key]),
                                           currency=ref.currency, reference_date=reference,
                                           note="Consensus des analystes"))
        return values
