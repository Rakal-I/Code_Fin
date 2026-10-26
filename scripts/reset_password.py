"""Mot de passe oublié : choisit un nouveau mot de passe pour un compte. Ses données sont conservées.

Usage : python scripts/reset_password.py
À lancer sur l'ordinateur qui héberge Ancora (la clé maître y est nécessaire). Les téléphones
connectés à ce compte sont déconnectés.
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.bootstrap import bootstrap  # noqa: E402
from app.config.settings import get_config  # noqa: E402
from app.services import auth, workspace  # noqa: E402


def main() -> None:
    config = get_config()
    bootstrap(config)
    accounts = workspace.list_accounts(config)
    if not accounts:
        print("Aucun compte : lancez Ancora sur l'ordinateur pour en créer un.")
        return
    print("Comptes :")
    for index, (_id, name, username, email) in enumerate(accounts, start=1):
        details = ", ".join(x for x in (f"identifiant {username}" if username else None, email) if x)
        print(f"  {index}. {name}" + (f" ({details})" if details else ""))
    choice = input("Numéro du compte : ").strip()
    if not choice.isdigit() or not 1 <= int(choice) <= len(accounts):
        print("Annulé.")
        return
    account_id, name, username, _ = accounts[int(choice) - 1]
    if not username:
        username = input("Ce compte n'a pas d'identifiant (Google / Apple). Identifiant à créer : ").strip()
    password = getpass.getpass("Nouveau mot de passe : ")
    confirmation = getpass.getpass("Confirmation : ")
    try:
        with workspace.directory(config) as s:
            account = auth.get_account(s, account_id)
            if account.username is None:
                auth.set_password(s, account, username, password, confirmation)
            else:
                auth.reset_password(s, account, password, confirmation)
    except auth.AuthError as exc:
        sys.exit(str(exc))
    print(f"Mot de passe de « {name} » modifié. Connectez-vous avec l'identifiant « {username} ».")


if __name__ == "__main__":
    main()
