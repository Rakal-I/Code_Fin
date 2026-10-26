"""Google / Apple : vérification du jeton d'identité, secret Apple, routes de l'interface ordinateur."""
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from starlette.applications import Starlette
from starlette.testclient import TestClient

from app.config.settings import AppleConfig, GoogleConfig
from app.services import auth, oidc, workspace
from app.services.auth import PendingOAuth
from app.web import connexion
from tests.conftest import make_account

RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
GOOGLE = oidc.google(GoogleConfig(client_id="client-test.apps.googleusercontent.com", client_secret="s"))


class _Jwks:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, _token):
        return self


@pytest.fixture(autouse=True)
def _cles_publiques(monkeypatch):
    monkeypatch.setattr(oidc, "_jwks", lambda _url: _Jwks(RSA_KEY.public_key()))


def id_token(**overrides) -> str:
    now = int(time.time())
    claims = {"iss": "https://accounts.google.com", "aud": GOOGLE.client_id, "sub": "1234", "iat": now,
              "exp": now + 600, "nonce": "n-1", "email": "camille@exemple.fr", "email_verified": True}
    claims.update(overrides)
    return jwt.encode(claims, RSA_KEY, algorithm="RS256")


def test_jeton_valide():
    assert oidc.verify_id_token(GOOGLE, id_token(), "n-1")["sub"] == "1234"


@pytest.mark.parametrize("overrides,nonce", [
    ({"aud": "autre-application"}, "n-1"),            # jeton émis pour un autre site
    ({"iss": "https://pirate.example"}, "n-1"),        # mauvais émetteur
    ({"exp": int(time.time()) - 3600}, "n-1"),        # expiré
    ({}, "n-2"),                                        # rejeu d'un jeton d'une autre demande
])
def test_jetons_refuses(overrides, nonce):
    with pytest.raises(oidc.OIDCError):
        oidc.verify_id_token(GOOGLE, id_token(**overrides), nonce)


def test_signature_falsifiee():
    forged = jwt.encode({"sub": "1234"}, rsa.generate_private_key(public_exponent=65537, key_size=2048),
                        algorithm="RS256")
    with pytest.raises(oidc.OIDCError):
        oidc.verify_id_token(GOOGLE, forged, "n-1")


def test_echange_du_code(monkeypatch):
    sent = {}

    class Response:
        status_code = 200

        def json(self):
            return {"id_token": id_token(email_verified=False)}

    def post(url, data, **_kwargs):
        sent.update(data, url=url)
        return Response()

    monkeypatch.setattr(oidc.requests, "post", post)
    claims = oidc.exchange(GOOGLE, "code-1", "http://localhost:8501/connexion/google/retour", "verif", "n-1")
    assert claims.subject == "1234" and claims.email is None  # adresse non vérifiée : ignorée
    assert sent["code_verifier"] == "verif" and sent["url"] == GOOGLE.token_url


def test_url_d_autorisation():
    pending = PendingOAuth(state="st", nonce="no", verifier="v" * 43)
    google = parse_qs(urlparse(oidc.authorization_url(GOOGLE, "http://localhost/r", pending)).query)
    assert google["code_challenge_method"] == ["S256"] and google["nonce"] == ["no"] and google["state"] == ["st"]
    apple = oidc.apple(AppleConfig(client_id="fr.exemple.ancora", team_id="T", key_id="K", private_key="-"))
    query = parse_qs(urlparse(oidc.authorization_url(apple, "https://a.fr/r", pending)).query)
    assert query["response_mode"] == ["form_post"] and query["scope"] == ["name email"]


def test_secret_apple_signe():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    apple = oidc.apple(AppleConfig(client_id="fr.exemple.ancora", team_id="TEAM123", key_id="KEY123",
                                   private_key=pem))
    secret = apple.client_secret()
    assert jwt.get_unverified_header(secret)["kid"] == "KEY123"
    claims = jwt.decode(secret, key.public_key(), algorithms=["ES256"], audience="https://appleid.apple.com")
    assert claims["iss"] == "TEAM123" and claims["sub"] == "fr.exemple.ancora" and claims["exp"] - claims["iat"] <= 300


# --------------------------------------------------------------------------
# Routes de l'interface ordinateur (ticket remis à Streamlit)
# --------------------------------------------------------------------------

@pytest.fixture
def desktop(app_config, monkeypatch):
    apple = oidc.apple(AppleConfig(client_id="fr.exemple.ancora", team_id="T", key_id="K", private_key="-"))
    monkeypatch.setattr(oidc, "providers", lambda _config: {"google": GOOGLE, "apple": apple})
    monkeypatch.setattr(oidc, "exchange", lambda p, code, uri, verifier, nonce, user=None:
                        oidc.Claims(subject=f"{p.name}-1", email=None, name="Camille"))
    return TestClient(Starlette(routes=connexion.routes("desktop")), base_url="https://ancora.exemple.fr")


def _state(client, url):
    response = client.get(url, follow_redirects=False)
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=none" in cookie and "secure" in cookie  # HTTPS : POST d'Apple
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def test_ordinateur_identite_inconnue_puis_ticket(desktop, app_config):
    state = _state(desktop, "/connexion/apple")
    back = desktop.post("/connexion/apple/retour", data={"state": state, "code": "c",
                                                         "user": '{"name":{"firstName":"Camille"}}'},
                        follow_redirects=False)
    assert back.status_code == 303
    ticket = back.cookies.get(connexion.TICKET_COOKIE) or desktop.cookies.get(connexion.TICKET_COOKIE)
    with workspace.directory(app_config) as d:
        pending = auth.redeem_ticket(d, ticket)
        assert pending.account_id is None and pending.provider == "apple" and pending.subject == "apple-1"
        assert auth.redeem_ticket(d, ticket) is None


def test_ordinateur_associer_depuis_les_parametres(desktop, app_config):
    ws = make_account(app_config)
    with workspace.directory(app_config) as d:
        intent = auth.create_link_intent(d, ws.account_id)
    state = _state(desktop, f"/connexion/google?associer={intent}")
    desktop.get("/connexion/google/retour", params={"state": state, "code": "c"}, follow_redirects=False)
    ticket = desktop.cookies.get(connexion.TICKET_COOKIE)
    with workspace.directory(app_config) as d:
        assert auth.find_identity(d, "google", "google-1").account_id == ws.account_id
        assert auth.redeem_ticket(d, ticket).account_id == ws.account_id
