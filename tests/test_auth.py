"""Comptes : empreintes, blocage après échecs, identités Google / Apple, sessions, jetons à usage unique."""
from datetime import timedelta

import pytest

from app.models.directory import Account, AuthSession, LoginTicket, OAuthRequest
from app.models.entities import utcnow
from app.services import auth, workspace
from tests.conftest import PASSWORD, USER


def make(app_config, d, username=USER, password=PASSWORD, **fields):
    account = workspace.create_account(app_config, d, username=username, password=password, confirmation=password,
                                       **fields)
    d.commit()
    return account


def test_mot_de_passe_jamais_stocke_en_clair(app_config, directory):
    account = make(app_config, directory)
    assert PASSWORD not in account.password_hash and account.password_hash.startswith("scrypt$")
    assert auth.verify_password(PASSWORD, account.password_hash)
    assert not auth.verify_password(PASSWORD.lower(), account.password_hash)


@pytest.mark.parametrize("password,confirmation,message", [
    ("court1", "court1", "au moins"),
    ("seulementdeslettres", "seulementdeslettres", "Mélangez"),
    ("Patrimoine2026", "Patrimoine2027", "ne correspondent pas"),
])
def test_regles_du_mot_de_passe(app_config, directory, password, confirmation, message):
    with pytest.raises(auth.AuthError, match=message):
        workspace.create_account(app_config, directory, username=USER, password=password, confirmation=confirmation)


def test_plusieurs_comptes_identifiants_uniques(app_config, directory):
    first = make(app_config, directory)
    second = make(app_config, directory, username="conjoint", password="Autre2026x")
    assert first.uuid != second.uuid and first.wrapped_key != second.wrapped_key
    with pytest.raises(auth.AuthError, match="déjà utilisé"):
        make(app_config, directory, username="PROPRIETAIRE")


def test_connexion(app_config, directory):
    account = make(app_config, directory)
    assert auth.authenticate(directory, " Proprietaire ", PASSWORD).account_id == account.id
    unknown = auth.authenticate(directory, "inconnu", PASSWORD)
    wrong = auth.authenticate(directory, USER, "mauvais")
    assert not unknown.ok and not wrong.ok
    assert unknown.message == wrong.message  # aucun indice sur l'existence d'un identifiant


def test_blocage_apres_cinq_echecs(app_config, directory):
    make(app_config, directory)
    now = utcnow()
    for _ in range(auth.MAX_FAILURES):
        result = auth.authenticate(directory, USER, "mauvais", now=now)
    assert result.locked_until == now + timedelta(minutes=1)
    assert "Réessayez" in auth.authenticate(directory, USER, PASSWORD, now=now).message
    later = now + timedelta(minutes=2)
    assert auth.authenticate(directory, USER, PASSWORD, now=later).ok
    assert directory.query(Account).one().failed_attempts == 0


def test_sessions_par_compte(app_config, directory):
    alice = make(app_config, directory)
    bob = make(app_config, directory, username="bob", password="Bob2026xx")
    token_a = auth.create_session(directory, alice.id, "iPhone")
    token_b = auth.create_session(directory, bob.id, "iPhone")
    assert auth.resolve_session(directory, token_a).id == alice.id
    assert auth.resolve_session(directory, "inconnu") is None
    assert token_a not in {s.token_hash for s in directory.query(AuthSession)}  # seule l'empreinte est stockée
    auth.change_password(directory, alice, PASSWORD, "Nouveau2026", "Nouveau2026")
    assert auth.resolve_session(directory, token_a) is None  # les téléphones d'Alice sont déconnectés
    assert auth.resolve_session(directory, token_b).id == bob.id  # pas ceux de Bob
    expired = auth.create_session(directory, bob.id, now=utcnow() - timedelta(days=auth.SESSION_DAYS + 1))
    assert auth.resolve_session(directory, expired) is None


def test_compte_google_puis_mot_de_passe(app_config, directory):
    account = workspace.create_account(app_config, directory, name="Camille", email="camille@exemple.fr")
    auth.link_identity(directory, account, "google", "sub-123", "camille@exemple.fr")
    assert auth.find_identity(directory, "google", "sub-123").account_id == account.id
    assert auth.find_identity(directory, "apple", "sub-123") is None
    assert not auth.authenticate(directory, "camille", PASSWORD).ok
    with pytest.raises(auth.AuthError, match="seul moyen"):
        auth.unlink_identity(directory, account, "google")
    auth.set_password(directory, account, "camille", PASSWORD, PASSWORD)
    assert auth.authenticate(directory, "camille", PASSWORD).ok
    auth.unlink_identity(directory, account, "google")
    assert auth.find_identity(directory, "google", "sub-123") is None


def test_identite_deja_associee_ailleurs(app_config, directory):
    alice = make(app_config, directory)
    bob = make(app_config, directory, username="bob", password="Bob2026xx")
    auth.link_identity(directory, alice, "apple", "apple-1", None)
    with pytest.raises(auth.AuthError, match="autre compte"):
        auth.link_identity(directory, bob, "apple", "apple-1", None)
    with pytest.raises(auth.AuthError, match="déjà associé"):
        auth.link_identity(directory, alice, "apple", "apple-2", None)


def test_tickets_et_demandes_a_usage_unique(app_config, directory):
    account = make(app_config, directory)
    ticket = auth.issue_ticket(directory, account_id=account.id)
    assert auth.redeem_ticket(directory, ticket).account_id == account.id
    assert auth.redeem_ticket(directory, ticket) is None
    old = auth.issue_ticket(directory, account_id=account.id)
    directory.query(LoginTicket).update({LoginTicket.expires_at: utcnow() - timedelta(seconds=1)})
    assert auth.redeem_ticket(directory, old) is None

    pending = auth.start_oauth(directory, "google", "mobile", "https://exemple.fr/connexion/google/retour")
    record = auth.consume_oauth(directory, pending.state)
    assert record.nonce == pending.nonce and record.verifier == pending.verifier
    assert auth.consume_oauth(directory, pending.state) is None  # rejeu refusé
    stale = auth.start_oauth(directory, "apple", "mobile", "https://exemple.fr/connexion/apple/retour")
    directory.query(OAuthRequest).update({OAuthRequest.created_at: utcnow() - timedelta(minutes=11)})
    assert auth.consume_oauth(directory, stale.state) is None

    intent = auth.create_link_intent(directory, account.id)
    assert auth.consume_link_intent(directory, intent) == account.id
    assert auth.consume_link_intent(directory, intent) is None


def test_mot_de_passe_oublie(app_config, directory):
    account = make(app_config, directory)
    token = auth.create_session(directory, account.id)
    auth.reset_password(directory, account, "Retrouve2026", "Retrouve2026")
    assert auth.authenticate(directory, USER, "Retrouve2026").ok
    assert auth.resolve_session(directory, token) is None
