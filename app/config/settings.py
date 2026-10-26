"""Configuration de l'application.

Les chemins et paramètres techniques viennent des variables d'environnement.
Les clés API et identifiants Google / Apple viennent de l'environnement ou de
``config/secrets.toml``, qui n'est jamais versionné (cahier des charges §18).
"""
from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
SECRETS_FILE = ROOT / "config" / "secrets.toml"

CONSOLIDATION_CURRENCY = "EUR"


class GoogleConfig(BaseModel):
    client_id: str
    client_secret: str


class AppleConfig(BaseModel):
    client_id: str          # identifiant de service (Services ID), ex. « fr.exemple.ancora.web »
    team_id: str
    key_id: str
    private_key: str        # contenu du fichier .p8 « Sign in with Apple »


class AppConfig(BaseModel):
    data_dir: Path = Field(default=ROOT / "data")
    backup_dir: Path = Field(default=ROOT / "backups")
    log_dir: Path = Field(default=ROOT / "logs")
    # Clé maître : trousseau du système si disponible, sinon ce fichier (hors du dossier du projet).
    key_file: Path = Field(default=Path.home() / ".ancora" / "cle-maitre")
    request_timeout: float = 15.0
    finnhub_api_key: str | None = None
    sec_user_agent: str | None = None
    google: GoogleConfig | None = None
    apple: AppleConfig | None = None

    @property
    def directory_path(self) -> Path:
        """Annuaire des comptes (chiffré par la clé maître)."""
        return self.data_dir / "annuaire.db"

    @property
    def accounts_dir(self) -> Path:
        """Une base chiffrée par compte, chacune avec sa propre clé."""
        return self.data_dir / "comptes"

    @property
    def legacy_db_path(self) -> Path:
        """Base unique non chiffrée des versions précédentes, migrée au démarrage."""
        return self.data_dir / "ancora.db"

    def secret_values(self) -> list[str]:
        """Valeurs à masquer dans les journaux."""
        values = [self.finnhub_api_key]
        if self.google:
            values.append(self.google.client_secret)
        return [v for v in values if v]


def _read_secrets() -> dict:
    if not SECRETS_FILE.exists():
        return {}
    with SECRETS_FILE.open("rb") as handle:
        return tomllib.load(handle)


def _section(secrets: dict, name: str, fields: tuple[str, ...]) -> dict | None:
    """Section [google] / [apple] du fichier de secrets, surchargée par ANCORA_GOOGLE_CLIENT_ID, etc."""
    values = dict(secrets.get(name) or {})
    for field in fields:
        env = os.environ.get(f"ANCORA_{name.upper()}_{field.upper()}")
        if env:
            values[field] = env
    path = values.pop("private_key_path", None) or os.environ.get(f"ANCORA_{name.upper()}_PRIVATE_KEY_PATH")
    if path and not values.get("private_key"):
        key_path = Path(path) if Path(path).is_absolute() else ROOT / path
        values["private_key"] = key_path.read_text(encoding="utf-8") if key_path.exists() else ""
    return values if all(values.get(f) for f in fields) else None


def load_config() -> AppConfig:
    secrets = _read_secrets()
    values: dict = {
        "finnhub_api_key": os.environ.get("FINNHUB_API_KEY") or secrets.get("finnhub_api_key"),
        "sec_user_agent": os.environ.get("SEC_USER_AGENT") or secrets.get("sec_user_agent"),
        "google": _section(secrets, "google", ("client_id", "client_secret")),
        "apple": _section(secrets, "apple", ("client_id", "team_id", "key_id", "private_key")),
    }
    for env, key in (("ANCORA_DATA_DIR", "data_dir"), ("ANCORA_BACKUP_DIR", "backup_dir"),
                     ("ANCORA_LOG_DIR", "log_dir"), ("ANCORA_KEY_FILE", "key_file")):
        if os.environ.get(env):
            values[key] = Path(os.environ[env])
    return AppConfig(**values)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config()
