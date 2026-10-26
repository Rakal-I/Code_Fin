"""Connexion par Face ID, Touch ID ou Windows Hello : clés d'accès (WebAuthn, « passkeys »).

L'appareil crée une paire de clés pour Ancora ; la clé privée ne quitte jamais l'appareil (sur
iPhone, elle est synchronisée par le trousseau iCloud) et Face ID la déverrouille. Ancora garde
la clé publique et vérifie, à chaque connexion, la signature d'un défi aléatoire à usage unique.
Une clé d'accès est liée à l'adresse du site : celle de l'ordinateur et celle du téléphone
sont distinctes lorsque les deux interfaces ont des adresses différentes.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.models.directory import Account, Passkey, WebAuthnChallenge
from app.models.entities import utcnow
from app.services.auth import _token_hash

log = logging.getLogger(__name__)

CHALLENGE_MINUTES = 5
RP_NAME = "Ancora"


class PasskeyError(ValueError):
    """Erreur affichable telle quelle."""


def _store_challenge(session: Session, challenge: bytes, purpose: str, rp_id: str, origin: str,
                     account_id: int | None = None) -> str:
    now = utcnow()
    session.execute(delete(WebAuthnChallenge).where(WebAuthnChallenge.expires_at < now))
    token = secrets.token_urlsafe(24)
    session.add(WebAuthnChallenge(id_hash=_token_hash(token), challenge=challenge, purpose=purpose,
                                  account_id=account_id, rp_id=rp_id, origin=origin,
                                  expires_at=now + timedelta(minutes=CHALLENGE_MINUTES)))
    return token


def _consume_challenge(session: Session, token: str | None, purpose: str) -> WebAuthnChallenge:
    record = session.get(WebAuthnChallenge, _token_hash(token or ""))
    if record is None or record.purpose != purpose:
        raise PasskeyError("Demande expirée : réessayez.")
    session.delete(record)
    session.flush()
    if record.expires_at < utcnow():
        raise PasskeyError("Demande expirée : réessayez.")
    return record


# --------------------------------------------------------------------------
# Ajout d'une clé d'accès (compte déjà connecté)
# --------------------------------------------------------------------------

def registration_options(session: Session, account: Account, rp_id: str, origin: str) -> dict:
    existing = [PublicKeyCredentialDescriptor(id=p.credential_id) for p in account.passkeys if p.rp_id == rp_id]
    options = generate_registration_options(
        rp_id=rp_id, rp_name=RP_NAME, user_id=account.uuid.encode(),
        user_name=account.username or account.name, user_display_name=account.name,
        exclude_credentials=existing,  # pas deux clés pour le même appareil
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,          # connexion sans saisir l'identifiant
            user_verification=UserVerificationRequirement.REQUIRED),  # Face ID / code exigé
    )
    token = _store_challenge(session, options.challenge, "ajout", rp_id, origin, account.id)
    return {"challenge": token, "options": json.loads(options_to_json(options))}


def finish_registration(session: Session, challenge: str, credential: dict, name: str) -> Passkey:
    record = _consume_challenge(session, challenge, "ajout")
    try:
        verified = verify_registration_response(credential=credential, expected_challenge=record.challenge,
                                                expected_rp_id=record.rp_id, expected_origin=record.origin,
                                                require_user_verification=True)
    except (WebAuthnException, ValueError, KeyError, TypeError) as exc:
        log.warning("Clé d'accès refusée à l'ajout : %s", type(exc).__name__)
        raise PasskeyError("Cette clé d'accès n'a pas pu être vérifiée.") from exc
    if session.scalars(select(Passkey).where(Passkey.credential_id == verified.credential_id)).first():
        raise PasskeyError("Cette clé d'accès est déjà enregistrée.")
    passkey = Passkey(account_id=record.account_id, credential_id=verified.credential_id,
                      public_key=verified.credential_public_key, sign_count=verified.sign_count,
                      rp_id=record.rp_id, name=(name or "Appareil")[:120])
    session.add(passkey)
    session.flush()
    log.info("Clé d'accès ajoutée (%s).", passkey.name)
    return passkey


# --------------------------------------------------------------------------
# Connexion
# --------------------------------------------------------------------------

def authentication_options(session: Session, rp_id: str, origin: str) -> dict:
    options = generate_authentication_options(rp_id=rp_id,
                                              user_verification=UserVerificationRequirement.REQUIRED)
    token = _store_challenge(session, options.challenge, "connexion", rp_id, origin)
    return {"challenge": token, "options": json.loads(options_to_json(options))}


def finish_authentication(session: Session, challenge: str, credential: dict) -> Account:
    record = _consume_challenge(session, challenge, "connexion")
    try:
        credential_id = base64url_to_bytes(credential["rawId"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PasskeyError("Réponse de l'appareil illisible.") from exc
    passkey = session.scalars(select(Passkey).where(Passkey.credential_id == credential_id,
                                                    Passkey.rp_id == record.rp_id)).first()
    if passkey is None:
        raise PasskeyError("Cette clé d'accès n'est plus enregistrée : connectez-vous avec votre mot de passe.")
    try:
        verified = verify_authentication_response(
            credential=credential, expected_challenge=record.challenge, expected_rp_id=record.rp_id,
            expected_origin=record.origin, credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count, require_user_verification=True)
    except (WebAuthnException, ValueError, KeyError, TypeError) as exc:
        log.warning("Connexion par clé d'accès refusée : %s", type(exc).__name__)
        raise PasskeyError("Connexion refusée : la clé d'accès n'a pas pu être vérifiée.") from exc
    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = utcnow()
    passkey.account.last_login_at = utcnow()
    return passkey.account


def list_passkeys(session: Session, account_id: int) -> list[Passkey]:
    return list(session.scalars(select(Passkey).where(Passkey.account_id == account_id)
                                .order_by(Passkey.created_at)))


def delete_passkey(session: Session, account_id: int, passkey_id: int) -> None:
    session.execute(delete(Passkey).where(Passkey.id == passkey_id, Passkey.account_id == account_id))
