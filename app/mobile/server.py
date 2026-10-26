"""Interface téléphone : API JSON + web-app installable (écran d'accueil iPhone).

Lancement : python -m app.mobile   (http://127.0.0.1:8502)

Elle lit la même base et applique les mêmes règles que l'interface ordinateur.
La saisie et l'administration restent sur l'ordinateur.
"""
from __future__ import annotations

import threading
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select

from app.bootstrap import bootstrap
from app.config.settings import ROOT, get_config
from app.connectors.registry import build_connectors
from app.database.engine import session_scope
from app.domain.quality import BADGES
from app.models.entities import RefreshLog
from app.models.enums import DataStatus, InstrumentType
from app.services import market_data, referential
from app.services import portfolio as pf
from app.ui import views

STATIC = ROOT / "app" / "mobile" / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap(get_config())
    yield


app = FastAPI(title="Ancora mobile", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


def _session():
    return session_scope(get_config().db_path)


def _status(status: DataStatus) -> dict:
    badge = BADGES[status]
    return {"code": status.name, "label": status.label, "emoji": badge.emoji}


def _require_app_header(x_ancora: str | None) -> None:
    """Les écritures exigent un en-tête personnalisé : un autre site ne peut pas l'envoyer sans autorisation."""
    if x_ancora != "1":
        raise HTTPException(status_code=403, detail="Requête refusée.")


# --------------------------------------------------------------------------
# Patrimoine
# --------------------------------------------------------------------------

@app.get("/api/summary")
def summary() -> dict:
    with _session() as s:
        prefs = referential.get_preferences(s)
        views_all = pf.holdings(s, prefs, include_closed=True)
        totals = pf.summarize(views_all)
        incomes = pf.incomes(s)
        last = market_data.last_refresh(s)
        stale = market_data.stale_prices(s, prefs)
        year_ago = datetime.now(UTC).date() - timedelta(days=365)
        recent = [r for r in incomes if r.day >= year_ago]
        positions = [{
            "instrument_id": v.instrument.id,
            "name": v.instrument.name,
            "envelope": v.envelope.name,
            "type": v.instrument.type.label,
            "currency": v.currency,
            "quantity": v.state.quantity,
            "pru": v.state.pru,
            "price": v.valuation.price,
            "value_eur": v.valuation.value_eur,
            "gain_eur": v.valuation.gain_eur,
            "gain_pct": v.valuation.gain_eur_pct,
            "price_status": _status(v.price_status),
            "issues": v.issues,
        } for v in views_all if v.is_open]
    positions.sort(key=lambda p: p["value_eur"] if p["value_eur"] is not None else -1, reverse=True)
    return {
        "value_eur": totals.value_eur,
        "cost_eur": totals.cost_eur,
        "gain_eur": totals.gain_eur,
        "gain_pct": totals.gain_pct,
        "realized_eur": totals.realized_eur,
        "income_12m_eur": sum(r.amount_eur for r in recent if r.amount_eur is not None),
        "lines": totals.lines,
        "unvalued_lines": totals.unvalued_lines,
        "by_envelope": _shares(totals.by_envelope),
        "by_type": _shares(totals.by_type),
        "positions": positions,
        "last_refresh": last.isoformat() if last else None,
        "stale_count": len(stale),
        "mask_amounts": prefs.mask_amounts,
    }


def _shares(values: dict[str, float]) -> list[dict]:
    return [{"label": k, "value": v} for k, v in sorted(values.items(), key=lambda kv: kv[1], reverse=True)]


# --------------------------------------------------------------------------
# Marchés
# --------------------------------------------------------------------------

@app.get("/api/markets")
def markets(scope: str = "watchlist") -> dict:
    with _session() as s:
        prefs = referential.get_preferences(s)
        instruments = referential.list_instruments(s)
        if scope == "held":
            held = {v.instrument.id for v in pf.holdings(s, prefs)}
            instruments = [i for i in instruments if i.id in held]
        elif scope == "indices":
            instruments = [i for i in instruments if i.type == InstrumentType.INDICE]
        elif scope == "watchlist":
            instruments = [i for i in instruments if i.watchlist and i.type != InstrumentType.INDICE]
        items = []
        for instrument in instruments:
            row = views.market_row(s, instrument, prefs)
            p = row.price.point
            items.append({
                "id": instrument.id,
                "name": instrument.name,
                "ticker": instrument.ticker or instrument.isin or "",
                "type": instrument.type.label,
                "price": row.price.value_num,
                "currency": (p.currency if p and p.currency else instrument.currency),
                "date": p.reference_date.isoformat() if p and p.reference_date and row.price.has_value else None,
                "status": _status(row.price.status),
                "perf": row.perf,
                "potential": row.potential,
            })
    return {"items": items}


@app.get("/api/instruments/{instrument_id}")
def instrument(instrument_id: int) -> dict:
    with _session() as s:
        prefs = referential.get_preferences(s)
        try:
            inst = referential.get_instrument(s, instrument_id)
        except referential.BusinessError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        row = views.market_row(s, inst, prefs)
        history = market_data.price_history(s, inst.id)
        sections = views.fundamentals_sections(s, inst, prefs)
        p = row.price.point
        return {
            "id": inst.id,
            "name": inst.name,
            "type": inst.type.label,
            "subtype": inst.subtype.label if inst.subtype else None,
            "ticker": inst.ticker,
            "symbol": inst.symbol,
            "isin": inst.isin,
            "exchange": inst.exchange,
            "currency": inst.currency,
            "country": inst.country,
            "issuer": inst.issuer,
            "archived": inst.archived,
            "price": {
                "value": row.price.value_num,
                "currency": p.currency if p else inst.currency,
                "date": p.reference_date.isoformat() if p and p.reference_date else None,
                "collected_at": p.collected_at.isoformat() if p else None,
                "source": p.source if p else None,
                "note": p.note if p else None,
                "status": _status(row.price.status),
            },
            "perf": row.perf,
            "potential": row.potential,
            "history": [[d.isoformat(), c] for d, c in history],
            "sections": [{"title": title, "rows": frame.to_dict(orient="records")}
                         for title, frame in sections.items()],
            "not_applicable": views.not_applicable_fields(inst),
        }


# --------------------------------------------------------------------------
# Revenus et qualité
# --------------------------------------------------------------------------

@app.get("/api/income")
def income() -> dict:
    with _session() as s:
        rows = pf.incomes(s)
    today = datetime.now(UTC).date()
    months = []
    year, month = today.year, today.month
    for _ in range(12):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    months.reverse()
    by_month = {m: 0.0 for m in months}
    missing = 0
    for r in rows:
        key = r.day.strftime("%Y-%m")
        if key in by_month:
            if r.amount_eur is None:
                missing += 1
            else:
                by_month[key] += r.amount_eur
    return {
        "total_12m": sum(by_month.values()),
        "missing_12m": missing,
        "months": [{"month": m, "value": v} for m, v in by_month.items()],
        "items": [{
            "date": r.day.isoformat(), "type": r.type.label, "instrument": r.instrument, "envelope": r.envelope,
            "amount": r.amount, "currency": r.currency, "amount_eur": r.amount_eur,
        } for r in reversed(rows[-50:])],
    }


@app.get("/api/quality")
def quality() -> dict:
    with _session() as s:
        prefs = referential.get_preferences(s)
        counts: Counter = Counter()
        for inst in referential.list_instruments(s):
            for cv in market_data.current_values(s, inst, prefs).values():
                counts[cv.status] += 1
        logs = s.scalars(select(RefreshLog).where(RefreshLog.ok.is_(False))
                         .order_by(RefreshLog.started_at.desc()).limit(5)).all()
        errors = [{"date": log.started_at.isoformat(),
                   "instrument": log.instrument.name if log.instrument else "Taux de change",
                   "message": log.message} for log in logs]
    return {"counts": [{**_status(st_), "count": counts.get(st_, 0)} for st_ in BADGES], "errors": errors}


# --------------------------------------------------------------------------
# Préférences et actualisation
# --------------------------------------------------------------------------

class PreferencesIn(BaseModel):
    mask_amounts: bool


@app.put("/api/preferences")
def set_preferences(data: PreferencesIn, x_ancora: str | None = Header(default=None)) -> dict:
    _require_app_header(x_ancora)
    with _session() as s:
        current = referential.get_preferences(s)
        referential.save_preferences(s, referential.Preferences(
            mask_amounts=data.mask_amounts, price_stale_days=current.price_stale_days,
            fundamental_stale_days=current.fundamental_stale_days))
    return {"mask_amounts": data.mask_amounts}


_refresh_lock = threading.Lock()
_refresh_state: dict = {"running": False, "done": 0, "total": 0, "current": None, "errors": [], "finished_at": None}


def _run_refresh() -> None:
    def progress(index: int, total: int, name: str) -> None:
        _refresh_state.update(done=index - 1, total=total, current=name)

    try:
        with _session() as s:
            results = market_data.refresh_all(s, build_connectors(get_config()), progress=progress)
        _refresh_state["errors"] = [f"{r.instrument} : {' '.join(r.messages)}" for r in results if not r.ok]
    except Exception as exc:  # l'état d'erreur reste consultable par l'application
        _refresh_state["errors"] = [f"Actualisation interrompue : {type(exc).__name__}"]
    finally:
        _refresh_state.update(running=False, current=None, done=_refresh_state["total"],
                              finished_at=datetime.now(UTC).replace(microsecond=0).isoformat())


@app.post("/api/refresh")
def start_refresh(x_ancora: str | None = Header(default=None)) -> dict:
    """Lance l'actualisation en arrière-plan : l'application reste utilisable pendant ce temps."""
    _require_app_header(x_ancora)
    with _refresh_lock:
        if not _refresh_state["running"]:
            _refresh_state.update(running=True, done=0, total=0, current=None, errors=[], finished_at=None)
            threading.Thread(target=_run_refresh, name="ancora-refresh", daemon=True).start()
    return dict(_refresh_state)


@app.get("/api/refresh")
def refresh_status() -> dict:
    return dict(_refresh_state)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "today": date.today().isoformat()}


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
