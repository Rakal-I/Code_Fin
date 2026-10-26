"""Configuration de l'application.

Les chemins et paramètres techniques viennent des variables d'environnement.
Les clés API viennent de l'environnement ou de ``config/secrets.toml``, qui n'est
jamais versionné (cahier des charges §18).
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


class AppConfig(BaseModel):
    data_dir: Path = Field(default=ROOT / "data")
    backup_dir: Path = Field(default=ROOT / "backups")
    log_dir: Path = Field(default=ROOT / "logs")
    # Clé maître : trousseau du système si disponible, sinon ce fichier (hors du dossier du projet).
    key_file: Path = Field(default=Path.home() / ".ancora" / "cle-maitre")
    request_timeout: float = 15.0
    finnhub_api_key: str | None = None
    sec_user_agent: str | None = None

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
        return [v for v in (self.finnhub_api_key,) if v]


def _read_secrets() -> dict:
    if not SECRETS_FILE.exists():
        return {}
    with SECRETS_FILE.open("rb") as handle:
        return tomllib.load(handle)


def load_config() -> AppConfig:
    secrets = _read_secrets()
    values: dict = {
        "finnhub_api_key": os.environ.get("FINNHUB_API_KEY") or secrets.get("finnhub_api_key"),
        "sec_user_agent": os.environ.get("SEC_USER_AGENT") or secrets.get("sec_user_agent"),
    }
    for env, key in (("ANCORA_DATA_DIR", "data_dir"), ("ANCORA_BACKUP_DIR", "backup_dir"),
                     ("ANCORA_LOG_DIR", "log_dir"), ("ANCORA_KEY_FILE", "key_file")):
        if os.environ.get(env):
            values[key] = Path(os.environ[env])
    return AppConfig(**values)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config()
