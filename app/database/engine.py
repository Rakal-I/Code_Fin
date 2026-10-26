"""Accès aux bases SQLite locales (chiffrées par SQLCipher) et migrations Alembic.

Sans clé, une base est un fichier SQLite ordinaire (tests, ancienne version) ; avec une clé,
chaque page du fichier est chiffrée en AES-256 et authentifiée (HMAC) par SQLCipher.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import sqlcipher3
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from app.config.settings import ROOT

_engines: dict[Path, Engine] = {}


def _raw_key(key: bytes) -> str:
    # Clé brute de 256 bits : SQLCipher n'applique pas de dérivation lente.
    return f"x'{key.hex()}'"


def connect_raw(db_path: Path, key: bytes | None = None, readonly: bool = False) -> sqlcipher3.Connection:
    """Connexion DB-API (sauvegardes, migration) ; lève DatabaseError si la clé est fausse."""
    target = f"file:{Path(db_path)}?mode=ro" if readonly else f"file:{Path(db_path)}"
    connection = sqlcipher3.connect(target, uri=True)
    if key is not None:
        connection.execute(f'PRAGMA key = "{_raw_key(key)}"')
    return connection


def _create_engine(db_path: Path, key: bytes | None, poolclass=QueuePool) -> Engine:
    if key is None:
        engine = create_engine(f"sqlite:///{db_path}", future=True, poolclass=poolclass)
    else:
        url = URL.create("sqlite+pysqlcipher", password=_raw_key(key), database=str(db_path))
        engine = create_engine(url, future=True, poolclass=poolclass, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL : les interfaces ordinateur et téléphone lisent pendant qu'une actualisation écrit.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()

    return engine


def get_engine(db_path: Path, key: bytes | None = None) -> Engine:
    db_path = Path(db_path).resolve()
    if db_path not in _engines:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engines[db_path] = _create_engine(db_path, key)
    return _engines[db_path]


def dispose_engine(db_path: Path) -> None:
    """Ferme les connexions (avant une restauration de sauvegarde)."""
    engine = _engines.pop(Path(db_path).resolve(), None)
    if engine is not None:
        engine.dispose()


def alembic_config(db_path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{Path(db_path).resolve()}")
    return config


def upgrade_to_head(db_path: Path, key: bytes | None = None) -> None:
    """Crée ou met à jour le schéma : les données sont conservées entre versions."""
    db_path = Path(db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    config = alembic_config(db_path)
    engine = _create_engine(db_path, key, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def session_factory(db_path: Path, key: bytes | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(db_path, key), expire_on_commit=False, future=True)


@contextmanager
def session_scope(db_path: Path, key: bytes | None = None) -> Iterator[Session]:
    session = session_factory(db_path, key)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
