#!/bin/bash
# Lance les deux interfaces d'Ancora dans le Codespace (relancé à chaque ouverture).
cd "$(dirname "$0")/.."
mkdir -p logs
pkill -f "streamlit run" 2>/dev/null; pkill -f "app.mobile" 2>/dev/null
# Le Codespace est derrière un proxy HTTPS de GitHub : Streamlit doit en accepter les en-têtes.
nohup streamlit run streamlit_app.py --server.port 8501 --server.headless true \
  --server.enableCORS false --server.enableXsrfProtection false > logs/ordinateur.log 2>&1 &
ANCORA_MOBILE_HOST=0.0.0.0 nohup python -m app.mobile > logs/telephone.log 2>&1 &
echo "Ancora démarre : ouvrez l'onglet « Ports » et cliquez sur l'adresse du port 8501 (ordinateur) ou 8502 (téléphone)."
