"""Écran de connexion de l'interface ordinateur.

Premier lancement : création de l'accès. Ensuite : identifiant + mot de passe.
La session se verrouille après 30 minutes d'inactivité.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import streamlit as st

from app.models.entities import utcnow
from app.services import auth
from app.ui import context, theme

AUTO_LOCK = timedelta(minutes=30)
_USER, _SEEN, _NOTICE = "auth_user", "auth_seen", "auth_notice"

_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stExpandSidebarButton"] { display: none; }
.block-container { max-width: 460px; padding-top: 9vh; }
.anc-login-head { text-align: center; margin-bottom: 1.4rem; }
.anc-login-head img { height: 64px; margin-bottom: 1.1rem; }
.anc-login-head h1 { font-size: 1.9rem; margin: 0; }
.anc-login-head p { color: #6E6E73; margin: .35rem 0 0; }
.anc-login-foot { text-align: center; color: #86868B; font-size: .8rem; margin-top: 1.2rem; }
[data-testid="stForm"] { padding: 1.6rem 1.6rem 1.2rem; }
</style>
"""


def logout(notice: str | None = None) -> None:
    for key in (_USER, _SEEN):
        st.session_state.pop(key, None)
    if notice:
        st.session_state[_NOTICE] = notice


def require_login() -> str:
    """Renvoie l'identifiant connecté ; sinon affiche l'écran de connexion et arrête la page."""
    with context.session() as s:
        account = auth.get_account(s)
        username = account.username if account else None

    user = st.session_state.get(_USER)
    seen: datetime | None = st.session_state.get(_SEEN)
    now = utcnow()
    if user and (username is None or user != username):
        logout("Votre accès a été réinitialisé : reconnectez-vous.")
        user = None
    if user and seen and now - seen > AUTO_LOCK:
        logout("Session verrouillée après 30 minutes d'inactivité.")
        user = None
    if user:
        st.session_state[_SEEN] = now
        return user

    st.markdown(_CSS, unsafe_allow_html=True)
    if username is None:
        _setup()
    else:
        _login()
    st.stop()


def _head(title: str, subtitle: str) -> None:
    logo = theme.LOGO.read_text(encoding="utf-8").replace("<svg ", '<svg style="height:64px;width:auto" ', 1)
    st.markdown(f'<div class="anc-login-head">{logo}<h1>{title}</h1><p>{subtitle}</p></div>',
                unsafe_allow_html=True)


def _login() -> None:
    _head("Bon retour", "Connectez-vous pour accéder à votre patrimoine.")
    notice = st.session_state.pop(_NOTICE, None)
    if notice:
        st.info(notice)
    with st.form("login", border=False):
        username = st.text_input("Identifiant", autocomplete="username")
        password = st.text_input("Mot de passe", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Se connecter", type="primary", width="stretch")
    if submitted:
        with context.session() as s:
            result = auth.authenticate(s, username, password)
            account = auth.get_account(s)
        if result.ok:
            st.session_state[_USER] = account.username
            st.session_state[_SEEN] = utcnow()
            st.rerun()
        st.error(result.message)
    st.markdown('<p class="anc-login-foot">Mot de passe oublié : lancez <code>python scripts/reset_password.py</code> '
                "sur cet ordinateur.</p>", unsafe_allow_html=True)


def _setup() -> None:
    _head("Bienvenue sur Ancora", "Créez votre accès. Il protégera aussi la version téléphone.")
    with st.form("setup", border=False):
        username = st.text_input("Identifiant", autocomplete="username")
        password = st.text_input("Mot de passe", type="password", autocomplete="new-password",
                                 help=f"Au moins {auth.MIN_PASSWORD_LENGTH} caractères, lettres et chiffres mélangés.")
        confirmation = st.text_input("Confirmation", type="password", autocomplete="new-password")
        submitted = st.form_submit_button("Créer mon accès", type="primary", width="stretch")
    if submitted:
        try:
            with context.session() as s:
                account = auth.create_account(s, username, password, confirmation)
                created = account.username
        except auth.AuthError as exc:
            st.error(str(exc))
        else:
            st.session_state[_USER] = created
            st.session_state[_SEEN] = utcnow()
            st.rerun()
    st.markdown('<p class="anc-login-foot">Votre mot de passe ne quitte pas cet ordinateur : seule une empreinte '
                "chiffrée est enregistrée.</p>", unsafe_allow_html=True)
