"""Interface téléphone : API JSON."""
import time

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database.engine import dispose_engine, upgrade_to_head
from app.mobile import server
from tests.conftest import FakeConnector
from tests.test_ui import populate


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "ancora.db"
    monkeypatch.setenv("ANCORA_DB_PATH", str(db))
    monkeypatch.setenv("ANCORA_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("ANCORA_LOG_DIR", str(tmp_path / "logs"))
    settings.get_config.cache_clear()
    upgrade_to_head(db)
    populate(db)
    with TestClient(server.app) as test_client:
        yield test_client
    settings.get_config.cache_clear()
    dispose_engine(db)


def test_synthese(client):
    data = client.get("/api/summary").json()
    assert data["lines"] == 2 and data["unvalued_lines"] == 0
    assert data["value_eur"] == pytest.approx(8 * 380.0 + 5 * 340.0 / 1.12)
    assert {s["label"] for s in data["by_envelope"]} == {"PEA", "CTO"}
    assert data["positions"][0]["value_eur"] >= data["positions"][1]["value_eur"]
    assert data["positions"][0]["price_status"]["label"] == "Réelle"


def test_marches_et_fiche(client):
    items = client.get("/api/markets", params={"scope": "watchlist"}).json()["items"]
    lvmh = next(i for i in items if i["name"] == "LVMH")
    assert lvmh["price"] == pytest.approx(380.0) and lvmh["perf"]["1 an"] is not None
    indices = client.get("/api/markets", params={"scope": "indices"}).json()["items"]
    assert all(i["type"] == "Indice" for i in indices) and len(indices) == 6

    detail = client.get(f"/api/instruments/{lvmh['id']}").json()
    assert detail["price"]["source"] == "Fournisseur test"
    assert len(detail["history"]) > 3000
    titles = [s["title"] for s in detail["sections"]]
    assert "Bénéfice net par action" in titles and "Consensus des analystes" in titles
    assert client.get("/api/instruments/9999").status_code == 404


def test_revenus(client):
    data = client.get("/api/income").json()
    assert len(data["months"]) == 12
    assert data["items"][0]["amount"] == 75


def test_qualite(client):
    counts = {c["label"]: c["count"] for c in client.get("/api/quality").json()["counts"]}
    assert counts["Réelle"] > 0


def test_ecritures_protegees(client):
    assert client.put("/api/preferences", json={"mask_amounts": True}).status_code == 403
    assert client.post("/api/refresh").status_code == 403
    ok = client.put("/api/preferences", json={"mask_amounts": True}, headers={"X-Ancora": "1"})
    assert ok.status_code == 200
    assert client.get("/api/summary").json()["mask_amounts"] is True


def test_actualisation_en_arriere_plan(client, monkeypatch):
    monkeypatch.setattr(server, "build_connectors",
                        lambda _cfg: [FakeConnector({"MC.PA": 400.0, "AAPL": 350.0}, fx={"USD": 1.1})])
    started = client.post("/api/refresh", headers={"X-Ancora": "1"}).json()
    assert started["running"] is True
    for _ in range(100):
        state = client.get("/api/refresh").json()
        if not state["running"]:
            break
        time.sleep(0.1)
    assert state["running"] is False and state["finished_at"]
    assert any(i["price"] == pytest.approx(400.0) for i in client.get("/api/markets").json()["items"])
