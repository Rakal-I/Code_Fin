"""Accès à la base SQLite locale et migrations Alembic."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import ROOT

_engines: dict[Path, Engine] = {}


def get_engine(db_path: Path) -> Engine:
    db_path = Path(db_path).resolve()
    if db_path not in _engines:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{db_path}", future=True)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            # WAL : les interfaces ordinateur et téléphone lisent pendant qu'une actualisation écrit.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.close()

        _engines[db_path] = engine
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


def upgrade_to_head(db_path: Path) -> None:
    """Crée ou met à jour le schéma : les données sont conservées entre versions."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(db_path), "head")


def session_factory(db_path: Path) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(db_path), expire_on_commit=False, future=True)


@contextmanager
def session_scope(db_path: Path) -> Iterator[Session]:
    session = session_factory(db_path)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
