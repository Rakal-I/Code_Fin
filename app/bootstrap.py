"""Démarrage commun aux interfaces ordinateur et téléphone. Aucun appel réseau."""
from __future__ import annotations

from app.config.settings import AppConfig
from app.services import workspace
from app.services.logging_setup import setup_logging


def bootstrap(config: AppConfig) -> None:
    """Journaux, clé maître, annuaire des comptes (et migration d'une ancienne base non chiffrée).

    La base de chaque compte est migrée et complétée (indices de référence) à sa première ouverture.
    """
    setup_logging(config.log_dir, config.secret_values())
    workspace.ensure_directory(config)
