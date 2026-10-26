"""Comptes Ancora : mot de passe, Google / Apple, sessions.

- Mot de passe : jamais stocké ; empreinte scrypt avec sel aléatoire, comparaison à temps constant.
- Échecs : après 5 tentatives ratées, blocage de 1 minute, doublé à chaque nouvel échec (60 min au plus).
- Google / Apple : le compte est reconnu par l'identifiant stable du fournisseur, jamais par l'adresse e-mail.
- Jetons (sessions du téléphone, tickets, demandes de connexion) : la base n'en garde que l'empreinte SHA-256.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.directory import Account, AuthSession, Identity, LinkIntent, LoginTicket, OAuthRequest
from app.models.entities import utcnow
from app.services import vault

log = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 8
MAX_FAILURES = 5
MAX_LOCK_MINUTES = 60
SESSION_DAYS = 30
TICKET_MINUTES = 2
OAUTH_MINUTES = 10
LINK_MINUTES = 5

PROVIDERS = {"google": "Google", "apple": "Apple"}

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


def verify_password(password: str, stored: str | None) -> bool:
    try:
        scheme, n, r, p, salt, digest = (stored or "").split("$")
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


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Comptes
# --------------------------------------------------------------------------

def accounts_exist(session: Session) -> bool:
    return bool(session.scalar(select(func.count()).select_from(Account)))


def get_account(session: Session, account_id: int | None) -> Account | None:
    return session.get(Account, account_id) if account_id is not None else None


def find_by_username(session: Session, username: str) -> Account | None:
    wanted = username.strip().lower()
    if not wanted:
        return None
    return session.scalars(select(Account).where(func.lower(Account.username) == wanted)).first()


def _check_username(session: Session, username: str) -> str:
    username = username.strip()
    if len(username) < 2:
        raise AuthError("Choisissez un identifiant d'au moins 2 caractères.")
    if find_by_username(session, username) is not None:
        raise AuthError("Cet identifiant est déjà utilisé.")
    return username


def create_account(session: Session, master: bytes, *, name: str | None = None, username: str | None = None,
                   password: str | None = None, confirmation: str | None = None,
                   email: str | None = None) -> Account:
    """Crée un compte et sa clé de données (enveloppée par la clé maître)."""
    if username is not None:
        username = _check_username(session, username)
        if password != confirmation:
            raise AuthError("Les deux mots de passe ne correspondent pas.")
        _check_password_rules(password or "")
    account_uuid = uuid.uuid4().hex
    account = Account(uuid=account_uuid, name=(name or username or email or "Mon compte")[:120], email=email,
                      username=username, password_hash=hash_password(password) if username else None,
                      password_changed_at=utcnow() if username else None, failed_attempts=0,
                      wrapped_key=vault.wrap(master, vault.new_key(), account_uuid))
    session.add(account)
    session.flush()
    log.info("Compte créé (%s).", account_uuid[:8])
    return account


@dataclass(frozen=True)
class LoginResult:
    ok: bool
    message: str = ""
    account_id: int | None = None
    locked_until: datetime | None = None


def authenticate(session: Session, username: str, password: str, now: datetime | None = None) -> LoginResult:
    now = now or utcnow()
    account = find_by_username(session, username)
    if account is None or account.password_hash is None:
        verify_password(password, _DUMMY_HASH)
        return LoginResult(False, "Identifiant ou mot de passe incorrect.")
    if account.locked_until and account.locked_until > now:
        remaining = max(1, round((account.locked_until - now).total_seconds() / 60))
        return LoginResult(False, f"Trop de tentatives. Réessayez dans {remaining} min.",
                           locked_until=account.locked_until)

    if verify_password(password, account.password_hash):
        account.failed_attempts = 0
        account.locked_until = None
        account.last_login_at = now
        return LoginResult(True, account_id=account.id)

    account.failed_attempts += 1
    log.warning("Échec de connexion (%s tentative(s) consécutive(s)).", account.failed_attempts)
    if account.failed_attempts >= MAX_FAILURES:
        minutes = min(2 ** (account.failed_attempts - MAX_FAILURES), MAX_LOCK_MINUTES)
        account.locked_until = now + timedelta(minutes=minutes)
        return LoginResult(False, f"Trop de tentatives. Connexion bloquée {minutes} min.",
                           locked_until=account.locked_until)
    return LoginResult(False, "Identifiant ou mot de passe incorrect.")


def change_password(session: Session, account: Account, current: str, new: str, confirmation: str) -> None:
    if not verify_password(current, account.password_hash):
        raise AuthError("Mot de passe actuel incorrect.")
    if new == current:
        raise AuthError("Le nouveau mot de passe doit être différent de l'actuel.")
    _store_password(session, account, new, confirmation)


def set_password(session: Session, account: Account, username: str, new: str, confirmation: str) -> None:
    """Ajoute un identifiant et un mot de passe à un compte créé avec Google ou Apple."""
    if account.password_hash is not None:
        raise AuthError("Ce compte a déjà un mot de passe.")
    account.username = _check_username(session, username)
    _store_password(session, account, new, confirmation)


def reset_password(session: Session, account: Account, new: str, confirmation: str) -> None:
    """Mot de passe oublié (script local) : les données du compte sont conservées."""
    _store_password(session, account, new, confirmation)


def _store_password(session: Session, account: Account, new: str, confirmation: str) -> None:
    if new != confirmation:
        raise AuthError("Les deux nouveaux mots de passe ne correspondent pas.")
    _check_password_rules(new)
    account.password_hash = hash_password(new)
    account.password_changed_at = utcnow()
    account.failed_attempts = 0
    account.locked_until = None
    revoke_all_sessions(session, account.id)  # les téléphones devront se reconnecter
    log.info("Mot de passe modifié ; sessions révoquées.")


# --------------------------------------------------------------------------
# Identités Google / Apple
# --------------------------------------------------------------------------

def find_identity(session: Session, provider: str, subject: str) -> Identity | None:
    return session.scalars(select(Identity).where(Identity.provider == provider,
                                                  Identity.subject == subject)).first()


def link_identity(session: Session, account: Account, provider: str, subject: str, email: str | None) -> Identity:
    existing = find_identity(session, provider, subject)
    if existing is not None:
        if existing.account_id != account.id:
            raise AuthError(f"Ce compte {PROVIDERS[provider]} est déjà associé à un autre compte Ancora.")
        existing.email = email or existing.email
        return existing
    if any(i.provider == provider for i in account.identities):
        raise AuthError(f"Un compte {PROVIDERS[provider]} est déjà associé : dissociez-le d'abord.")
    identity = Identity(account=account, provider=provider, subject=subject, email=email)
    session.add(identity)
    if not account.email and email:
        account.email = email
    session.flush()
    log.info("Identité %s associée au compte %s.", provider, account.uuid[:8])
    return identity


def unlink_identity(session: Session, account: Account, provider: str) -> None:
    identity = next((i for i in account.identities if i.provider == provider), None)
    if identity is None:
        return
    if account.password_hash is None and len(account.identities) == 1:
        raise AuthError("C'est votre seul moyen de connexion : définissez d'abord un mot de passe.")
    account.identities.remove(identity)
    session.flush()


# --------------------------------------------------------------------------
# Sessions (téléphone)
# --------------------------------------------------------------------------

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


def revoke_all_sessions(session: Session, account_id: int) -> None:
    session.execute(delete(AuthSession).where(AuthSession.account_id == account_id))


def active_sessions(session: Session, account_id: int, now: datetime | None = None) -> list[AuthSession]:
    now = now or utcnow()
    return list(session.scalars(select(AuthSession).where(AuthSession.account_id == account_id,
                                                          AuthSession.expires_at >= now)
                                .order_by(AuthSession.last_seen_at.desc())))


# --------------------------------------------------------------------------
# Connexion Google / Apple : demandes, tickets, associations
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PendingOAuth:
    state: str
    nonce: str
    verifier: str


def start_oauth(session: Session, provider: str, client: str, redirect_uri: str,
                link_account_id: int | None = None) -> PendingOAuth:
    now = utcnow()
    session.execute(delete(OAuthRequest).where(OAuthRequest.created_at < now - timedelta(minutes=OAUTH_MINUTES)))
    pending = PendingOAuth(secrets.token_urlsafe(32), secrets.token_urlsafe(24), secrets.token_urlsafe(48))
    session.add(OAuthRequest(state_hash=_token_hash(pending.state), provider=provider, client=client,
                             nonce=pending.nonce, verifier=pending.verifier, redirect_uri=redirect_uri,
                             link_account_id=link_account_id, created_at=now))
    return pending


def consume_oauth(session: Session, state: str | None) -> OAuthRequest | None:
    """Demande correspondant au « state » reçu ; supprimée aussitôt (usage unique)."""
    if not state:
        return None
    record = session.get(OAuthRequest, _token_hash(state))
    if record is None:
        return None
    session.delete(record)
    session.flush()
    if record.created_at < utcnow() - timedelta(minutes=OAUTH_MINUTES):
        return None
    return record


def issue_ticket(session: Session, *, account_id: int | None = None, provider: str | None = None,
                 subject: str | None = None, email: str | None = None, name: str | None = None) -> str:
    now = utcnow()
    session.execute(delete(LoginTicket).where(LoginTicket.expires_at < now))
    token = secrets.token_urlsafe(32)
    session.add(LoginTicket(token_hash=_token_hash(token), account_id=account_id, provider=provider,
                            subject=subject, email=email, name=(name or "")[:120] or None,
                            expires_at=now + timedelta(minutes=TICKET_MINUTES)))
    return token


def redeem_ticket(session: Session, token: str | None) -> LoginTicket | None:
    if not token:
        return None
    ticket = session.get(LoginTicket, _token_hash(token))
    if ticket is None:
        return None
    session.delete(ticket)
    session.flush()
    return ticket if ticket.expires_at >= utcnow() else None


def create_link_intent(session: Session, account_id: int) -> str:
    token = secrets.token_urlsafe(24)
    session.add(LinkIntent(token_hash=_token_hash(token), account_id=account_id,
                           expires_at=utcnow() + timedelta(minutes=LINK_MINUTES)))
    return token


def consume_link_intent(session: Session, token: str | None) -> int | None:
    if not token:
        return None
    intent = session.get(LinkIntent, _token_hash(token))
    if intent is None:
        return None
    session.delete(intent)
    session.flush()
    return intent.account_id if intent.expires_at >= utcnow() else None
