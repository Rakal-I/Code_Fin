"""Chiffrement : bases illisibles sans clé, une clé par compte, sauvegardes chiffrées, migration."""
import os
import sqlite3
import stat

import pytest
import sqlcipher3

from app.database.engine import connect_raw, dispose_engine, upgrade_to_head
from app.services import auth, backup, referential, vault, workspace
from app.services.workspace import is_plaintext
from tests.conftest import PASSWORD, USER, make_account
from tests.test_ui import populate


def test_bases_et_sauvegardes_illisibles_sans_cle(app_config):
    ws = make_account(app_config)
    populate(ws)
    entry = backup.create_backup(ws.db_path, ws.backup_dir, key=ws.key)
    for path in (ws.db_path, app_config.directory_path, ws.backup_dir / entry.file):
        content = path.read_bytes()
        assert not is_plaintext(path)
        assert b"LVMH" not in content and USER.encode() not in content
        with pytest.raises(sqlcipher3.DatabaseError):
            connect_raw(path, readonly=True).execute("SELECT count(*) FROM sqlite_master").fetchone()
    assert backup.verify_backup(ws.backup_dir, entry, ws.key)[0]


def test_une_cle_par_compte(app_config):
    alice = make_account(app_config)
    bob = make_account(app_config, username="bob", password="Bob2026xx")
    populate(alice)
    assert alice.key != bob.key
    with pytest.raises(sqlcipher3.DatabaseError):
        connect_raw(alice.db_path, bob.key, readonly=True).execute("SELECT count(*) FROM sqlite_master").fetchone()
    with bob.session() as s:
        assert [i.name for i in referential.list_instruments(s) if i.name == "LVMH"] == []


def test_cle_enveloppee_liee_au_compte():
    master, data_key = vault.new_key(), vault.new_key()
    wrapped = vault.wrap(master, data_key, "compte-a")
    assert data_key not in wrapped
    assert vault.unwrap(master, wrapped, "compte-a") == data_key
    with pytest.raises(vault.VaultError):
        vault.unwrap(master, wrapped, "compte-b")  # recopiée sur un autre compte : refusée
    with pytest.raises(vault.VaultError):
        vault.unwrap(vault.new_key(), wrapped, "compte-a")


def test_cle_maitre_creee_hors_du_projet(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCORA_MASTER_KEY")
    monkeypatch.setenv("ANCORA_KEYRING", "0")
    vault.master_key.cache_clear()
    key_file = tmp_path / "secret" / "cle-maitre"
    key = vault.master_key(key_file)
    assert len(key) == 32 and stat.S_IMODE(os.stat(key_file).st_mode) == 0o600
    vault.master_key.cache_clear()
    assert vault.master_key(key_file) == key  # relue à l'identique
    assert vault.format_recovery_key(key).count("-") == 15


def test_mauvaise_cle_maitre(app_config, monkeypatch):
    make_account(app_config)
    monkeypatch.setenv("ANCORA_MASTER_KEY", "00" * 32)
    vault.master_key.cache_clear()
    workspace._ready_directories.clear()
    dispose_engine(app_config.directory_path)
    with pytest.raises(vault.VaultError, match="clé maître"):
        with workspace.directory(app_config) as d:
            auth.accounts_exist(d)


def _legacy_database(app_config, with_account: bool):
    """Base unique non chiffrée d'une version précédente (avec ou sans compte), et une sauvegarde."""
    legacy = app_config.legacy_db_path
    upgrade_to_head(legacy)
    from app.database.engine import session_scope
    with session_scope(legacy) as s:
        referential.seed_default_indices(s)
    dispose_engine(legacy)
    connection = sqlite3.connect(legacy)
    connection.executescript("""
        CREATE TABLE account (id INTEGER PRIMARY KEY, username VARCHAR(60), password_hash VARCHAR(255),
            failed_attempts INTEGER, locked_until DATETIME, created_at DATETIME, password_changed_at DATETIME);
        CREATE TABLE auth_sessions (id INTEGER PRIMARY KEY, token_hash VARCHAR(64), account_id INTEGER,
            created_at DATETIME, last_seen_at DATETIME, expires_at DATETIME, device VARCHAR(120));
        UPDATE alembic_version SET version_num = '0002';
    """)
    if with_account:
        connection.execute("INSERT INTO account (username, password_hash, failed_attempts) VALUES (?, ?, 0)",
                           (USER, auth.hash_password(PASSWORD)))
    connection.commit()
    connection.close()
    entry = backup.create_backup(legacy, app_config.backup_dir)
    return legacy, entry


def test_migration_de_l_ancienne_base_avec_compte(app_config):
    legacy, entry = _legacy_database(app_config, with_account=True)
    with workspace.directory(app_config) as d:
        result = auth.authenticate(d, USER, PASSWORD)  # même mot de passe qu'avant
        assert result.ok
        account = auth.get_account(d, result.account_id)
        ws = workspace.open_workspace(app_config, account)
    assert not legacy.exists()  # la version en clair a disparu
    assert not is_plaintext(ws.db_path)
    with ws.session() as s:
        assert any(i.name == "CAC 40" for i in referential.list_instruments(s))
        tables = s.connection().exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").scalars()
        assert "account" not in set(tables)
    moved = backup.list_backups(ws.backup_dir)
    assert [e.file for e in moved] == [entry.file]
    assert not (app_config.backup_dir / entry.file).exists()
    assert backup.verify_backup(ws.backup_dir, moved[0], ws.key)[0]


def test_migration_sans_compte_reprise_par_le_premier_compte(app_config):
    legacy, _ = _legacy_database(app_config, with_account=False)
    ws = make_account(app_config)
    assert not legacy.exists()
    with ws.session() as s:
        assert any(i.name == "CAC 40" for i in referential.list_instruments(s))
