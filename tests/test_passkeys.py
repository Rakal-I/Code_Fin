"""Face ID / Touch ID (clés d'accès) : ajout, connexion, refus, ordinateur et téléphone."""
import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette

from app.mobile import server
from app.services import auth, passkeys, workspace
from app.web import connexion
from tests.conftest import PASSWORD, USER, make_account
from tests.fake_authenticator import FakeAuthenticator
from tests.test_ui import populate

H = {"X-Ancora": "1"}
ORIGIN, RP = "http://testserver", "testserver"


def register(app_config, ws, authenticator):
    with workspace.directory(app_config) as d:
        account = auth.get_account(d, ws.account_id)
        started = passkeys.registration_options(d, account, RP, ORIGIN)
    assert started["options"]["authenticatorSelection"]["userVerification"] == "required"
    with workspace.directory(app_config) as d:
        return passkeys.finish_registration(d, started["challenge"], authenticator.create(started["options"]), "iPhone")


def login(app_config, authenticator, **kwargs):
    with workspace.directory(app_config) as d:
        started = passkeys.authentication_options(d, RP, ORIGIN)
    with workspace.directory(app_config) as d:
        answer = authenticator.get(started["options"], **kwargs)
        return passkeys.finish_authentication(d, started["challenge"], answer).id


def test_ajout_puis_connexion(app_config):
    ws, device = make_account(app_config), FakeAuthenticator()
    key = register(app_config, ws, device)
    assert key.name == "iPhone" and key.rp_id == RP
    assert login(app_config, device) == ws.account_id
    assert login(app_config, device) == ws.account_id  # compteur de signatures croissant
    with workspace.directory(app_config) as d:
        assert passkeys.list_passkeys(d, ws.account_id)[0].last_used_at is not None


def test_cle_inconnue_ou_supprimee(app_config):
    ws = make_account(app_config)
    with pytest.raises(passkeys.PasskeyError, match="plus enregistrée"):
        login(app_config, FakeAuthenticator())
    device = FakeAuthenticator()
    key = register(app_config, ws, device)
    with workspace.directory(app_config) as d:
        passkeys.delete_passkey(d, ws.account_id, key.id)
    with pytest.raises(passkeys.PasskeyError):
        login(app_config, device)


def test_refus_sans_face_id_ou_mauvaise_adresse(app_config):
    ws, device = make_account(app_config), FakeAuthenticator()
    register(app_config, ws, device)
    with pytest.raises(passkeys.PasskeyError, match="refusée"):
        login(app_config, device, user_verified=False)  # appareil déverrouillé sans Face ID
    phishing = FakeAuthenticator(origin="https://faux-ancora.example")
    phishing.key, phishing.credential_id = device.key, device.credential_id
    with pytest.raises(passkeys.PasskeyError, match="refusée"):
        login(app_config, phishing)  # signature valide mais émise pour un autre site


def test_defi_a_usage_unique(app_config):
    ws, device = make_account(app_config), FakeAuthenticator()
    register(app_config, ws, device)
    with workspace.directory(app_config) as d:
        started = passkeys.authentication_options(d, RP, ORIGIN)
    answer = device.get(started["options"])
    with workspace.directory(app_config) as d:
        passkeys.finish_authentication(d, started["challenge"], answer)
    with pytest.raises(passkeys.PasskeyError, match="expirée"):
        with workspace.directory(app_config) as d:
            passkeys.finish_authentication(d, started["challenge"], answer)  # rejeu


# --------------------------------------------------------------------------
# Téléphone : ajout depuis la session, puis connexion par Face ID
# --------------------------------------------------------------------------

def test_telephone(app_config):
    populate(make_account(app_config))
    device = FakeAuthenticator()
    with TestClient(server.app) as c:
        assert c.post("/connexion/cle/ajout/options", headers=H).status_code == 401  # non connecté
        c.post("/api/auth/login", json={"username": USER, "password": PASSWORD}, headers=H)
        assert c.get("/api/auth/status").json()["passkeys"] == 0
        assert c.post("/connexion/cle/ajout/options").status_code == 403  # sans en-tête X-Ancora
        started = c.post("/connexion/cle/ajout/options", headers=H).json()
        done = c.post("/connexion/cle/ajout", headers=H, json={"challenge": started["challenge"],
                                                               "credential": device.create(started["options"])})
        assert done.json() == {"ok": True}
        assert c.get("/api/auth/status").json()["passkeys"] == 1
        c.post("/api/auth/logout", headers=H)
        assert c.get("/api/summary").status_code == 401

        started = c.post("/connexion/cle/options", headers=H).json()
        back = c.post("/connexion/cle/verifier", headers=H, json={"challenge": started["challenge"],
                                                                  "credential": device.get(started["options"])})
        assert back.status_code == 200 and "ancora_session" in back.headers["set-cookie"]
        assert c.get("/api/summary").json()["lines"] == 2
        assert "javascript" in c.get("/connexion/cle.js").headers["content-type"]


# --------------------------------------------------------------------------
# Ordinateur : jeton d'ajout remis par la session Streamlit, ticket après Face ID
# --------------------------------------------------------------------------

def test_ordinateur(app_config):
    ws, device = make_account(app_config), FakeAuthenticator()
    c = TestClient(Starlette(routes=connexion.routes("desktop")))
    assert c.post("/connexion/cle/ajout/options", headers=H, json={"jeton": "faux"}).status_code == 401
    with workspace.directory(app_config) as d:
        token = auth.create_link_intent(d, ws.account_id)
    started = c.post("/connexion/cle/ajout/options", headers=H, json={"jeton": token}).json()
    c.post("/connexion/cle/ajout", headers=H, json={"challenge": started["challenge"],
                                                     "credential": device.create(started["options"])})
    assert c.post("/connexion/cle/ajout/options", headers=H, json={"jeton": token}).status_code == 401  # usage unique

    started = c.post("/connexion/cle/options", headers=H).json()
    back = c.post("/connexion/cle/verifier", headers=H, json={"challenge": started["challenge"],
                                                              "credential": device.get(started["options"])})
    ticket = back.cookies.get(connexion.TICKET_COOKIE) or c.cookies.get(connexion.TICKET_COOKIE)
    with workspace.directory(app_config) as d:
        assert auth.redeem_ticket(d, ticket).account_id == ws.account_id


def test_adresse_publique_du_codespace(monkeypatch):
    from starlette.requests import Request

    monkeypatch.setenv("CODESPACE_NAME", "ancora-xyz")
    request = Request({"type": "http", "scheme": "http", "path": "/", "server": ("localhost", 8502),
                       "headers": [(b"host", b"localhost:8502")]})
    assert connexion.origin(request) == "https://ancora-xyz-8502.app.github.dev"
    assert connexion.rp_id(request) == "ancora-xyz-8502.app.github.dev"
