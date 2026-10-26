"""Connexion au compte unique d'Ancora.

- Mot de passe : jamais stocké ; empreinte scrypt avec sel aléatoire, comparaison à temps constant.
- Échecs : après 5 tentatives ratées, blocage de 1 minute, doublé à chaque nouvel échec (60 min au plus).
- Sessions du téléphone : jeton aléatoire remis au navigateur ; la base n'en garde que l'empreinte SHA-256.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.entities import Account, AuthSession, utcnow

log = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 8
MAX_FAILURES = 5
MAX_LOCK_MINUTES = 60
SESSION_DAYS = 30

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


class AuthError(ValueError):
    """Erreur affichable telle quelle."""


# --------------------------------------------------------------------------
# Empreintes
# --------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    encode = lambda raw: base64.b64encode(raw).decode("ascii")  # noqa: E731
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${encode(salt)}${encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), dklen=len(expected),
                                n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Empreinte factice : un identifiant inconnu coûte le même temps de calcul qu'un bon.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def _check_password_rules(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères.")
    if password.isdigit() or password.isalpha():
        raise AuthError("Mélangez lettres et chiffres (ou symboles) dans le mot de passe.")


# --------------------------------------------------------------------------
# Compte
# --------------------------------------------------------------------------

def get_account(session: Session) -> Account | None:
    return session.scalars(select(Account).order_by(Account.id)).first()


def account_exists(session: Session) -> bool:
    return bool(session.scalar(select(func.count()).select_from(Account)))


def create_account(session: Session, username: str, password: str, confirmation: str) -> Account:
    """Crée le compte unique (premier lancement uniquement)."""
    if account_exists(session):
        raise AuthError("Un compte existe déjà.")
    username = username.strip()
    if len(username) < 2:
        raise AuthError("Choisissez un identifiant d'au moins 2 caractères.")
    if password != confirmation:
        raise AuthError("Les deux mots de passe ne correspondent pas.")
    _check_password_rules(password)
    account = Account(username=username, password_hash=hash_password(password))
    session.add(account)
    session.flush()
    log.info("Compte créé.")
    return account


@dataclass(frozen=True)
class LoginResult:
    ok: bool
    message: str = ""
    account_id: int | None = None
    locked_until: datetime | None = None


def authenticate(session: Session, username: str, password: str, now: datetime | None = None) -> LoginResult:
    now = now or utcnow()
    account = get_account(session)
    if account is None:
        verify_password(password, _DUMMY_HASH)
        return LoginResult(False, "Aucun compte n'est configuré.")
    if account.locked_until and account.locked_until > now:
        remaining = max(1, round((account.locked_until - now).total_seconds() / 60))
        return LoginResult(False, f"Trop de tentatives. Réessayez dans {remaining} min.",
                           locked_until=account.locked_until)

    username_ok = hmac.compare_digest(username.strip().casefold().encode(), account.username.casefold().encode())
    password_ok = verify_password(password, account.password_hash)
    if username_ok and password_ok:
        account.failed_attempts = 0
        account.locked_until = None
        return LoginResult(True, account_id=account.id)

    account.failed_attempts += 1
    log.warning("Échec de connexion (%s tentative(s) consécutive(s)).", account.failed_attempts)
    if account.failed_attempts >= MAX_FAILURES:
        minutes = min(2 ** (account.failed_attempts - MAX_FAILURES), MAX_LOCK_MINUTES)
        account.locked_until = now + timedelta(minutes=minutes)
        return LoginResult(False, f"Trop de tentatives. Connexion bloquée {minutes} min.",
                           locked_until=account.locked_until)
    left = MAX_FAILURES - account.failed_attempts
    return LoginResult(False, f"Identifiant ou mot de passe incorrect ({left} essai{'s' if left > 1 else ''} "
                              "avant blocage temporaire).")


def change_password(session: Session, current: str, new: str, confirmation: str) -> None:
    account = get_account(session)
    if account is None or not verify_password(current, account.password_hash):
        raise AuthError("Mot de passe actuel incorrect.")
    if new != confirmation:
        raise AuthError("Les deux nouveaux mots de passe ne correspondent pas.")
    if new == current:
        raise AuthError("Le nouveau mot de passe doit être différent de l'actuel.")
    _check_password_rules(new)
    account.password_hash = hash_password(new)
    account.password_changed_at = utcnow()
    revoke_all_sessions(session)  # les téléphones devront se reconnecter
    log.info("Mot de passe modifié ; sessions révoquées.")


def reset_account(session: Session) -> None:
    """Supprime le compte et ses sessions (mot de passe oublié). Les données patrimoniales sont conservées."""
    session.execute(delete(AuthSession))
    session.execute(delete(Account))
    log.warning("Compte réinitialisé.")


# --------------------------------------------------------------------------
# Sessions (téléphone)
# --------------------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(session: Session, account_id: int, device: str | None = None, now: datetime | None = None) -> str:
    now = now or utcnow()
    token = secrets.token_urlsafe(32)
    session.add(AuthSession(token_hash=_token_hash(token), account_id=account_id, created_at=now, last_seen_at=now,
                            expires_at=now + timedelta(days=SESSION_DAYS), device=(device or "")[:120] or None))
    session.execute(delete(AuthSession).where(AuthSession.expires_at < now))
    return token


def resolve_session(session: Session, token: str | None, now: datetime | None = None) -> Account | None:
    """Compte associé à un jeton valide ; prolonge la session (30 jours glissants)."""
    if not token:
        return None
    now = now or utcnow()
    record = session.scalars(select(AuthSession).where(AuthSession.token_hash == _token_hash(token))).first()
    if record is None or record.expires_at < now:
        return None
    if (now - record.last_seen_at) > timedelta(hours=1):
        record.last_seen_at = now
        record.expires_at = now + timedelta(days=SESSION_DAYS)
    return session.get(Account, record.account_id)


def revoke_session(session: Session, token: str | None) -> None:
    if token:
        session.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))


def revoke_all_sessions(session: Session) -> None:
    session.execute(delete(AuthSession))


def active_sessions(session: Session, now: datetime | None = None) -> list[AuthSession]:
    now = now or utcnow()
    return list(session.scalars(select(AuthSession).where(AuthSession.expires_at >= now)
                                .order_by(AuthSession.last_seen_at.desc())))
