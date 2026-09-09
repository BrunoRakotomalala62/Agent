#!/usr/bin/env bash
# Agent Computer — brancher GitHub (une seule fois par machine)
# Usage :
#   1) créez un Personal Access Token GitHub (classic, scope repo) : GitHub → Settings → Developer settings → Tokens
#   2) .env :  GITHUB_TOKEN=..., GIT_USER=..., GIT_EMAIL=...
#   3) ./scripts/git-setup.sh   (avec .env rempli)
#   4) pour cloner un dépôt dans la machine : ./scripts/git-setup.sh clone https://github.com/vous/projet
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
export HOME_AGENT="$ROOT/machine/home/agent"

# charge .env s'il existe
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a

TOKEN="${GITHUB_TOKEN:-}"
USER="${GIT_USER:-}"
EMAIL="${GIT_EMAIL:-}"

echo "→ Configuration git dans la machine ($HOME_AGENT)"
git -C "$HOME_AGENT" config user.name  "${USER:-Agent Computer}"
git -C "$HOME_AGENT" config user.email "${EMAIL:-agent@computer.local}"
if [ -n "$TOKEN" ]; then
  # le token sert aux push (écrit dans .git/config de la machine uniquement, pas dans le code)
  git -C "$HOME_AGENT" config --global credential.helper store
  touch "$HOME_AGENT/.git-credentials" && chmod 600 "$HOME_AGENT/.git-credentials"
  echo "ATTENTION : le token sera stocké dans $HOME_AGENT/.git-credentials (protégé)."
fi

case "${1:-}" in
  clone)
    URL="${2:?usage: git-setup.sh clone https://github.com/user/repo}"
    echo "→ Clonage de $URL dans le dossier de travail…"
    if [ -n "$TOKEN" ]; then
      # clone authentifié sans exposer le token dans l'URL (fichier .git/config)
      git -C "$HOME_AGENT" clone "$URL" .
    else
      git -C "$HOME_AGENT" clone "$URL" .
    fi
    echo "→ Cloné. Le code est maintenant stocké dans votre machine."
    ;;
  *)
    echo "Configuration git terminée."
    echo "Puis :  ./scripts/git-setup.sh clone https://github.com/vous/projet"
    ;;
esac
