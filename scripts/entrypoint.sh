#!/usr/bin/env bash
# Agent Computer — point d'entrée conteneur (Docker/Railway/Render)
# Lance portail + terminal web en avant-plan ; le redémarrage en cas de crash
# est géré par la plateforme (Restart policy / Railway auto-restart).
set -u
cd /opt/agent-computer
export MACHINE_DIR="${MACHINE_DIR:-/opt/agent-computer/machine/home/agent}"
mkdir -p "$MACHINE_DIR" /opt/agent-computer/var/log

# --- 1) Si le volume persistant est vide, on y remet les fichiers de départ ---
if [ ! -f "$MACHINE_DIR/LISEZMOI.txt" ]; then
  echo "→ Initialisation du dossier de travail persistant…"
  cp -an /opt/agent-computer/machine/home/agent/. "$MACHINE_DIR/" 2>/dev/null || true
  [ -f "$MACHINE_DIR/LISEZMOI.txt" ] || printf '# Bienvenue sur votre Agent Computer (conteneur)\n\nLe code stocké ici survit aux redémarrages (volume persistant).\n' > "$MACHINE_DIR/LISEZMOI.txt"
fi

# --- 2) Terminal web (ttyd) avec mot de passe OBLIGATOIRE si TERM_PASS défini ---
TTYD_EXTRA=()
if [ -n "${TERM_USER:-}" ] && [ -n "${TERM_PASS:-}" ]; then
  TTYD_EXTRA=(-c "$TERM_USER:$TERM_PASS")
  echo "→ Terminal protégé par mot de passe ($TERM_USER)"
else
  echo "⚠️  TERM_USER/TERM_PASS non définis : le terminal sera OUVERT (risqué en public) !"
fi
( cd "$MACHINE_DIR" && HOME="$MACHINE_DIR" \
    ttyd -p "${TTYD_PORT:-7681}" -W "${TTYD_EXTRA[@]}" -t titleFixed='Agent Computer — terminal' bash -l \
    >> /opt/agent-computer/var/log/ttyd.log 2>&1 & )
echo "→ Terminal web sur :${TTYD_PORT:-7681}"

# --- 3) Portail web ---
python3 /opt/agent-computer/portal.py --port "${PORT:-8125}" \
  >> /opt/agent-computer/var/log/portal.log 2>&1 &
echo "→ Portail web sur :${PORT:-8125}"

# --- 4) Garder le conteneur vivant + journal visible ---
echo "→ Agent Computer ACTIF (Ctrl+C pour arrêter)"
trap 'kill $(jobs -p) 2>/dev/null' EXIT INT TERM
tail -f /opt/agent-computer/var/log/portal.log /opt/agent-computer/var/log/ttyd.log &
wait
