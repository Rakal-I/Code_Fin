"""Écrans de connexion de l'interface ordinateur.

Création de compte (identifiant et mot de passe), puis connexion par mot de passe ou par
Face ID / Touch ID (clé d'accès). Verrouillage après 30 minutes d'inactivité.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

import streamlit as st

from app.models.entities import utcnow
from app.services import auth, passkeys
from app.services import workspace as workspaces
from app.services.workspace import Workspace
from app.ui import context, theme
from app.web.connexion import TICKET_COOKIE

AUTO_LOCK = timedelta(minutes=30)
_SEEN, _NOTICE, _VIEW, _TICKETS, _OFFER = "auth_seen", "auth_notice", "auth_view", "_auth_tickets", "_passkey_offer"

PASSKEY_JS = (Path(__file__).resolve().parents[1] / "web" / "passkey.js").read_text(encoding="utf-8")
FACE_ID_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
               'stroke-linejoin="round" aria-hidden="true"><path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2'
               'M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><path d="M9 9v1.5M15 9v1.5M12 9v4h-1"/>'
               '<path d="M9.5 16a3.5 3.5 0 0 0 5 0"/></svg>')

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

PASSKEY_CSS = """
<style>
.anc-pk { display: flex; flex-direction: column; gap: .4rem; max-width: 460px; }
.anc-pk button { display: flex; align-items: center; justify-content: center; gap: .55rem; height: 46px;
  border-radius: 14px; font: inherit; font-weight: 600; font-size: .98rem; cursor: pointer; letter-spacing: -.01em;
  background: #000; color: #fff; border: 0; transition: transform .12s ease, box-shadow .2s ease; }
.anc-pk button.secondary { background: rgba(255,255,255,.85); color: #1D1D1F; border: 1px solid rgba(0,0,0,.12); }
.anc-pk button:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(0,0,0,.10); }
.anc-pk button:active { transform: scale(.985); }
.anc-pk button:disabled { opacity: .5; cursor: default; transform: none; }
.anc-pk button svg { width: 20px; height: 20px; }
.anc-pk p { margin: 0; min-height: 1.1em; font-size: .85rem; color: #6E6E73; text-align: center; }
.anc-pk p.err { color: #D70015; }
.anc-pk p.ok { color: #1E8E3E; }
</style>
"""

OR_CSS = """
<style>
.anc-or { display: flex; align-items: center; gap: .8rem; color: #86868B; font-size: .82rem; margin: 1rem 0 .4rem; }
.anc-or::before, .anc-or::after { content: ""; flex: 1; height: 1px; background: rgba(0,0,0,.10); }
</style>
"""


def passkey_button(mode: str, key: str, token: str | None = None, label: str | None = None,
                   secondary: bool = False) -> None:
    """Bouton Face ID / Touch ID. mode « login » : connexion puis rechargement ; « add » : ajout de la clé.

    Le libellé s'adapte à l'appareil (Face ID, Touch ID, Windows Hello) ; le bouton disparaît si le
    navigateur ne gère pas les clés d'accès (ou si l'adresse n'est pas sécurisée).
    """
    action = ("await AncoraPasskey.login(); msg.className = 'ok'; msg.textContent = 'Connexion…'; "
              "setTimeout(() => location.reload(), 150);") if mode == "login" else (
              f"await AncoraPasskey.register({{jeton: {token!r}}}); msg.className = 'ok'; "
              "msg.textContent = 'C’est activé : la prochaine fois, connectez-vous avec ' + name + '.'; "
              "btn.disabled = true;")
    text = label or ("Se connecter avec {name}" if mode == "login" else "Activer {name} sur cet appareil")
    st.html(f"""{PASSKEY_CSS}<div class="anc-pk" id="pk-{key}">
<button type="button" class="{'secondary' if secondary else ''}">{FACE_ID_SVG}<span></span></button><p></p></div>
<script>{PASSKEY_JS}
(function () {{
  const box = document.getElementById("pk-{key}"); if (!box) return;
  const btn = box.querySelector("button"), msg = box.querySelector("p"), name = AncoraPasskey.label();
  if (!AncoraPasskey.supported()) {{ box.style.display = "none"; return; }}
  btn.querySelector("span").textContent = {text!r}.replace("{{name}}", name);
  btn.onclick = async () => {{
    btn.disabled = true; msg.className = ""; msg.textContent = "";
    try {{ {action} }}
    catch (error) {{ msg.className = "err"; msg.textContent = AncoraPasskey.friendly(error); btn.disabled = false; }}
  }};
}})();
</script>""", unsafe_allow_javascript=True)


def _or(text: str = "ou") -> None:
    st.markdown(OR_CSS + f'<div class="anc-or">{escape(text)}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# État de connexion
# --------------------------------------------------------------------------

def logout(notice: str | None = None) -> None:
    for key in (context.ACCOUNT_KEY, _SEEN, _OFFER):
        st.session_state.pop(key, None)
    context.forget_workspace()
    if notice:
        st.session_state[_NOTICE] = notice


def _sign_in(account_id: int) -> None:
    st.session_state[context.ACCOUNT_KEY] = account_id
    st.session_state[_SEEN] = utcnow()
    context.forget_workspace()


def _consume_return() -> None:
    """Après Face ID / Touch ID : ticket à usage unique déposé en cookie par /connexion/cle/verifier."""
    token = st.context.cookies.get(TICKET_COOKIE)
    used: set[str] = st.session_state.setdefault(_TICKETS, set())
    if not isinstance(token, str) or not token or token in used:
        return
    used.add(token)
    with context.directory() as s:
        ticket = auth.redeem_ticket(s, token)
        if ticket is not None:
            _sign_in(ticket.account_id)


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
    if not has_accounts or st.session_state.get(_VIEW) == "create":
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
    passkey_button("login", "login")
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
                "est enregistrée, et vos données sont chiffrées. Vous pourrez ensuite activer Face ID ou Touch ID."
                "</p>", unsafe_allow_html=True)


def ajout_token(account_id: int) -> str:
    """Jeton (5 minutes) autorisant l'ajout d'une clé d'accès depuis cette session."""
    cached = st.session_state.get("_ajout_token")
    if not cached or cached["account"] != account_id or time.time() - cached["at"] > 240:
        with context.directory() as s:
            cached = {"account": account_id, "at": time.time(), "token": auth.create_link_intent(s, account_id)}
        st.session_state["_ajout_token"] = cached
    return cached["token"]


def offer_passkey(ws: Workspace) -> None:
    """Après la connexion : proposer Face ID / Touch ID tant qu'aucune clé n'est enregistrée."""
    if st.session_state.get(_OFFER) == "non":
        return
    with context.directory() as s:
        if passkeys.list_passkeys(s, ws.account_id):
            return
    with st.container(border=True):
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.markdown("**Connexion express** — la prochaine fois, connectez-vous d'un regard ou d'une empreinte, "
                    "sans mot de passe.")
        with c1:
            passkey_button("add", "offer", ajout_token(ws.account_id))
        if c2.button("Plus tard", key="passkey_later", type="tertiary"):
            st.session_state[_OFFER] = "non"
            st.rerun()
