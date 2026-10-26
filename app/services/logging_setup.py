"""Journalisation des erreurs, sans donnée sensible (cahier des charges §18 et §20)."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_PATTERNS = [
    (re.compile(r"(?i)\b(token|api[_-]?key|apikey|secret|password)=[^&\s]+"), r"\1=***"),
    (re.compile(r"(?i)(x-finnhub-token['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"), r"\1***"),
]


class RedactingFilter(logging.Filter):
    """Masque les clés API et secrets dans tous les messages journalisés."""

    def __init__(self, secrets: list[str] | None = None):
        super().__init__()
        self.secrets = [s for s in (secrets or []) if s]

    def redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "***")
        for pattern, replacement in _PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redact(record.getMessage())
        record.args = ()
        if record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        return True


def setup_logging(log_dir: Path, secrets: list[str] | None = None) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ancora.log"
    root = logging.getLogger()
    if any(getattr(h, "_ancora", False) for h in root.handlers):
        return log_file
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler._ancora = True  # type: ignore[attr-defined]
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s : %(message)s"))
    handler.addFilter(RedactingFilter(secrets))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # Les bibliothèques réseau peuvent journaliser des URL : on les limite aux avertissements.
    for noisy in ("urllib3", "yfinance", "peewee", "requests"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return log_file
