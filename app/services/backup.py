"""Sauvegarde, restauration et vérification d'intégrité (cahier des charges §17).

Une sauvegarde est chiffrée avec la même clé que la base du compte : sans la clé maître,
le fichier est illisible.

L'historique des sauvegardes est tenu dans ``manifest.json``, à côté des fichiers,
pour survivre à une restauration de la base.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import sqlcipher3

from app.database.engine import connect_raw, dispose_engine

log = logging.getLogger(__name__)

MANIFEST = "manifest.json"


class BackupError(RuntimeError):
    pass


@dataclass
class BackupEntry:
    file: str
    created_at: str
    sha256: str
    size: int
    kind: str          # « manuelle » ou « avant restauration »
    comment: str = ""
    restored_at: str = ""

    @property
    def created(self) -> datetime:
        return datetime.fromisoformat(self.created_at)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_manifest(backup_dir: Path) -> list[BackupEntry]:
    path = backup_dir / MANIFEST
    if not path.exists():
        return []
    return [BackupEntry(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


def _write_manifest(backup_dir: Path, entries: list[BackupEntry]) -> None:
    path = backup_dir / MANIFEST
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(e) for e in entries], ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def list_backups(backup_dir: Path) -> list[BackupEntry]:
    return sorted(_read_manifest(backup_dir), key=lambda e: e.created_at, reverse=True)


def create_backup(db_path: Path, backup_dir: Path, kind: str = "manuelle", comment: str = "",
                  key: bytes | None = None) -> BackupEntry:
    """Copie cohérente de la base via l'API de sauvegarde SQLite (fonctionne base ouverte)."""
    if not db_path.exists():
        raise BackupError("Aucune base à sauvegarder.")
    backup_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().replace(microsecond=0)
    target = backup_dir / f"ancora-{now:%Y%m%d-%H%M%S}.db"
    suffix = 1
    while target.exists():
        target = backup_dir / f"ancora-{now:%Y%m%d-%H%M%S}-{suffix}.db"
        suffix += 1
    source = connect_raw(db_path, key)
    destination = connect_raw(target, key)
    try:
        source.backup(destination)
        # Fichier autonome : pas de journal WAL à côté de la sauvegarde.
        destination.execute("PRAGMA journal_mode=DELETE")
    finally:
        destination.close()
        source.close()
    entry = BackupEntry(file=target.name, created_at=now.isoformat(), sha256=_sha256(target),
                        size=target.stat().st_size, kind=kind, comment=comment)
    ok, message = _check_database(target, key)
    if not ok:
        target.unlink(missing_ok=True)
        raise BackupError(f"Sauvegarde invalide : {message}")
    entries = _read_manifest(backup_dir)
    entries.append(entry)
    _write_manifest(backup_dir, entries)
    log.info("Sauvegarde créée : %s", target.name)
    return entry


def _check_database(path: Path, key: bytes | None = None) -> tuple[bool, str]:
    try:
        connection = connect_raw(path, key, readonly=True)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()
    except sqlcipher3.DatabaseError as exc:
        return False, f"fichier illisible ({exc})"
    if result != "ok":
        return False, f"contrôle SQLite en échec ({result})"
    missing = {"alembic_version", "instruments", "positions", "operations"} - tables
    if missing:
        return False, "structure Ancora absente"
    return True, "intégrité vérifiée"


def verify_backup(backup_dir: Path, entry: BackupEntry, key: bytes | None = None) -> tuple[bool, str]:
    """Empreinte SHA-256 identique à celle de la création + contrôle d'intégrité SQLite."""
    path = backup_dir / entry.file
    if not path.exists():
        return False, "Fichier de sauvegarde introuvable."
    if _sha256(path) != entry.sha256:
        return False, "Empreinte différente : le fichier a été modifié ou corrompu."
    ok, message = _check_database(path, key)
    return ok, message.capitalize() + "."


def restore_backup(db_path: Path, backup_dir: Path, entry: BackupEntry, key: bytes | None = None) -> BackupEntry:
    """Restaure après vérification ; la base actuelle est d'abord sauvegardée."""
    ok, message = verify_backup(backup_dir, entry, key)
    if not ok:
        raise BackupError(f"Restauration annulée : {message}")
    safety = create_backup(db_path, backup_dir, kind="avant restauration",
                           comment=f"Base remplacée par {entry.file}", key=key) if db_path.exists() else None
    dispose_engine(db_path)
    source = connect_raw(backup_dir / entry.file, key, readonly=True)
    destination = connect_raw(db_path, key)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    entries = _read_manifest(backup_dir)
    for e in entries:
        if e.file == entry.file:
            e.restored_at = datetime.now().replace(microsecond=0).isoformat()
    _write_manifest(backup_dir, entries)
    log.info("Base restaurée depuis %s", entry.file)
    return safety
