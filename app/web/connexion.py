"""Routes « Face ID / Touch ID » (clés d'accès), communes aux deux interfaces.

POST /connexion/cle/options       défi de connexion
POST /connexion/cle/verifier      vérifie la signature et connecte
POST /connexion/cle/ajout/options défi d'ajout (compte connecté)
POST /connexion/cle/ajout         enregistre la clé publique
GET  /connexion/cle.js            script navigateur (appel de Face ID)

Ordinateur : un ticket à usage unique (cookie, 2 minutes) est remis à l'écran Streamlit, qui se
recharge. Téléphone : la session de 30 jours est ouverte directement (cookie ancora_session).
Les POST exigent l'en-tête X-Ancora : un autre site ne peut pas les envoyer à votre place.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from app.config.settings import get_config
from app.services import auth, passkeys, workspace

log = logging.getLogger(__name__)

TICKET_COOKIE = "ancora_ticket"
SESSION_COOKIE = "ancora_session"
SCRIPT = Path(__file__).with_name("passkey.js")


def is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"


def origin(request: Request) -> str:
    """Adresse vue par le navigateur (le Codespace ou Tailscale sont des relais HTTPS).

    Face ID n'accepte que l'adresse exacte de la page : dans un Codespace, si le relais transmet
    « localhost:8501 », on reconstitue l'adresse publique https://<codespace>-8501.app.github.dev.
    """
    scheme = "https" if is_https(request) else request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    codespace = os.environ.get("CODESPACE_NAME")
    if codespace and host.split(":")[0] in ("localhost", "127.0.0.1", "0.0.0.0"):
        port = host.split(":")[1] if ":" in host else str(request.url.port or "")
        domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
        return f"https://{codespace}-{port}.{domain}"
    return f"{scheme}://{host}"


def rp_id(request: Request) -> str:
    return origin(request).split("://", 1)[1].split(":", 1)[0]


def device_label(request: Request) -> str:
    agent = request.headers.get("user-agent", "")
    for marker, label in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                          ("Macintosh", "Mac"), ("Windows", "Windows")):
        if marker in agent:
            return label
    return "Navigateur"


def _error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=status)


async def _json(request: Request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def routes(client: str) -> list[Route]:
    """Routes pour l'interface « desktop » (Streamlit) ou « mobile » (FastAPI)."""

    def guarded(handler):
        async def wrapper(request: Request) -> Response:
            if request.headers.get("x-ancora") != "1":
                return _error("Requête refusée.", 403)
            return await handler(request)
        return wrapper

    def _account_for_ajout(s, request: Request, data: dict):
        if client == "mobile":
            return auth.resolve_session(s, request.cookies.get(SESSION_COOKIE))
        return auth.get_account(s, auth.consume_link_intent(s, data.get("jeton")))

    async def login_options(request: Request) -> Response:
        def run():
            with workspace.directory(get_config()) as s:
                return passkeys.authentication_options(s, rp_id(request), origin(request))
        return JSONResponse(await run_in_threadpool(run))

    async def login_verify(request: Request) -> Response:
        data = await _json(request)

        def run() -> tuple[str | None, str | None]:
            with workspace.directory(get_config()) as s:
                try:
                    account = passkeys.finish_authentication(s, data.get("challenge"), data.get("credential") or {})
                except passkeys.PasskeyError as exc:
                    return None, str(exc)
                if client == "mobile":
                    return auth.create_session(s, account.id, device_label(request)), None
                return auth.issue_ticket(s, account.id), None

        token, error = await run_in_threadpool(run)
        if error:
            return _error(error, 401)
        response = JSONResponse({"ok": True})
        if client == "mobile":
            response.set_cookie(SESSION_COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True,
                                samesite="strict", secure=is_https(request), path="/")
        else:
            response.set_cookie(TICKET_COOKIE, token, max_age=auth.TICKET_MINUTES * 60, httponly=True,
                                samesite="strict", secure=is_https(request), path="/")
        log.info("Connexion par clé d'accès (%s).", client)
        return response

    async def add_options(request: Request) -> Response:
        data = await _json(request)

        def run():
            with workspace.directory(get_config()) as s:
                account = _account_for_ajout(s, request, data)
                if account is None:
                    return None
                return passkeys.registration_options(s, account, rp_id(request), origin(request))

        result = await run_in_threadpool(run)
        return JSONResponse(result) if result else _error("Connexion requise.", 401)

    async def add_finish(request: Request) -> Response:
        data = await _json(request)

        def run() -> str | None:
            with workspace.directory(get_config()) as s:
                try:
                    passkeys.finish_registration(s, data.get("challenge"), data.get("credential") or {},
                                                 device_label(request))
                except passkeys.PasskeyError as exc:
                    return str(exc)
            return None

        error = await run_in_threadpool(run)
        return _error(error) if error else JSONResponse({"ok": True})

    async def script(_request: Request) -> Response:
        return Response(SCRIPT.read_text(encoding="utf-8"), media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})

    return [
        Route("/connexion/cle.js", script, methods=["GET"]),
        Route("/connexion/cle/options", guarded(login_options), methods=["POST"]),
        Route("/connexion/cle/verifier", guarded(login_verify), methods=["POST"]),
        Route("/connexion/cle/ajout/options", guarded(add_options), methods=["POST"]),
        Route("/connexion/cle/ajout", guarded(add_finish), methods=["POST"]),
    ]
