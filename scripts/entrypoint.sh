#!/usr/bin/env bash
# Agent Computer — point d'entrée conteneur : portail + TERMINAL INTÉGRÉ (webapp)
set -u
cd /opt/agent-computer
export MACHINE_DIR="${MACHINE_DIR:-/opt/agent-computer/machine/home/agent}"
mkdir -p "$MACHINE_DIR" /opt/agent-computer/var/log

# 1) Si le volume persistant est vide, initialiser le dossier de travail
if [ ! -f "$MACHINE_DIR/LISEZMOI.txt" ]; then
  echo "→ Initialisation du dossier de travail persistant…"
  cp -an /opt/agent-computer/machine/home/agent/. "$MACHINE_DIR/" 2>/dev/null || true
  [ -f "$MACHINE_DIR/LISEZMOI.txt" ] || printf '# Bienvenue sur votre Agent Computer (conteneur)\n\nLe code stocké ici survit aux redémarrages (volume persistant).\n' > "$MACHINE_DIR/LISEZMOI.txt"
fi

# 2) Sécurité : mot de passe obligatoire pour le terminal intégré
if [ -z "${TERM_PASS:-}" ]; then
  echo "⚠️  TERM_PASS non défini : le terminal intégré sera OUVERT (risqué en public) !"
fi

# 3) Un seul service : portail + terminal (port ${PORT:-8125})
echo "→ Agent Computer (portail + terminal intégré) sur :${PORT:-8125}"
exec python3 -m uvicorn webapp:app --host 0.0.0.0 --port "${PORT:-8125}"
