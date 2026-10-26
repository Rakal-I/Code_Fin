"""Affiche la clé de secours (clé maître) qui déchiffre tous les comptes de cet ordinateur.

Usage : python scripts/cle_de_secours.py

Notez-la et rangez-la hors de l'ordinateur (gestionnaire de mots de passe, papier au coffre).
Sans elle, une sauvegarde copiée sur un autre ordinateur ne peut pas être ouverte. Pour l'utiliser
ailleurs : variable d'environnement ANCORA_MASTER_KEY=<clé>.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import get_config  # noqa: E402
from app.services import vault, workspace  # noqa: E402


def main() -> None:
    answer = input("La clé de secours donne accès à tous les comptes. L'afficher ? Tapez OUI : ")
    if answer.strip() != "OUI":
        print("Annulé.")
        return
    print(vault.format_recovery_key(workspace.master(get_config())))


if __name__ == "__main__":
    main()
