"""Annuaire des comptes : identités, sessions et clés enveloppées.

Base distincte des données patrimoniales, chiffrée par la clé maître. Chaque compte a ses
données dans sa propre base, chiffrée par sa propre clé.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.models.entities import utcnow

SCHEMA_VERSION = 1


class DirectoryBase(DeclarativeBase):
    pass


class Account(DirectoryBase):
    """Un compte Ancora. Mot de passe facultatif (connexion Google / Apple), jamais stocké en clair."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    uuid: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254))
    username: Mapped[str | None] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    identities: Mapped[list[Identity]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Identity(DirectoryBase):
    """Compte Google ou Apple associé : identifié par l'identifiant stable du fournisseur (« sub »)."""

    __tablename__ = "identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    account: Mapped[Account] = relationship(back_populates="identities")


class AuthSession(DirectoryBase):
    """Session de l'application téléphone. Seule l'empreinte du jeton est conservée."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    device: Mapped[str | None] = mapped_column(String(120))


class LoginTicket(DirectoryBase):
    """Passage de relais après Google / Apple vers l'interface ordinateur (usage unique, 2 minutes).

    Sans compte associé, le ticket porte l'identité en attente : l'utilisateur choisit alors de
    créer un compte ou de l'associer à son compte existant.
    """

    __tablename__ = "login_tickets"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    provider: Mapped[str | None] = mapped_column(String(20))
    subject: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(254))
    name: Mapped[str | None] = mapped_column(String(120))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class OAuthRequest(DirectoryBase):
    """Demande de connexion en cours (anti-rejeu : state, nonce, vérificateur PKCE). Usage unique, 10 min."""

    __tablename__ = "oauth_requests"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))
    client: Mapped[str] = mapped_column(String(10))          # « desktop » ou « mobile »
    nonce: Mapped[str] = mapped_column(String(64))
    verifier: Mapped[str] = mapped_column(String(128))
    redirect_uri: Mapped[str] = mapped_column(String(500))
    link_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LinkIntent(DirectoryBase):
    """Association d'un compte Google / Apple demandée depuis les Paramètres (usage unique, 5 min)."""

    __tablename__ = "link_intents"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
