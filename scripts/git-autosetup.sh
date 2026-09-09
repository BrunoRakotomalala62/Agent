#!/usr/bin/env bash
# Agent Computer — brancher GitHub pour que l'AGENT pousse automatiquement.
# À lancer une fois (ou au démarrage du conteneur). Idempotent.
#
# Variables lues (env ou .env) :
#   GITHUB_TOKEN   token GitHub (fine-grained, accès en écriture au dépôt)
#   REPO_URL       défaut : https://github.com/BrunoRakotomalala62/Agent.git
#   GIT_USER       défaut : Agent Computer
#   GIT_EMAIL      défaut : agent@computer.local
#   WS_DIR         dossier de travail (défaut : machine/home/agent)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

[ -f .env ] && set -a && . .env && set +a
TOKEN="${GITHUB_TOKEN:-}"
REPO_URL="${REPO_URL:-https://github.com/BrunoRakotomalala62/Agent.git}"
GIT_USER="${GIT_USER:-Agent Computer}"
GIT_EMAIL="${GIT_EMAIL:-agent@computer.local}"
WS_DIR="${WS_DIR:-$ROOT/machine/home/agent}"
mkdir -p "$WS_DIR"

echo "→ Dossier de travail : $WS_DIR"

# 1) Identifiants (jamais dans le code ; protégés chmod 600)
if [ -n "$TOKEN" ]; then
  if [ -n "${HOME:-}" ] && [ -w "$HOME" ]; then
    git config --global credential.helper store
    echo "https://x-access-token:${TOKEN}@github.com" > "$HOME/.git-credentials"
    chmod 600 "$HOME/.git-credentials"
  fi
else
  echo "⚠️  GITHUB_TOKEN absent : l'agent ne pourra pas pousser. Ajoutez-le puis relancez."
fi

# 2) Dépôt : clone si vide, pull si existant
if [ ! -d "$WS_DIR/.git" ]; then
  if [ -z "$(ls -A "$WS_DIR" | head -1)" ]; then
    echo "→ Dossier vide : clonage de $REPO_URL …"
    git clone --depth 1 "$REPO_URL" "$WS_DIR" || {
      echo "✖ Clone impossible (réseau ou accès)."; exit 1; }
  else
    echo "→ Initialisation d'un dépôt local…"
    git -C "$WS_DIR" init -q -b main
    git -C "$WS_DIR" remote add origin "$REPO_URL" 2>/dev/null || true
    git -C "$WS_DIR" fetch -q origin main || true
    git -C "$WS_DIR" checkout -q -b main 2>/dev/null || git -C "$WS_DIR" checkout -q main || true
  fi
else
  echo "→ Dépôt existant : récupération des dernières versions…"
  git -C "$WS_DIR" pull --rebase -q origin main 2>/dev/null || \
    echo "  (pull impossible — on continue avec l'état local)"
fi

# 3) Identité locale (pour des commits propres)
git -C "$WS_DIR" config user.name  "$GIT_USER"
git -C "$WS_DIR" config user.email "$GIT_EMAIL"

echo "✅ Prêt : l'agent poussera automatiquement après chaque modification (AGENTS.md)."
