"""Connecteurs actifs, par ordre de priorité (annexe B : stratégie retenue)."""
from __future__ import annotations

from app.config.settings import AppConfig
from app.connectors.base import Connector
from app.connectors.finnhub import FinnhubConnector
from app.connectors.sec_edgar import SecEdgarConnector
from app.connectors.yahoo import YahooConnector

MANUAL_SOURCE = "Saisie manuelle"


def build_connectors(config: AppConfig) -> list[Connector]:
    """Principale (Yahoo), secondaire (Finnhub), réglementaire (SEC EDGAR).

    La saisie manuelle, source de secours, passe par l'interface.
    """
    return [
        YahooConnector(timeout=config.request_timeout),
        FinnhubConnector(config.finnhub_api_key, timeout=config.request_timeout),
        SecEdgarConnector(config.sec_user_agent, timeout=config.request_timeout),
    ]
