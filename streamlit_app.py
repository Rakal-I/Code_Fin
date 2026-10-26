"""Ancora : serveur de l'interface ordinateur.

Lancement : streamlit run streamlit_app.py   (http://localhost:8501)

Streamlit sert le script interface.py ; on y ajoute les routes « Continuer avec Google / Apple »
(/connexion/…), que Streamlit seul ne sait pas recevoir (Apple répond par un POST).
"""
from pathlib import Path

import streamlit as st

from app.web import connexion

app = st.App(Path(__file__).with_name("interface.py"), routes=connexion.routes("desktop"))
