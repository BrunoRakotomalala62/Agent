#!/usr/bin/env bash
# Agent Computer — point d'entrée conteneur : portail + terminal intégré (webapp)
# Au démarrage : branche GitHub (si GITHUB_TOKEN fourni) pour que l'agent
# puisse pousser automatiquement après chaque modification (AGENTS.md).
set -u
cd /opt/agent-computer
export WS_DIR="${WS_DIR:-/opt/agent-computer/machine}"
mkdir -p "$WS_DIR" /opt/agent-computer/var/log

# 1) Dossier de travail :
#    - avec GITHUB_TOKEN → clone frais du dépôt (l'agent modifie le VRAI projet et pousse)
#    - sans token        → simple dossier local (démo, non sauvegardé)
if [ -n "${GITHUB_TOKEN:-}" ]; then
  export WS_DIR="${WS_DIR:-/opt/workspace}"
  echo "→ Workspace : ${REPO_URL:-Agent.git} cloné dans $WS_DIR (sauvegarde auto par l'agent)"
  GITHUB_TOKEN="$GITHUB_TOKEN" REPO_URL="${REPO_URL:-https://github.com/BrunoRakotomalala62/Agent.git}" \
    GIT_USER="${GIT_USER:-Agent Computer}" GIT_EMAIL="${GIT_EMAIL:-agent@computer.local}" \
    WS_DIR="$WS_DIR" bash /opt/agent-computer/scripts/git-autosetup.sh || echo "⚠️ branchement GitHub échoué"
else
  export WS_DIR="${WS_DIR:-/opt/agent-computer/machine/home/agent}"
  echo "→ Pas de token GitHub : dossier local (non sauvegardé) : $WS_DIR"
  mkdir -p "$WS_DIR"
  if [ ! -f "$WS_DIR/LISEZMOI.txt" ]; then
    cp -an /opt/agent-computer/machine/home/agent/. "$WS_DIR/" 2>/dev/null || true
    [ -f "$WS_DIR/LISEZMOI.txt" ] || printf '# Bienvenue sur votre Agent Computer (conteneur)\n\nAjoutez GITHUB_TOKEN pour que l'\''agent sauvegarde automatiquement sur GitHub.\n' > "$WS_DIR/LISEZMOI.txt"
  fi
fi

# 2) Sécurité : mot de passe obligatoire pour le terminal intégré
if [ -z "${TERM_PASS:-}" ]; then
  echo "⚠️  TERM_PASS non défini : le terminal intégré sera OUVERT (risqué en public) !"
fi

# 3) Config opencode : modèle par défaut (évite le choix interactif au 1er lancement)
mkdir -p "${HOME:-/root}/.config/opencode"
if [ ! -f "${HOME:-/root}/.config/opencode/opencode.json" ]; then
  printf '{"model":"google/gemini-3.6-flash"}\n' > "${HOME:-/root}/.config/opencode/opencode.json"
fi

# 4) Un seul service : portail + terminal intégré (port ${PORT:-8125})
echo "→ Agent Computer (portail + terminal intégré) sur :${PORT:-8125} — dossier : $WS_DIR"
exec env WS_DIR="$WS_DIR" python3 -m uvicorn webapp:app --host 0.0.0.0 --port "${PORT:-8125}"
