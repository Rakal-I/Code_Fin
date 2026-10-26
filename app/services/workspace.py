"""Espaces de données : l'annuaire des comptes et la base chiffrée de chaque compte.

data/annuaire.db          comptes, identités Google / Apple, sessions (clé dérivée de la clé maître)
data/comptes/<id>.db      patrimoine d'un compte (sa propre clé, enveloppée dans l'annuaire)
backups/<id>/             sauvegardes de ce compte, chiffrées avec la même clé
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from app.config.settings import AppConfig
from app.database.engine import connect_raw, dispose_engine, get_engine, session_scope, upgrade_to_head
from app.models.directory import Account, DirectoryBase
from app.services import auth, backup, vault
from app.services.referential import seed_default_indices

log = logging.getLogger(__name__)

_SQLITE_HEADER = b"SQLite format 3\x00"
_lock = threading.RLock()
_ready_directories: set[Path] = set()
_ready_stores: set[Path] = set()


@dataclass(frozen=True)
class Workspace:
    """Patrimoine d'un compte : base et sauvegardes chiffrées avec la clé de ce compte."""

    account_id: int
    uuid: str
    name: str
    db_path: Path
    key: bytes
    backup_dir: Path

    @contextmanager
    def session(self) -> Iterator[Session]:
        with session_scope(self.db_path, self.key) as s:
            yield s

    def __repr__(self) -> str:  # la clé n'apparaît jamais dans un journal
        return f"Workspace({self.uuid[:8]}…)"


def master(config: AppConfig) -> bytes:
    return vault.master_key(config.key_file)


def _directory_key(config: AppConfig) -> bytes:
    return vault.derive(master(config), "annuaire")


@contextmanager
def directory(config: AppConfig) -> Iterator[Session]:
    """Session sur l'annuaire chiffré (créé et migré au premier appel)."""
    ensure_directory(config)
    with session_scope(config.directory_path, _directory_key(config)) as s:
        yield s


def ensure_directory(config: AppConfig) -> None:
    path = config.directory_path.resolve()
    if path in _ready_directories:
        return
    with _lock:
        if path in _ready_directories:
            return
        try:
            DirectoryBase.metadata.create_all(get_engine(path, _directory_key(config)))
        except DatabaseError as exc:
            dispose_engine(path)
            raise vault.VaultError(
                "L'annuaire des comptes ne peut pas être déchiffré : la clé maître de cet ordinateur ne "
                "correspond pas (voir « Clé de secours » dans le README).") from exc
        with session_scope(path, _directory_key(config)) as s:
            _migrate_legacy_account(config, s)
        _ready_directories.add(path)


def is_plaintext(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < len(_SQLITE_HEADER):
        return False
    with path.open("rb") as handle:
        return handle.read(len(_SQLITE_HEADER)) == _SQLITE_HEADER


# --------------------------------------------------------------------------
# Comptes
# --------------------------------------------------------------------------

def create_account(config: AppConfig, s: Session, **fields) -> Account:
    """Crée le compte dans l'annuaire ; sa base chiffrée est créée à la première ouverture."""
    return auth.create_account(s, master(config), **fields)


def open_workspace(config: AppConfig, account: Account) -> Workspace:
    key = vault.unwrap(master(config), account.wrapped_key, account.uuid)
    db_path = (config.accounts_dir / f"{account.uuid}.db").resolve()
    ws = Workspace(account_id=account.id, uuid=account.uuid, name=account.name, db_path=db_path, key=key,
                   backup_dir=config.backup_dir / account.uuid)
    if db_path not in _ready_stores:
        with _lock:
            if db_path not in _ready_stores:
                if not db_path.exists() and is_plaintext(config.legacy_db_path):
                    _adopt_legacy(config, ws)
                upgrade_to_head(db_path, key)
                with ws.session() as s:
                    seed_default_indices(s)
                _ready_stores.add(db_path)
    return ws


def workspace_for(config: AppConfig, account_id: int) -> Workspace | None:
    with directory(config) as s:
        account = auth.get_account(s, account_id)
        return open_workspace(config, account) if account else None


# --------------------------------------------------------------------------
# Migration de la base non chiffrée des versions précédentes
# --------------------------------------------------------------------------

def _migrate_legacy_account(config: AppConfig, s: Session) -> None:
    """Ancienne base avec un compte : ce compte est recréé dans l'annuaire avec le même mot de passe."""
    legacy = config.legacy_db_path
    if not is_plaintext(legacy) or auth.accounts_exist(s):
        return
    connection = connect_raw(legacy, readonly=True)
    try:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        row = (connection.execute("SELECT username, password_hash FROM account ORDER BY id LIMIT 1").fetchone()
               if "account" in tables else None)
    finally:
        connection.close()
    if row is None:
        return  # données sans compte : le premier compte créé les reprendra
    account = create_account(config, s, name=row[0])
    account.username, account.password_hash = row[0], row[1]
    s.flush()
    open_workspace(config, account)
    log.info("Ancienne base migrée vers un compte chiffré.")


def _adopt_legacy(config: AppConfig, ws: Workspace) -> None:
    """Chiffre l'ancienne base dans le fichier du compte, vérifie, puis supprime la version en clair."""
    legacy = config.legacy_db_path
    ws.db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = ws.db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    source = connect_raw(legacy)
    try:
        source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        counts = _table_counts(source)
        source.execute(f"ATTACH DATABASE ? AS chiffree KEY \"x'{ws.key.hex()}'\"", (str(tmp),))
        source.execute("SELECT sqlcipher_export('chiffree')")
        source.execute("DETACH DATABASE chiffree")
    finally:
        source.close()
    check = connect_raw(tmp, ws.key)
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or _table_counts(check) != counts:
            raise vault.VaultError("Migration de l'ancienne base interrompue : copie chiffrée incomplète.")
    finally:
        check.close()
    tmp.replace(ws.db_path)
    for suffix in ("", "-wal", "-shm"):
        Path(f"{legacy}{suffix}").unlink(missing_ok=True)
    _adopt_legacy_backups(config, ws)
    log.info("Ancienne base chiffrée et supprimée en clair.")


def _table_counts(connection) -> dict[str, int]:
    tables = [r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: connection.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}


def _adopt_legacy_backups(config: AppConfig, ws: Workspace) -> None:
    """Les anciennes sauvegardes en clair sont chiffrées dans le dossier du compte."""
    old_dir = config.backup_dir
    manifest = old_dir / backup.MANIFEST
    if not manifest.exists():
        return
    ws.backup_dir.mkdir(parents=True, exist_ok=True)
    kept = []
    for entry in backup.list_backups(old_dir):
        plain = old_dir / entry.file
        if not is_plaintext(plain):
            continue
        target = ws.backup_dir / entry.file
        source = connect_raw(plain)
        try:
            source.execute(f"ATTACH DATABASE ? AS chiffree KEY \"x'{ws.key.hex()}'\"", (str(target),))
            source.execute("SELECT sqlcipher_export('chiffree')")
            source.execute("DETACH DATABASE chiffree")
        finally:
            source.close()
        entry.sha256 = backup._sha256(target)
        entry.size = target.stat().st_size
        kept.append(entry)
        plain.unlink()
    backup._write_manifest(ws.backup_dir, kept + backup._read_manifest(ws.backup_dir))
    manifest.unlink()
    log.info("%s ancienne(s) sauvegarde(s) chiffrée(s).", len(kept))


def list_accounts(config: AppConfig) -> list[tuple[int, str, str | None, str | None]]:
    with directory(config) as s:
        return [(a.id, a.name, a.username, a.email) for a in s.scalars(select(Account).order_by(Account.id))]

