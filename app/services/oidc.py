"""Connexion avec Google et Apple (OpenID Connect, flux « authorization code »).

Protections : « state » lié au navigateur (cookie), « nonce » vérifié dans le jeton d'identité,
PKCE (Google), signature du jeton vérifiée avec les clés publiques du fournisseur, audience et
émetteur contrôlés. Ancora ne reçoit jamais votre mot de passe Google ou Apple.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable
from urllib.parse import urlencode

import jwt
import requests

from app.config.settings import AppConfig, AppleConfig, GoogleConfig
from app.services.auth import PendingOAuth

TIMEOUT = 15


class OIDCError(RuntimeError):
    pass


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    client_id: str
    authorize_url: str
    token_url: str
    jwks_url: str
    issuers: tuple[str, ...]
    scope: str
    form_post: bool                     # Apple renvoie la réponse en POST quand l'e-mail est demandé
    pkce: bool
    client_secret: Callable[[], str] = field(repr=False)
    extra: tuple[tuple[str, str], ...] = ()


def google(cfg: GoogleConfig) -> Provider:
    return Provider(name="google", label="Google", client_id=cfg.client_id,
                    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
                    token_url="https://oauth2.googleapis.com/token",
                    jwks_url="https://www.googleapis.com/oauth2/v3/certs",
                    issuers=("https://accounts.google.com", "accounts.google.com"),
                    scope="openid email profile", form_post=False, pkce=True,
                    client_secret=lambda: cfg.client_secret, extra=(("prompt", "select_account"),))


def apple(cfg: AppleConfig) -> Provider:
    def secret() -> str:
        # Apple n'utilise pas de secret fixe : un jeton signé (ES256) par la clé « Sign in with Apple ».
        now = int(time.time())
        claims = {"iss": cfg.team_id, "iat": now, "exp": now + 300, "aud": "https://appleid.apple.com",
                  "sub": cfg.client_id}
        return jwt.encode(claims, cfg.private_key, algorithm="ES256", headers={"kid": cfg.key_id})

    return Provider(name="apple", label="Apple", client_id=cfg.client_id,
                    authorize_url="https://appleid.apple.com/auth/authorize",
                    token_url="https://appleid.apple.com/auth/token",
                    jwks_url="https://appleid.apple.com/auth/keys",
                    issuers=("https://appleid.apple.com",),
                    scope="name email", form_post=True, pkce=False, client_secret=secret)


def providers(config: AppConfig) -> dict[str, Provider]:
    """Fournisseurs configurés (identifiants présents dans config/secrets.toml ou l'environnement)."""
    found: dict[str, Provider] = {}
    if config.google:
        found["google"] = google(config.google)
    if config.apple:
        found["apple"] = apple(config.apple)
    return found


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorization_url(provider: Provider, redirect_uri: str, pending: PendingOAuth) -> str:
    params = {"response_type": "code", "client_id": provider.client_id, "redirect_uri": redirect_uri,
              "scope": provider.scope, "state": pending.state, "nonce": pending.nonce, **dict(provider.extra)}
    if provider.form_post:
        params["response_mode"] = "form_post"
    if provider.pkce:
        params.update(code_challenge=_challenge(pending.verifier), code_challenge_method="S256")
    return f"{provider.authorize_url}?{urlencode(params)}"


@dataclass(frozen=True)
class Claims:
    subject: str
    email: str | None
    name: str | None


@lru_cache(maxsize=4)
def _jwks(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=TIMEOUT)


def verify_id_token(provider: Provider, token: str, nonce: str) -> dict:
    try:
        key = _jwks(provider.jwks_url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256", "ES256"], audience=provider.client_id,
                            issuer=list(provider.issuers), leeway=60,
                            options={"require": ["exp", "iat", "iss", "aud", "sub"]})
    except jwt.PyJWTError as exc:
        raise OIDCError(f"Jeton d'identité refusé ({type(exc).__name__}).") from exc
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise OIDCError("Jeton d'identité refusé (nonce).")
    return claims


def exchange(provider: Provider, code: str, redirect_uri: str, verifier: str, nonce: str,
             apple_user: str | None = None) -> Claims:
    """Échange le code contre le jeton d'identité, le vérifie et renvoie l'identité."""
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
            "client_id": provider.client_id, "client_secret": provider.client_secret()}
    if provider.pkce:
        data["code_verifier"] = verifier
    try:
        response = requests.post(provider.token_url, data=data, timeout=TIMEOUT,
                                 headers={"Accept": "application/json"})
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise OIDCError(f"{provider.label} injoignable ({type(exc).__name__}).") from exc
    if response.status_code != 200 or "id_token" not in payload:
        raise OIDCError(f"{provider.label} a refusé l'échange ({payload.get('error', response.status_code)}).")
    claims = verify_id_token(provider, payload["id_token"], nonce)

    verified = claims.get("email_verified") in (True, "true")
    name = claims.get("name")
    if apple_user and not name:  # Apple n'envoie le nom qu'à la première connexion, hors du jeton
        try:
            parts = json.loads(apple_user).get("name") or {}
            name = " ".join(p for p in (parts.get("firstName"), parts.get("lastName")) if p) or None
        except (ValueError, AttributeError):
            name = None
    return Claims(subject=str(claims["sub"]), email=claims.get("email") if verified else None, name=name)
