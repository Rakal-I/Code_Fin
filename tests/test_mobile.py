"""Interface téléphone : API JSON."""
import time

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database.engine import dispose_engine, session_scope, upgrade_to_head
from app.mobile import server
from app.services import auth
from tests.conftest import FakeConnector
from tests.test_ui import populate

USER, PASSWORD = "proprietaire", "Patrimoine2026"


@pytest.fixture
def anonymous(tmp_path, monkeypatch):
    """Client non connecté, sur une base remplie avec un compte configuré."""
    db = tmp_path / "ancora.db"
    monkeypatch.setenv("ANCORA_DB_PATH", str(db))
    monkeypatch.setenv("ANCORA_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("ANCORA_LOG_DIR", str(tmp_path / "logs"))
    settings.get_config.cache_clear()
    upgrade_to_head(db)
    populate(db)
    with session_scope(db) as s:
        auth.create_account(s, USER, PASSWORD, PASSWORD)
    with TestClient(server.app) as test_client:
        yield test_client
    settings.get_config.cache_clear()
    dispose_engine(db)


@pytest.fixture
def client(anonymous):
    response = anonymous.post("/api/auth/login", json={"username": USER, "password": PASSWORD},
                              headers={"X-Ancora": "1"})
    assert response.status_code == 200
    return anonymous


def test_api_protegee_sans_connexion(anonymous):
    for path in ("/api/summary", "/api/markets", "/api/instruments/7", "/api/income", "/api/quality",
                 "/api/refresh"):
        assert anonymous.get(path).status_code == 401, path
    status = anonymous.get("/api/auth/status").json()
    assert status == {"configured": True, "authenticated": False, "username": None}
    assert anonymous.get("/").status_code == 200  # l'écran de connexion lui-même reste accessible


def test_connexion_et_deconnexion(anonymous):
    bad = anonymous.post("/api/auth/login", json={"username": USER, "password": "mauvais"}, headers={"X-Ancora": "1"})
    assert bad.status_code == 401 and "incorrect" in bad.json()["detail"]
    assert anonymous.post("/api/auth/login", json={"username": USER, "password": PASSWORD}).status_code == 403
    ok = anonymous.post("/api/auth/login", json={"username": USER, "password": PASSWORD}, headers={"X-Ancora": "1"})
    cookie = ok.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert anonymous.get("/api/summary").status_code == 200
    assert anonymous.get("/api/auth/status").json()["username"] == USER
    anonymous.post("/api/auth/logout", headers={"X-Ancora": "1"})
    assert anonymous.get("/api/summary").status_code == 401


def test_blocage_apres_echecs(anonymous):
    for _ in range(auth.MAX_FAILURES):
        anonymous.post("/api/auth/login", json={"username": USER, "password": "x"}, headers={"X-Ancora": "1"})
    locked = anonymous.post("/api/auth/login", json={"username": USER, "password": PASSWORD},
                            headers={"X-Ancora": "1"})
    assert locked.status_code == 429


def test_aucun_compte_configure(tmp_path, monkeypatch):
    db = tmp_path / "vide.db"
    monkeypatch.setenv("ANCORA_DB_PATH", str(db))
    monkeypatch.setenv("ANCORA_LOG_DIR", str(tmp_path / "logs"))
    settings.get_config.cache_clear()
    try:
        with TestClient(server.app) as c:
            assert c.get("/api/auth/status").json()["configured"] is False
            assert c.get("/api/summary").status_code == 401
    finally:
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
