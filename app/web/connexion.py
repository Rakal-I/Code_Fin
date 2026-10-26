"""Routes « Continuer avec Google / Apple », communes aux deux interfaces.

GET  /connexion/{fournisseur}          redirige vers Google ou Apple
GET|POST /connexion/{fournisseur}/retour  retour du fournisseur (Apple répond en POST)

Ordinateur : un ticket à usage unique (cookie, 2 minutes) est remis à l'écran Streamlit.
Téléphone : la session de 30 jours est ouverte directement (cookie ancora_session).
"""
from __future__ import annotations

import hmac
import logging
from urllib.parse import urlencode

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Route

from app.config.settings import get_config
from app.models.entities import utcnow
from app.services import auth, oidc, workspace

log = logging.getLogger(__name__)

STATE_COOKIE = "ancora_oauth"
TICKET_COOKIE = "ancora_ticket"
SESSION_COOKIE = "ancora_session"

MESSAGES = {
    "non-configure": "La connexion avec {p} n'est pas encore configurée sur cet ordinateur "
                     "(Administration › Paramètres › Connexion Google et Apple).",
    "refus": "Connexion avec {p} annulée.",
    "echec": "La connexion avec {p} a échoué. Réessayez.",
    "expire": "La demande de connexion a expiré. Réessayez.",
    "inconnu": "Aucun compte Ancora n'est associé à ce compte {p}. Créez votre compte ou associez-le depuis "
               "l'ordinateur (Administration › Paramètres › Sécurité).",
    "deja-associe": "Ce compte {p} est déjà associé à un autre compte Ancora.",
}


def message(code: str | None, provider: str | None) -> str | None:
    template = MESSAGES.get(code or "")
    return template.format(p=auth.PROVIDERS.get(provider or "", "ce fournisseur")) if template else None


def is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"


def base_url(request: Request) -> str:
    scheme = "https" if is_https(request) else request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}"


def redirect_uri(base: str, provider: str) -> str:
    return f"{base.rstrip('/')}/connexion/{provider}/retour"


def device_label(request: Request) -> str:
    agent = request.headers.get("user-agent", "")
    return "iPhone" if "iPhone" in agent else "iPad" if "iPad" in agent else "Navigateur"


def _back(code: str, provider: str) -> RedirectResponse:
    response = RedirectResponse("/?" + urlencode({"erreur": code, "fournisseur": provider}), status_code=303)
    response.delete_cookie(STATE_COOKIE, path="/connexion")
    return response


def routes(client: str) -> list[Route]:
    """Routes pour l'interface « desktop » (Streamlit) ou « mobile » (FastAPI)."""

    async def start(request: Request) -> Response:
        provider_name = request.path_params["provider"]
        if provider_name not in auth.PROVIDERS:
            return Response(status_code=404)
        config = get_config()
        provider = oidc.providers(config).get(provider_name)
        if provider is None:
            return _back("non-configure", provider_name)
        uri = redirect_uri(base_url(request), provider_name)

        def prepare() -> auth.PendingOAuth:
            with workspace.directory(config) as s:
                link_to = auth.consume_link_intent(s, request.query_params.get("associer")) \
                    if client == "desktop" else None
                return auth.start_oauth(s, provider_name, client, uri, link_account_id=link_to)

        pending = await run_in_threadpool(prepare)
        response = RedirectResponse(oidc.authorization_url(provider, uri, pending), status_code=303)
        # Apple répond par un POST venant de son domaine : le cookie doit alors être SameSite=None (HTTPS).
        secure = is_https(request)
        response.set_cookie(STATE_COOKIE, pending.state, max_age=auth.OAUTH_MINUTES * 60, httponly=True,
                            secure=secure, samesite="none" if secure else "lax", path="/connexion")
        return response

    async def callback(request: Request) -> Response:
        provider_name = request.path_params["provider"]
        if provider_name not in auth.PROVIDERS:
            return Response(status_code=404)
        params = dict(request.query_params)
        if request.method == "POST":
            params.update({k: v for k, v in (await request.form()).items() if isinstance(v, str)})
        state = params.get("state", "")
        cookie = request.cookies.get(STATE_COOKIE, "")
        if not state or not hmac.compare_digest(state.encode(), cookie.encode()):
            return _back("expire", provider_name)
        config = get_config()

        def consume():
            with workspace.directory(config) as s:
                record = auth.consume_oauth(s, state)
                return (record.provider, record.nonce, record.verifier, record.redirect_uri,
                        record.link_account_id) if record else None

        pending = await run_in_threadpool(consume)
        if pending is None or pending[0] != provider_name:
            return _back("expire", provider_name)
        _, nonce, verifier, uri, link_account_id = pending
        if params.get("error") or not params.get("code"):
            return _back("refus", provider_name)
        provider = oidc.providers(config).get(provider_name)
        if provider is None:
            return _back("non-configure", provider_name)
        try:
            claims = await run_in_threadpool(oidc.exchange, provider, params["code"], uri, verifier, nonce,
                                             params.get("user"))
        except oidc.OIDCError as exc:
            log.warning("Connexion %s refusée : %s", provider_name, exc)
            return _back("echec", provider_name)

        def finish() -> tuple[str, str | None]:
            """Renvoie (résultat, jeton) : « ticket », « session », ou un code d'erreur."""
            with workspace.directory(config) as s:
                if link_account_id is not None:
                    account = auth.get_account(s, link_account_id)
                    try:
                        auth.link_identity(s, account, provider_name, claims.subject, claims.email)
                    except auth.AuthError:
                        return "deja-associe", None
                else:
                    identity = auth.find_identity(s, provider_name, claims.subject)
                    account = identity.account if identity else None
                    if identity and claims.email:
                        identity.email = claims.email
                if account is None:
                    if client == "mobile":
                        return "inconnu", None
                    # Ordinateur : l'utilisateur choisit de créer un compte ou d'associer son compte existant.
                    return "ticket", auth.issue_ticket(s, provider=provider_name, subject=claims.subject,
                                                       email=claims.email, name=claims.name)
                account.last_login_at = utcnow()
                if client == "mobile":
                    return "session", auth.create_session(s, account.id, device_label(request))
                return "ticket", auth.issue_ticket(s, account_id=account.id)

        outcome, token = await run_in_threadpool(finish)
        if token is None:
            return _back(outcome, provider_name)
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(STATE_COOKIE, path="/connexion")
        secure = is_https(request)
        if outcome == "session":
            response.set_cookie(SESSION_COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True,
                                samesite="strict", secure=secure, path="/")
        else:
            response.set_cookie(TICKET_COOKIE, token, max_age=auth.TICKET_MINUTES * 60, httponly=True,
                                samesite="lax", secure=secure, path="/")
        log.info("Connexion %s réussie (%s).", provider_name, client)
        return response

    return [
        Route("/connexion/{provider}", start, methods=["GET"]),
        Route("/connexion/{provider}/retour", callback, methods=["GET", "POST"]),
    ]
