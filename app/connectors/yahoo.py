"""Source principale : Yahoo Finance via yfinance."""
from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime

from app.connectors.base import ConnectorError, FetchedBar, FetchedValue, InstrumentRef, PriceHistory
from app.models.enums import DataField, DataStatus, InstrumentType

log = logging.getLogger(__name__)

SOURCE = "Yahoo Finance"


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _day(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not math.isnan(value):
        return datetime.fromtimestamp(value, UTC).date()
    if hasattr(value, "date"):
        return value.date()
    return None


def _normalize_currency(currency: str | None) -> tuple[str | None, float]:
    """Les cotations de Londres en pence (GBp) sont converties en livres."""
    if currency in ("GBp", "GBX"):
        return "GBP", 0.01
    if currency in ("ZAc", "ILA"):
        return {"ZAc": "ZAR", "ILA": "ILS"}[currency], 0.01
    return (currency.upper() if currency else None), 1.0


class YahooConnector:
    name = SOURCE

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return True

    def _ticker(self, symbol: str):
        import yfinance as yf

        return yf.Ticker(symbol)

    def price_history(self, ref: InstrumentRef, start: date) -> PriceHistory:
        try:
            ticker = self._ticker(ref.symbol)
            frame = ticker.history(start=start.isoformat(), auto_adjust=False, timeout=self.timeout)
            meta_currency = (ticker.history_metadata or {}).get("currency")
        except Exception as exc:  # erreurs réseau ou de format du fournisseur
            raise ConnectorError(f"Historique indisponible : {type(exc).__name__}") from exc
        if frame is None or frame.empty:
            raise ConnectorError("Aucun cours renvoyé pour ce symbole.")
        currency, factor = _normalize_currency(meta_currency or ref.currency)
        bars = [
            FetchedBar(day=_day(index), close=close * factor)
            for index, close in frame["Close"].items()
            if _num(close) is not None and close > 0
        ]
        return PriceHistory(currency=currency or ref.currency, bars=bars)

    def fx_history(self, quote: str, start: date) -> list[FetchedBar]:
        """Taux EUR/devise : 1 EUR = x devise."""
        ref = InstrumentRef(symbol=f"EUR{quote}=X", type=InstrumentType.INDICE, currency=quote)
        return self.price_history(ref, start).bars

    def fundamentals(self, ref: InstrumentRef) -> list[FetchedValue]:
        try:
            ticker = self._ticker(ref.symbol)
            info = ticker.info or {}
        except Exception as exc:
            raise ConnectorError(f"Fondamentaux indisponibles : {type(exc).__name__}") from exc

        today = datetime.now(UTC).date()
        currency, factor = _normalize_currency(info.get("currency") or ref.currency)
        values: list[FetchedValue] = []

        def add(field, status=DataStatus.REELLE, **kwargs):
            reference = kwargs.pop("reference_date", today)
            values.append(FetchedValue(field=field, status=status, reference_date=reference, **kwargs))

        if ref.type in (InstrumentType.ACTION, InstrumentType.ETF):
            for field, key in ((DataField.TARGET_MEAN, "targetMeanPrice"), (DataField.TARGET_LOW, "targetLowPrice"),
                               (DataField.TARGET_HIGH, "targetHighPrice")):
                if (v := _num(info.get(key))) is not None:
                    add(field, DataStatus.ESTIMEE, value_num=v * factor, currency=currency,
                        note="Consensus des analystes")
            if (v := _num(info.get("numberOfAnalystOpinions"))) is not None:
                add(DataField.ANALYSTS, value_num=v)

        if ref.type == InstrumentType.ACTION:
            values += self._dividends(ticker, info, currency, factor, today)
            values += self._eps(ticker, info, today)

        if ref.type in (InstrumentType.ETF, InstrumentType.FONDS, InstrumentType.UC):
            ter = _num(info.get("netExpenseRatio")) or _num(info.get("annualReportExpenseRatio"))
            if ter is not None:
                add(DataField.TER, value_num=ter, note="En % par an")
            if (aum := _num(info.get("totalAssets"))) is not None:
                add(DataField.AUM, value_num=aum, currency=currency)
            if info.get("fundFamily"):
                add(DataField.MANAGER, value_text=str(info["fundFamily"]))
        return values

    def _dividends(self, ticker, info, currency, factor, today) -> list[FetchedValue]:
        values: list[FetchedValue] = []
        if (rate := _num(info.get("dividendRate"))) is not None:
            values.append(FetchedValue(
                field=DataField.DIVIDEND_N, status=DataStatus.ESTIMEE, value_num=rate * factor,
                currency=currency, fiscal_year=today.year, reference_date=today,
                note="Dividende annuel prévisionnel publié par Yahoo (dividendRate)",
            ))
        try:
            history = ticker.dividends
        except Exception:
            history = None
        if history is not None and len(history):
            last_year = today.year - 1
            paid = [_num(v) for d, v in history.items() if _day(d) and _day(d).year == last_year]
            if paid and all(p is not None for p in paid):
                values.append(FetchedValue(
                    field=DataField.DIVIDEND_LAST, status=DataStatus.REELLE, value_num=sum(paid) * factor,
                    currency=currency, fiscal_year=last_year, reference_date=date(last_year, 12, 31),
                    note=f"Somme des dividendes détachés en {last_year}",
                ))
        try:
            calendar = ticker.calendar or {}
        except Exception:
            calendar = {}
        for field, key in ((DataField.EX_DATE, "Ex-Dividend Date"), (DataField.PAYMENT_DATE, "Dividend Date")):
            if (d := _day(calendar.get(key))) is not None:
                values.append(FetchedValue(field=field, status=DataStatus.REELLE, value_date=d, reference_date=today))
        return values

    def _eps(self, ticker, info, today) -> list[FetchedValue]:
        """BNA rattachés à leur exercice fiscal réel (année de clôture)."""
        values: list[FetchedValue] = []
        currency, factor = _normalize_currency(info.get("financialCurrency") or info.get("currency"))
        try:
            statement = ticker.income_stmt
        except Exception:
            statement = None
        if statement is not None and not statement.empty:
            row = next((r for r in ("Diluted EPS", "Basic EPS") if r in statement.index), None)
            if row:
                for column, value in statement.loc[row].items():
                    end = _day(column)
                    if end and (v := _num(value)) is not None:
                        values.append(FetchedValue(
                            field=DataField.EPS, status=DataStatus.REELLE, value_num=v * factor, currency=currency,
                            fiscal_year=end.year, reference_date=end, note=f"Exercice clos le {end:%d/%m/%Y}",
                        ))
        try:
            estimates = ticker.earnings_estimate
        except Exception:
            estimates = None
        next_end = _day(info.get("nextFiscalYearEnd"))
        if estimates is not None and not estimates.empty and next_end:
            for period, offset in (("0y", 0), ("+1y", 1)):
                if period in estimates.index and (v := _num(estimates.loc[period, "avg"])) is not None:
                    analysts = _num(estimates.loc[period].get("numberOfAnalysts"))
                    year = next_end.year + offset
                    note = f"Consensus, exercice clos en {year}"
                    if analysts:
                        note += f" ({int(analysts)} analystes)"
                    values.append(FetchedValue(
                        field=DataField.EPS, status=DataStatus.ESTIMEE, value_num=v * factor, currency=currency,
                        fiscal_year=year, reference_date=today, note=note,
                    ))
        return values
