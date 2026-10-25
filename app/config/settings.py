"""Configuration de l'application.

Les chemins et paramètres techniques viennent des variables d'environnement.
Les clés API viennent de l'environnement ou de ``config/secrets.toml``, qui
n'est jamais versionné (cahier des charges §18 : protection des clés API).
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
    db_path: Path = Field(default=ROOT / "data" / "ancora.db")
    backup_dir: Path = Field(default=ROOT / "backups")
    log_dir: Path = Field(default=ROOT / "logs")
    request_timeout: float = 15.0
    finnhub_api_key: str | None = None
    sec_user_agent: str | None = None

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
    if os.environ.get("ANCORA_DB_PATH"):
        values["db_path"] = Path(os.environ["ANCORA_DB_PATH"])
    if os.environ.get("ANCORA_BACKUP_DIR"):
        values["backup_dir"] = Path(os.environ["ANCORA_BACKUP_DIR"])
    if os.environ.get("ANCORA_LOG_DIR"):
        values["log_dir"] = Path(os.environ["ANCORA_LOG_DIR"])
    return AppConfig(**values)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config()
