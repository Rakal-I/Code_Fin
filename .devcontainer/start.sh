#!/bin/bash
# Lance les deux interfaces d'Ancora dans le Codespace (relancé à chaque ouverture).
cd "$(dirname "$0")/.."
mkdir -p logs
pkill -f "streamlit run" 2>/dev/null; pkill -f "app.mobile" 2>/dev/null
# Le Codespace est derrière un proxy HTTPS de GitHub : on autorise l'adresse du Codespace pour la
# connexion temps réel (WebSocket) de Streamlit, sans désactiver les protections CORS / XSRF
# (les désactiver ensemble laisse l'écran blanc).
ORIGINS=""
if [ -n "$CODESPACE_NAME" ]; then
  DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  ORIGINS="--server.corsAllowedOrigins=https://${CODESPACE_NAME}-8501.${DOMAIN}"
fi
nohup streamlit run streamlit_app.py --server.port 8501 --server.headless true $ORIGINS \
  > logs/ordinateur.log 2>&1 &
ANCORA_MOBILE_HOST=0.0.0.0 nohup python -m app.mobile > logs/telephone.log 2>&1 &
echo "Ancora démarre : ouvrez l'onglet « Ports » et cliquez sur l'adresse du port 8501 (ordinateur) ou 8502 (téléphone)."
