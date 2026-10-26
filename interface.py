"""Ancora : interface ordinateur (script Streamlit, servi par streamlit_app.py).

Lancement : streamlit run streamlit_app.py

Le script est à la racine (et non à côté de app/pages) : Streamlit active sinon
son ancien mode « dossier pages », incompatible avec la navigation ci-dessous.
"""
from pathlib import Path

import streamlit as st

from app.services import market_data, referential
from app.ui import context, login, theme

st.set_page_config(page_title="Ancora", page_icon=str(theme.FAVICON), layout="wide",
                   initial_sidebar_state="expanded")
theme.apply()
st.logo(str(theme.LOGO), size="large", icon_image=str(theme.ICON))

# Connexion obligatoire avant toute donnée : chaque compte n'ouvre que sa propre base chiffrée.
ws = login.require_login()

PAGES = Path(__file__).parent / "app" / "pages"
navigation = st.navigation({
    "Patrimoine": [
        st.Page(PAGES / "dashboard.py", title="Tableau de bord", icon=":material/donut_large:", default=True),
        st.Page(PAGES / "portfolio.py", title="Portefeuille", icon=":material/account_balance_wallet:"),
        st.Page(PAGES / "envelopes.py", title="Enveloppes", icon=":material/folder_open:"),
        st.Page(PAGES / "income.py", title="Revenus", icon=":material/payments:"),
    ],
    "Marchés": [
        st.Page(PAGES / "markets.py", title="Marchés", icon=":material/show_chart:"),
        st.Page(PAGES / "quality.py", title="Qualité des données", icon=":material/verified:"),
    ],
    "Gestion": [
        st.Page(PAGES / "entry.py", title="Saisie", icon=":material/edit_note:"),
        st.Page(PAGES / "admin.py", title="Administration", icon=":material/tune:"),
    ],
})

# Barre latérale : masquage des montants et fraîcheur des données (vérifiée au démarrage, sans réseau).
with st.sidebar:
    stored = context.prefs()
    masked = st.toggle("Masquer les montants", value=stored.mask_amounts, key="mask_amounts")
    if masked != stored.mask_amounts:
        with context.session() as s:
            referential.save_preferences(s, referential.Preferences(
                mask_amounts=masked, price_stale_days=stored.price_stale_days,
                fundamental_stale_days=stored.fundamental_stale_days))
    with context.session() as s:
        stale = market_data.stale_prices(s, context.prefs())
        last = market_data.last_refresh(s)
    st.caption(f"Dernière actualisation : {theme.day(last) if last else 'jamais'} (UTC)")
    if stale:
        st.caption(f"🟠 {len(stale)} instrument(s) sans cours à jour.")
    if st.button("Actualiser tout", icon=":material/refresh:", width="stretch"):
        with context.session() as s:
            progress = st.progress(0.0, text="Actualisation…")
            results = market_data.refresh_all(
                s, context.connectors(),
                progress=lambda i, n, name: progress.progress(i / max(n, 1), text=f"{name} ({i}/{n})"))
            progress.empty()
        failed = [r for r in results if not r.ok]
        if failed:
            st.warning(f"{len(failed)} élément(s) en erreur : voir « Qualité des données ».")
        else:
            st.success("Données actualisées.")
    st.divider()
    st.caption(f"Connecté : {ws.name}")
    if st.button("Se déconnecter", icon=":material/logout:", width="stretch"):
        login.logout("Vous êtes déconnecté.")
        st.rerun()

navigation.run()
