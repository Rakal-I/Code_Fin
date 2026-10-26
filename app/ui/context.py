"""Contexte partagé par les pages : configuration, compte connecté, préférences."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import streamlit as st
from sqlalchemy.orm import Session

from app.bootstrap import bootstrap
from app.config.settings import AppConfig, get_config
from app.connectors.base import Connector
from app.connectors.registry import build_connectors
from app.services import workspace as workspaces
from app.services.referential import Preferences, get_preferences
from app.services.workspace import Workspace

ACCOUNT_KEY = "auth_account"
_WORKSPACE_KEY = "_workspace"


@st.cache_resource(show_spinner=False)
def _bootstrap(data_dir: str) -> bool:
    bootstrap(get_config())
    return True


def config() -> AppConfig:
    cfg = get_config()
    _bootstrap(str(cfg.data_dir))
    return cfg


@contextmanager
def directory() -> Iterator[Session]:
    """Annuaire des comptes (chiffré)."""
    with workspaces.directory(config()) as s:
        yield s


def workspace() -> Workspace:
    """Patrimoine du compte connecté ; aucune donnée n'est lisible sans connexion."""
    account_id = st.session_state.get(ACCOUNT_KEY)
    if account_id is None:
        st.info("Connectez-vous pour accéder à votre patrimoine.")
        st.stop()
    cached: Workspace | None = st.session_state.get(_WORKSPACE_KEY)
    if cached is None or cached.account_id != account_id:
        cached = workspaces.workspace_for(config(), account_id)
        if cached is None:
            st.session_state.pop(ACCOUNT_KEY, None)
            st.stop()
        st.session_state[_WORKSPACE_KEY] = cached
    return cached


def forget_workspace() -> None:
    st.session_state.pop(_WORKSPACE_KEY, None)


@contextmanager
def session() -> Iterator[Session]:
    with workspace().session() as s:
        yield s


def prefs() -> Preferences:
    with session() as s:
        stored = get_preferences(s)
    if "mask_amounts" in st.session_state:
        return Preferences(mask_amounts=st.session_state["mask_amounts"],
                           price_stale_days=stored.price_stale_days,
                           fundamental_stale_days=stored.fundamental_stale_days)
    return stored


def connectors() -> list[Connector]:
    return build_connectors(config())
