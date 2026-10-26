"""Connexion : empreintes, blocage après échecs, sessions."""
from datetime import timedelta

import pytest

from app.models.entities import Account, AuthSession, utcnow
from app.services import auth


def make(session, username="proprietaire", password="Patrimoine2026"):
    auth.create_account(session, username, password, password)
    session.commit()


def test_mot_de_passe_jamais_stocke_en_clair(session):
    make(session)
    stored = session.query(Account).one().password_hash
    assert "Patrimoine2026" not in stored and stored.startswith("scrypt$")
    assert auth.verify_password("Patrimoine2026", stored)
    assert not auth.verify_password("patrimoine2026", stored)


@pytest.mark.parametrize("password,confirmation,message", [
    ("court1", "court1", "au moins"),
    ("seulementdeslettres", "seulementdeslettres", "Mélangez"),
    ("Patrimoine2026", "Patrimoine2027", "ne correspondent pas"),
])
def test_regles_du_mot_de_passe(session, password, confirmation, message):
    with pytest.raises(auth.AuthError, match=message):
        auth.create_account(session, "proprietaire", password, confirmation)


def test_un_seul_compte(session):
    make(session)
    with pytest.raises(auth.AuthError, match="existe déjà"):
        auth.create_account(session, "autre", "Autre2026x", "Autre2026x")


def test_connexion(session):
    make(session)
    assert auth.authenticate(session, "Proprietaire ", "Patrimoine2026").ok  # identifiant insensible à la casse
    result = auth.authenticate(session, "proprietaire", "mauvais")
    assert not result.ok and "incorrect" in result.message


def test_blocage_apres_cinq_echecs(session):
    make(session)
    now = utcnow()
    for _ in range(auth.MAX_FAILURES):
        result = auth.authenticate(session, "proprietaire", "mauvais", now)
    assert result.locked_until is not None
    # Même le bon mot de passe est refusé pendant le blocage.
    assert not auth.authenticate(session, "proprietaire", "Patrimoine2026", now + timedelta(seconds=30)).ok
    assert auth.authenticate(session, "proprietaire", "Patrimoine2026", now + timedelta(minutes=2)).ok
    assert session.query(Account).one().failed_attempts == 0


def test_sessions(session):
    make(session)
    account_id = auth.authenticate(session, "proprietaire", "Patrimoine2026").account_id
    token = auth.create_session(session, account_id, "iPhone")
    session.commit()
    assert auth.resolve_session(session, token).username == "proprietaire"
    assert auth.resolve_session(session, "jeton-inventé") is None
    assert token not in {s.token_hash for s in session.query(AuthSession)}  # seule l'empreinte est gardée
    assert auth.resolve_session(session, token, utcnow() + timedelta(days=auth.SESSION_DAYS + 1)) is None
    auth.revoke_session(session, token)
    assert auth.resolve_session(session, token) is None


def test_changer_de_mot_de_passe_deconnecte_les_telephones(session):
    make(session)
    token = auth.create_session(session, auth.get_account(session).id)
    with pytest.raises(auth.AuthError):
        auth.change_password(session, "mauvais", "Nouveau2026x", "Nouveau2026x")
    auth.change_password(session, "Patrimoine2026", "Nouveau2026x", "Nouveau2026x")
    assert auth.resolve_session(session, token) is None
    assert auth.authenticate(session, "proprietaire", "Nouveau2026x").ok


def test_reinitialisation(session):
    make(session)
    auth.reset_account(session)
    assert not auth.account_exists(session)
