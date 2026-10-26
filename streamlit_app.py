"""Ancora : serveur de l'interface ordinateur.

Lancement : streamlit run streamlit_app.py   (http://localhost:8501)

Streamlit sert le script interface.py ; on y ajoute les routes de connexion par Face ID /
Touch ID (/connexion/cle/…), que Streamlit seul ne sait pas recevoir.
"""
from pathlib import Path

import streamlit as st

from app.web import connexion

app = st.App(Path(__file__).with_name("interface.py"), routes=connexion.routes("desktop"))
