"""Démarrage commun aux interfaces ordinateur et téléphone. Aucun appel réseau."""
from __future__ import annotations

from app.config.settings import AppConfig
from app.database.engine import session_scope, upgrade_to_head
from app.services.logging_setup import setup_logging
from app.services.referential import seed_default_indices


def bootstrap(config: AppConfig) -> None:
    """Journaux, migrations (les données sont conservées), indices de référence au premier lancement."""
    setup_logging(config.log_dir, config.secret_values())
    upgrade_to_head(config.db_path)
    with session_scope(config.db_path) as session:
        seed_default_indices(session)
