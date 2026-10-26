"""Clés de chiffrement.

- Clé maître (256 bits) : variable ANCORA_MASTER_KEY, sinon trousseau du système (Trousseau macOS,
  Gestionnaire d'identification Windows), sinon fichier ``~/.ancora/cle-maitre`` lisible par vous seul.
  Elle n'est jamais écrite dans le dossier du projet, ni dans les sauvegardes.
- Annuaire des comptes : chiffré par une clé dérivée de la clé maître.
- Chaque compte : sa propre clé de données aléatoire, conservée dans l'annuaire enveloppée
  (AES-256-GCM) par une autre clé dérivée de la clé maître.
"""
from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

log = logging.getLogger(__name__)

KEY_BYTES = 32
_KEYRING_SERVICE, _KEYRING_USER = "Ancora", "cle-maitre"
_WRAP_VERSION = b"\x01"


class VaultError(RuntimeError):
    """Clé absente ou invalide : les données ne peuvent pas être déchiffrées."""


def new_key() -> bytes:
    return secrets.token_bytes(KEY_BYTES)


def _parse(text: str) -> bytes:
    raw = bytes.fromhex(text.strip().replace("-", "").replace(" ", ""))
    if len(raw) != KEY_BYTES:
        raise ValueError
    return raw


def format_recovery_key(key: bytes) -> str:
    """Clé de secours lisible : 16 groupes de 4 caractères hexadécimaux."""
    text = key.hex().upper()
    return "-".join(text[i:i + 4] for i in range(0, len(text), 4))


def _keyring():
    try:
        import keyring
        from keyring.backends import fail
    except ImportError:
        return None
    try:
        backend = keyring.get_keyring()
    except Exception:  # noqa: BLE001 - trousseau indisponible : repli sur le fichier
        return None
    return None if isinstance(backend, fail.Keyring) else keyring


@lru_cache(maxsize=4)
def master_key(key_file: Path) -> bytes:
    """Lit (ou crée au premier lancement) la clé maître."""
    env = os.environ.get("ANCORA_MASTER_KEY")
    if env:
        try:
            return _parse(env)
        except ValueError as exc:
            raise VaultError("ANCORA_MASTER_KEY doit contenir 64 caractères hexadécimaux.") from exc

    ring = _keyring() if os.environ.get("ANCORA_KEYRING", "1") != "0" else None
    if ring is not None:
        try:
            stored = ring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
            if stored:
                return _parse(stored)
        except Exception:  # noqa: BLE001
            log.warning("Trousseau du système illisible : utilisation du fichier de clé.")
            ring = None

    if key_file.exists():
        try:
            return _parse(key_file.read_text(encoding="ascii"))
        except ValueError as exc:
            raise VaultError(f"Fichier de clé invalide : {key_file}") from exc

    key = new_key()
    if ring is not None:
        try:
            ring.set_password(_KEYRING_SERVICE, _KEYRING_USER, key.hex())
            log.info("Clé maître créée dans le trousseau du système.")
            return key
        except Exception:  # noqa: BLE001
            log.warning("Écriture dans le trousseau impossible : utilisation du fichier de clé.")
    key_file.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(key_file.parent, 0o700)
    try:
        descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # l'autre interface vient de la créer
        return _parse(key_file.read_text(encoding="ascii"))
    with os.fdopen(descriptor, "w", encoding="ascii") as handle:
        handle.write(key.hex())
    log.info("Clé maître créée : %s", key_file)
    return key


def derive(master: bytes, purpose: str) -> bytes:
    """Clé distincte par usage (HKDF-SHA256) : l'annuaire et l'enveloppe n'utilisent pas la même clé."""
    return HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES, salt=None,
                info=f"ancora/{purpose}".encode()).derive(master)


def wrap(master: bytes, data_key: bytes, account_uuid: str) -> bytes:
    """Enveloppe la clé d'un compte ; l'identifiant du compte est lié au chiffré (données associées)."""
    nonce = secrets.token_bytes(12)
    sealed = AESGCM(derive(master, "enveloppe")).encrypt(nonce, data_key, account_uuid.encode())
    return _WRAP_VERSION + nonce + sealed


def unwrap(master: bytes, wrapped: bytes, account_uuid: str) -> bytes:
    if not wrapped or wrapped[:1] != _WRAP_VERSION:
        raise VaultError("Clé de compte illisible.")
    try:
        return AESGCM(derive(master, "enveloppe")).decrypt(wrapped[1:13], wrapped[13:], account_uuid.encode())
    except InvalidTag as exc:
        raise VaultError("Clé de compte invalide : la clé maître ne correspond pas.") from exc
