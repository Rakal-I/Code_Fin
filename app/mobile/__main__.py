"""Lance l'interface téléphone : python -m app.mobile

Par défaut, le serveur n'écoute que sur cet ordinateur (127.0.0.1). Pour y accéder
depuis le téléphone, utilisez Tailscale (« tailscale serve 8502 ») ou Cloudflare Tunnel
plutôt que d'exposer le port sur le réseau local. L'API exige en plus une connexion
(compte créé sur l'ordinateur).
"""
import os

import uvicorn


def main() -> None:
    uvicorn.run("app.mobile.server:app",
                host=os.environ.get("ANCORA_MOBILE_HOST", "127.0.0.1"),
                port=int(os.environ.get("ANCORA_MOBILE_PORT", "8502")),
                log_level="warning")


if __name__ == "__main__":
    main()
