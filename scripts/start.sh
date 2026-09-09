#!/usr/bin/env bash
# Agent Computer — démarrage : portail + terminal web + watchdog (auto-réparation)
# Machine TOUJOURS active : si un service meurt, le watchdog le relance.
set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
export ROOT

mkdir -p "$ROOT/var/log"
LOG_DIR="$ROOT/var/log"

# ports (surchargeables)
PORT="${PORT:-8125}"          # portail web
TTYD_PORT="${TTYD_PORT:-7681}" # terminal web
export TTYD_PORT

is_up() { curl -fs -o /dev/null --max-time 2 "http://127.0.0.1:$1/" 2>/dev/null; }

start_portal() {
  if is_up "$PORT"; then echo "portal déjà actif (:${PORT})"; return 0; fi
  nohup python3 "$ROOT/portal.py" --port "$PORT" >> "$LOG_DIR/portal.log" 2>&1 &
  echo $! > "$ROOT/var/portal.pid"
  echo "$(date '+%F %T') portal démarré (pid $!)" >> "$LOG_DIR/lifecycle.log"
}

start_terminal() {
  if is_up "$TTYD_PORT"; then echo "terminal déjà actif (:${TTYD_PORT})"; return 0; fi
  # Terminal web qui ouvre un shell bash DANS le dossier de travail de la machine
  ( cd "$HOME_AGENT" && HOME="$HOME_AGENT" \
      nohup "$ROOT/bin/ttyd" -p "$TTYD_PORT" -W -t titleFixed='Agent Computer — terminal' bash -l \
      >> "$LOG_DIR/ttyd.log" 2>&1 & echo $! > "$ROOT/var/ttyd.pid" )
  echo "$(date '+%F %T') terminal démarré (pid $(cat "$ROOT/var/ttyd.pid" 2>/dev/null))" >> "$LOG_DIR/lifecycle.log"
}

start_watchdog() {
  if pgrep -f "watchdog.sh" > /dev/null 2>&1; then echo "watchdog déjà actif"; return 0; fi
  nohup "$ROOT/scripts/watchdog.sh" >> "$LOG_DIR/watchdog.log" 2>&1 &
  echo $! > "$ROOT/var/watchdog.pid"
  echo "$(date '+%F %T') watchdog démarré (pid $!)" >> "$LOG_DIR/lifecycle.log"
}

# HOME_AGENT exporté pour le shell du terminal
export HOME_AGENT="$ROOT/machine/home/agent"

case "${1:-start}" in
  start)
    start_portal; start_terminal; start_watchdog
    echo
    echo "🖥️  Agent Computer actif :"
    echo "   Portail      → http://localhost:${PORT}"
    echo "   Terminal web → http://localhost:${TTYD_PORT}"
    echo "   Dossier code → $HOME_AGENT"
    ;;
  stop)
    for p in var/portal.pid var/ttyd.pid var/watchdog.pid; do
      [ -f "$ROOT/$p" ] && kill "$(cat "$ROOT/$p")" 2>/dev/null && rm -f "$ROOT/$p"
    done
    pkill -f "watchdog.sh" 2>/dev/null
    echo "Arrêté."
    ;;
  status)
    echo "portal :     $(is_up "$PORT" && echo ACTIF || echo arrêté)"
    echo "terminal :   $(is_up "$TTYD_PORT" && echo ACTIF || echo arrêté)"
    echo "watchdog :   $(pgrep -f watchdog.sh > /dev/null && echo ACTIF || echo arrêté)"
    ;;
  *) echo "usage: $0 {start|stop|status}"; exit 1;;
esac
