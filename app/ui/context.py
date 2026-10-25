"""Contexte partagé par les pages : configuration, base, préférences."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import streamlit as st
from sqlalchemy.orm import Session

from app.config.settings import AppConfig, get_config
from app.connectors.base import Connector
from app.connectors.registry import build_connectors
from app.database.engine import session_scope, upgrade_to_head
from app.services.logging_setup import setup_logging
from app.services.referential import Preferences, get_preferences, seed_default_indices


@st.cache_resource(show_spinner=False)
def _bootstrap(db_path: str) -> bool:
    """Démarrage : journaux, migrations, indices par défaut. Aucun appel réseau."""
    config = get_config()
    setup_logging(config.log_dir, config.secret_values())
    upgrade_to_head(config.db_path)
    with session_scope(config.db_path) as session:
        seed_default_indices(session)
    return True


def config() -> AppConfig:
    cfg = get_config()
    _bootstrap(str(cfg.db_path))
    return cfg


@contextmanager
def session() -> Iterator[Session]:
    with session_scope(config().db_path) as s:
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
