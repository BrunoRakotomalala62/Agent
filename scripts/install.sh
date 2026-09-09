#!/usr/bin/env bash
# Agent Computer — installation sur un serveur Linux (Ubuntu/Debian recommandé)
# Usage :  sudo bash install.sh [--with-opencode]
# Résultat : services systemd actifs + relancés automatiquement au démarrage (24/7).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
DEST="${DEST:-/opt/agent-computer}"
WITH_OPENCODE=0
[ "${1:-}" = "--with-opencode" ] && WITH_OPENCODE=1

echo "→ Installation dans $DEST"

# 1) Dépendances système
sudo apt-get update -qq
sudo apt-get install -y -qq python3 git curl ca-certificates >/dev/null

# 2) ttyd (terminal web) — binaire statique
if ! command -v ttyd >/dev/null 2>&1 && [ ! -x "$DEST/bin/ttyd" ]; then
  echo "→ Téléchargement de ttyd…"
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64) TTYD="ttyd.x86_64";;
    aarch64|arm64) TTYD="ttyd.aarch64";;
    *) echo "Architecture $ARCH non supportée par le script (installez ttyd manuellement)."; exit 1;;
  esac
  curl -fsSL -o /tmp/ttyd "https://github.com/tsl0922/ttyd/releases/download/1.7.7/$TTYD"
  chmod +x /tmp/ttyd
  sudo mkdir -p "$DEST/bin"
  sudo mv /tmp/ttyd "$DEST/bin/ttyd"
fi

# 3) Copie du projet
sudo mkdir -p "$DEST"
sudo cp -a "$ROOT"/. "$DEST/"
sudo chmod +x "$DEST/bin/ttyd" "$DEST"/scripts/*.sh "$DEST/portal.py"
# le dossier var doit être inscriptible
sudo mkdir -p "$DEST/var/log" && sudo chmod -R a+rw "$DEST/var"

# 4) Agent opencode (optionnel) — le moteur d'agent que Tembo utilise aussi
if [ "$WITH_OPENCODE" = "1" ]; then
  echo "→ Installation d'opencode (agent de codage local)…"
  if ! command -v node >/dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - >/dev/null 2>&1 || true
    sudo apt-get install -y -qq nodejs >/dev/null
  fi
  sudo npm install -g opencode-ai >/dev/null 2>&1 || sudo npm install -g opencode
  echo "   ok : $(opencode --version 2>/dev/null || echo 'opencode installé')"
fi

# 5) Unités systemd (démarrage auto + redémarrage en cas de crash)
sudo sed "s|__ROOT__|$DEST|g" "$DEST/systemd/agent-computer-portal.service"    > /etc/systemd/system/agent-computer-portal.service
sudo sed "s|__ROOT__|$DEST|g" "$DEST/systemd/agent-computer-ttyd.service"      > /etc/systemd/system/agent-computer-ttyd.service
sudo sed "s|__ROOT__|$DEST|g" "$DEST/systemd/agent-computer-watchdog.service"  > /etc/systemd/system/agent-computer-watchdog.service
sudo systemctl daemon-reload
sudo systemctl enable --now agent-computer-portal agent-computer-ttyd agent-computer-watchdog
sudo systemctl restart agent-computer-portal agent-computer-ttyd agent-computer-watchdog

echo
echo "✅ Agent Computer installé et ACTIF en permanence :"
echo "   Portail      → http://$(hostname -I | awk '{print $1}'):8125"
echo "   Terminal web → http://$(hostname -I | awk '{print $1}'):7681"
echo
echo "Pour configurer votre clé d'IA et GitHub :"
echo "   sudo nano $DEST/.env   puis relisez la doc README.md"
