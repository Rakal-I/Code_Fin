"""Annuaire des comptes : sessions, clés d'accès (Face ID / Touch ID) et clés enveloppées.

Base distincte des données patrimoniales, chiffrée par la clé maître. Chaque compte a ses
données dans sa propre base, chiffrée par sa propre clé.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.models.entities import utcnow

SCHEMA_VERSION = 1


class DirectoryBase(DeclarativeBase):
    pass


class Account(DirectoryBase):
    """Un compte Ancora. Le mot de passe n'est jamais stocké en clair, seulement son empreinte."""

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

    passkeys: Mapped[list[Passkey]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Passkey(DirectoryBase):
    """Clé d'accès (WebAuthn) : Face ID, Touch ID, Windows Hello…

    La clé privée reste dans l'appareil (trousseau iCloud sur iPhone) ; Ancora ne garde que la clé
    publique, qui ne permet pas de se connecter à elle seule.
    """

    __tablename__ = "passkeys"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    rp_id: Mapped[str] = mapped_column(String(255))          # adresse du site pour laquelle elle a été créée
    name: Mapped[str] = mapped_column(String(120))           # « iPhone », « Mac »…
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)

    account: Mapped[Account] = relationship(back_populates="passkeys")


class WebAuthnChallenge(DirectoryBase):
    """Défi aléatoire d'une cérémonie Face ID en cours (usage unique, 5 minutes)."""

    __tablename__ = "webauthn_challenges"

    id_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    challenge: Mapped[bytes] = mapped_column(LargeBinary)
    purpose: Mapped[str] = mapped_column(String(12))        # « connexion » ou « ajout »
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    rp_id: Mapped[str] = mapped_column(String(255))
    origin: Mapped[str] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


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
    """Passage de relais après Face ID / Touch ID vers l'interface ordinateur (usage unique, 2 minutes)."""

    __tablename__ = "login_tickets"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class LinkIntent(DirectoryBase):
    """Ajout d'une clé d'accès demandé depuis l'interface ordinateur connectée (usage unique, 5 min)."""

    __tablename__ = "link_intents"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
