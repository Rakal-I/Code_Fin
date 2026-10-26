"""Contexte partagé par les pages : configuration, base, préférences."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import streamlit as st
from sqlalchemy.orm import Session

from app.bootstrap import bootstrap
from app.config.settings import AppConfig, get_config
from app.connectors.base import Connector
from app.connectors.registry import build_connectors
from app.database.engine import session_scope
from app.services.referential import Preferences, get_preferences


@st.cache_resource(show_spinner=False)
def _bootstrap(db_path: str) -> bool:
    bootstrap(get_config())
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
