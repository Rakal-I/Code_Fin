"""Écrans de connexion de l'interface ordinateur.

Connexion avec Apple, Google ou un identifiant et un mot de passe ; création de compte ;
association d'un compte Google / Apple à un compte existant. Verrouillage après 30 minutes
d'inactivité.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from html import escape

import streamlit as st

from app.models.entities import utcnow
from app.services import auth
from app.services import workspace as workspaces
from app.services.workspace import Workspace
from app.ui import context, theme
from app.web import connexion

AUTO_LOCK = timedelta(minutes=30)
_SEEN, _NOTICE, _PENDING, _VIEW, _TICKETS = "auth_seen", "auth_notice", "auth_pending", "auth_view", "_auth_tickets"

APPLE_SVG = ('<svg viewBox="0 0 814 1000" aria-hidden="true"><path fill="currentColor" d="M788.1 340.9c-5.8 4.5-108.2 '
             "62.2-108.2 190.5 0 148.4 130.3 200.9 134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9-42.8 61.6-87.5 123.1-155.5 "
             "123.1s-85.5-39.5-164-39.5c-76.5 0-103.7 40.8-165.9 40.8s-105.6-57-155.5-127C46.7 790.7 0 663 0 541.8c0-"
             "194.4 126.4-297.5 250.8-297.5 66.1 0 121.2 43.4 162.7 43.4 39.5 0 101.1-46 176.3-46 28.5 0 130.9 2.6 "
             "198.3 99.2zm-234-181.5c31.1-36.9 53.1-88.1 53.1-139.3 0-7.1-.6-14.3-1.9-20.1-50.6 1.9-110.8 33.7-147.1 "
             "75.8-28.5 32.4-55.1 83.6-55.1 135.5 0 7.8 1.3 15.6 1.9 18.1 3.2.6 8.4 1.3 13.6 1.3 45.4 0 102.5-30.4 "
             '135.5-71.3z"/></svg>')
GOOGLE_SVG = ('<svg viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 '
              "3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 "
              '9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 '
              '5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-'
              "1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 "
              '10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-'
              '4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>')
_ICONS = {"apple": APPLE_SVG, "google": GOOGLE_SVG}

_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stExpandSidebarButton"] { display: none; }
.block-container { max-width: 460px; padding-top: 7vh; }
.anc-login-head { text-align: center; margin-bottom: 1.3rem; }
.anc-login-head svg { margin-bottom: 1.1rem; }
.anc-login-head h1 { font-size: 1.9rem; margin: 0; }
.anc-login-head p { color: #6E6E73; margin: .35rem 0 0; }
.anc-login-foot { text-align: center; color: #86868B; font-size: .8rem; margin-top: 1rem; }
[data-testid="stForm"] { padding: 0; }
</style>
"""

SSO_CSS = """
<style>
.anc-sso { display: flex; flex-direction: column; gap: .6rem; margin: .2rem 0 .4rem; max-width: 460px; }
.anc-sso a { display: flex; align-items: center; justify-content: center; gap: .55rem; height: 46px;
  border-radius: 14px; font-weight: 600; font-size: .98rem; text-decoration: none !important;
  transition: transform .12s ease, box-shadow .2s ease; letter-spacing: -.01em; }
.anc-sso a:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(0,0,0,.10); }
.anc-sso a:active { transform: scale(.985); }
.anc-sso a svg { width: 18px; height: 18px; }
.anc-sso .apple { background: #000; color: #fff !important; }
.anc-sso .apple svg { margin-top: -3px; }
.anc-sso .google { background: rgba(255,255,255,.85); color: #1F1F1F !important; border: 1px solid #DADCE0; }
</style>
"""

OR_CSS = """
<style>
.anc-or { display: flex; align-items: center; gap: .8rem; color: #86868B; font-size: .82rem; margin: 1rem 0 .4rem; }
.anc-or::before, .anc-or::after { content: ""; flex: 1; height: 1px; background: rgba(0,0,0,.10); }
</style>
"""


def sso_buttons(label: str = "Continuer avec", link_tokens: dict[str, str] | None = None,
                only: tuple[str, ...] = ("apple", "google")) -> None:
    """Boutons Apple / Google (liens vers /connexion/…, même onglet)."""
    links = []
    for provider in only:
        href = f"/connexion/{provider}"
        if link_tokens and provider in link_tokens:
            href += f"?associer={link_tokens[provider]}"
        links.append(f'<a class="{provider}" href="{href}" target="_self">{_ICONS[provider]}'
                     f"<span>{label} {auth.PROVIDERS[provider]}</span></a>")
    st.markdown(SSO_CSS + f'<div class="anc-sso">{"".join(links)}</div>', unsafe_allow_html=True)


def _or(text: str = "ou") -> None:
    st.markdown(OR_CSS + f'<div class="anc-or">{escape(text)}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# État de connexion
# --------------------------------------------------------------------------

def logout(notice: str | None = None) -> None:
    for key in (context.ACCOUNT_KEY, _SEEN, _PENDING):
        st.session_state.pop(key, None)
    context.forget_workspace()
    if notice:
        st.session_state[_NOTICE] = notice


def _sign_in(account_id: int) -> None:
    st.session_state[context.ACCOUNT_KEY] = account_id
    st.session_state[_SEEN] = utcnow()
    st.session_state.pop(_PENDING, None)
    context.forget_workspace()


def _consume_return() -> None:
    """Retour de Google / Apple : ticket à usage unique (cookie) ou message d'erreur (paramètres d'URL)."""
    code = st.query_params.get("erreur")
    if code:
        text = connexion.message(code, st.query_params.get("fournisseur"))
        if text:
            st.session_state[_NOTICE] = text
        st.query_params.clear()
    token = st.context.cookies.get(connexion.TICKET_COOKIE)
    used: set[str] = st.session_state.setdefault(_TICKETS, set())
    if not isinstance(token, str) or not token or token in used:
        return
    used.add(token)
    with context.directory() as s:
        ticket = auth.redeem_ticket(s, token)
        if ticket is None:
            return
        if ticket.account_id is not None:
            _sign_in(ticket.account_id)
        else:
            st.session_state[_PENDING] = {"provider": ticket.provider, "subject": ticket.subject,
                                          "email": ticket.email, "name": ticket.name}


def require_login() -> Workspace:
    """Renvoie le patrimoine du compte connecté ; sinon affiche l'écran de connexion et arrête la page."""
    _consume_return()
    account_id = st.session_state.get(context.ACCOUNT_KEY)
    seen: datetime | None = st.session_state.get(_SEEN)
    now = utcnow()
    if account_id is not None:
        with context.directory() as s:
            exists = auth.get_account(s, account_id) is not None
        if not exists:
            logout("Ce compte n'existe plus : reconnectez-vous.")
        elif seen and now - seen > AUTO_LOCK:
            logout("Session verrouillée après 30 minutes d'inactivité.")
        else:
            st.session_state[_SEEN] = now
            return context.workspace()

    st.markdown(_CSS, unsafe_allow_html=True)
    with context.directory() as s:
        has_accounts = auth.accounts_exist(s)
    if st.session_state.get(_PENDING):
        _pending_identity()
    elif not has_accounts or st.session_state.get(_VIEW) == "create":
        _create(first=not has_accounts)
    else:
        _login()
    st.stop()


def _head(title: str, subtitle: str) -> None:
    logo = theme.LOGO.read_text(encoding="utf-8").replace("<svg ", '<svg style="height:64px;width:auto" ', 1)
    st.markdown(f'<div class="anc-login-head">{logo}<h1>{title}</h1><p>{subtitle}</p></div>',
                unsafe_allow_html=True)


def _notice() -> None:
    notice = st.session_state.pop(_NOTICE, None)
    if notice:
        st.info(notice)


# --------------------------------------------------------------------------
# Écrans
# --------------------------------------------------------------------------

def _login() -> None:
    _head("Bon retour", "Connectez-vous pour accéder à votre patrimoine.")
    _notice()
    sso_buttons()
    _or()
    with st.form("login", border=False):
        username = st.text_input("Identifiant", autocomplete="username")
        password = st.text_input("Mot de passe", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Se connecter", type="primary", width="stretch")
    if submitted:
        with context.directory() as s:
            result = auth.authenticate(s, username, password)
        if result.ok:
            _sign_in(result.account_id)
            st.rerun()
        st.error(result.message)
    if st.button("Nouveau sur Ancora ? Créer un compte", type="tertiary", width="stretch"):
        st.session_state[_VIEW] = "create"
        st.rerun()
    st.markdown('<p class="anc-login-foot">Mot de passe oublié : lancez <code>python scripts/reset_password.py</code> '
                "sur cet ordinateur.</p>", unsafe_allow_html=True)


def _create(first: bool) -> None:
    if first:
        _head("Bienvenue sur Ancora", "Créez votre compte. Il protège aussi la version téléphone.")
    else:
        _head("Créer un compte", "Chaque compte a ses propres données, chiffrées avec sa propre clé.")
    _notice()
    sso_buttons()
    _or("ou avec un identifiant")
    with st.form("setup", border=False):
        username = st.text_input("Identifiant", autocomplete="username")
        password = st.text_input("Mot de passe", type="password", autocomplete="new-password",
                                 help=f"Au moins {auth.MIN_PASSWORD_LENGTH} caractères, lettres et chiffres mélangés.")
        confirmation = st.text_input("Confirmation", type="password", autocomplete="new-password")
        submitted = st.form_submit_button("Créer mon compte", type="primary", width="stretch")
    if submitted:
        try:
            with context.directory() as s:
                account = workspaces.create_account(context.config(), s, username=username, password=password,
                                                    confirmation=confirmation)
                created = account.id
        except auth.AuthError as exc:
            st.error(str(exc))
        else:
            st.session_state.pop(_VIEW, None)
            _sign_in(created)
            st.rerun()
    if not first and st.button("Déjà un compte ? Se connecter", type="tertiary", width="stretch"):
        st.session_state.pop(_VIEW, None)
        st.rerun()
    st.markdown('<p class="anc-login-foot">Votre mot de passe ne quitte pas cet ordinateur : seule une empreinte '
                "est enregistrée, et vos données sont chiffrées.</p>", unsafe_allow_html=True)


def _pending_identity() -> None:
    pending = st.session_state[_PENDING]
    provider = auth.PROVIDERS.get(pending["provider"], "")
    who = f" ({escape(pending['email'])})" if pending.get("email") else ""
    _head("Presque terminé", f"Vous êtes connecté avec {provider}{who}. Aucun compte Ancora n'y est encore associé.")
    _notice()
    if st.button("Créer mon compte Ancora", type="primary", width="stretch"):
        with context.directory() as s:
            account = workspaces.create_account(context.config(), s, name=pending.get("name") or pending.get("email"),
                                                email=pending.get("email"))
            auth.link_identity(s, account, pending["provider"], pending["subject"], pending.get("email"))
            created = account.id
        _sign_in(created)
        st.rerun()
    _or("ou associez-le à votre compte existant")
    with st.form("link", border=False):
        username = st.text_input("Identifiant", autocomplete="username")
        password = st.text_input("Mot de passe", type="password", autocomplete="current-password")
        submitted = st.form_submit_button(f"Associer {provider} et se connecter", width="stretch")
    if submitted:
        error = None
        with context.directory() as s:
            result = auth.authenticate(s, username, password)
            if result.ok:
                try:
                    auth.link_identity(s, auth.get_account(s, result.account_id), pending["provider"],
                                       pending["subject"], pending.get("email"))
                except auth.AuthError as exc:
                    error = str(exc)
            else:
                error = result.message
        if error is None:
            _sign_in(result.account_id)
            st.rerun()
        st.error(error)
    other = next(p for p in auth.PROVIDERS if p != pending["provider"])
    theme.note(f"Votre compte utilise {auth.PROVIDERS[other]} ? Connectez-vous avec {auth.PROVIDERS[other]}, puis "
               f"associez {provider} dans Administration › Paramètres › Sécurité.")
    if st.button("Annuler", type="tertiary", width="stretch"):
        st.session_state.pop(_PENDING, None)
        st.rerun()


def link_tokens(account_id: int) -> dict[str, str]:
    """Jetons d'association (5 minutes) pour les boutons « Associer » des Paramètres."""
    cached = st.session_state.get("_link_tokens")
    if not cached or cached["account"] != account_id or time.time() - cached["at"] > 240:
        with context.directory() as s:
            tokens = {p: auth.create_link_intent(s, account_id) for p in auth.PROVIDERS}
        cached = {"account": account_id, "at": time.time(), "tokens": tokens}
        st.session_state["_link_tokens"] = cached
    return cached["tokens"]
