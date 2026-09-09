#!/usr/bin/env bash
# Agent Computer — point d'entrée conteneur : portail + terminal intégré (webapp)
# Au démarrage : branche GitHub (si GITHUB_TOKEN fourni) pour que l'agent
# puisse pousser automatiquement après chaque modification (AGENTS.md).
set -u
cd /opt/agent-computer
export WS_DIR="${WS_DIR:-/opt/agent-computer/machine}"
mkdir -p "$WS_DIR" /opt/agent-computer/var/log

# 1) Dossier de travail : clone/pull du dépôt GitHub (mémoire durable) OU seed local
if [ -n "${GITHUB_TOKEN:-}" ]; then
  echo "→ Branchement GitHub pour sauvegarde automatique par l'agent…"
  GITHUB_TOKEN="$GITHUB_TOKEN" REPO_URL="${REPO_URL:-https://github.com/BrunoRakotomalala62/Agent.git}" \
    GIT_USER="${GIT_USER:-Agent Computer}" GIT_EMAIL="${GIT_EMAIL:-agent@computer.local}" \
    WS_DIR="$WS_DIR" bash /opt/agent-computer/scripts/git-autosetup.sh || echo "⚠️ branchement GitHub échoué"
elif [ ! -f "$WS_DIR/LISEZMOI.txt" ] && [ ! -f "$WS_DIR/README.md" ]; then
  echo "→ Pas de token GitHub : simple dossier de travail (non sauvegardé)."
  cp -an /opt/agent-computer/machine/home/agent/. "$WS_DIR/" 2>/dev/null || true
  [ -f "$WS_DIR/LISEZMOI.txt" ] || printf '# Bienvenue sur votre Agent Computer (conteneur)\n\nAjoutez GITHUB_TOKEN pour que l'\''agent sauvegarde automatiquement sur GitHub.\n' > "$WS_DIR/LISEZMOI.txt"
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
