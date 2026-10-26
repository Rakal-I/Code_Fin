"""Mot de passe oublié : supprime le compte Ancora (vos données patrimoniales sont conservées).

Usage : python scripts/reset_password.py
Au prochain lancement sur l'ordinateur, Ancora vous demandera de créer un nouvel accès.
Les téléphones connectés sont déconnectés.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_config  # noqa: E402
from app.database.engine import session_scope, upgrade_to_head  # noqa: E402
from app.services import auth  # noqa: E402


def main() -> None:
    config = get_config()
    upgrade_to_head(config.db_path)
    answer = input(f"Réinitialiser l'accès à {config.db_path} ? Tapez OUI pour confirmer : ")
    if answer.strip() != "OUI":
        print("Annulé.")
        return
    with session_scope(config.db_path) as session:
        auth.reset_account(session)
    print("Accès réinitialisé. Relancez Ancora sur l'ordinateur pour créer un nouveau mot de passe.")


if __name__ == "__main__":
    main()
