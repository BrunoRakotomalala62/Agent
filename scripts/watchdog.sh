#!/usr/bin/env bash
# Watchdog de l'Agent Computer — auto-réparation permanente.
# Toutes les 15 s : vérifie portail + terminal, relance ce qui est mort,
# écrit un battement de cœur (preuve que la machine veille).
set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PORT="${PORT:-8125}"
TTYD_PORT="${TTYD_PORT:-7681}"
export HOME_AGENT="$ROOT/machine/home/agent"
export TTYD_PORT

beat() { date '+%F %T'; }

restart_portal() {
  nohup python3 "$ROOT/portal.py" --port "$PORT" >> "$ROOT/var/log/portal.log" 2>&1 &
  echo "$(beat) PORTAL relancé (pid $!)" >> "$ROOT/var/log/lifecycle.log"
}
restart_terminal() {
  ( cd "$HOME_AGENT" && HOME="$HOME_AGENT" \
      nohup "$ROOT/bin/ttyd" -p "$TTYD_PORT" -W -t titleFixed='Agent Computer — terminal' bash -l \
      >> "$ROOT/var/log/ttyd.log" 2>&1 & )
  echo "$(beat) TERMINAL relancé" >> "$ROOT/var/log/lifecycle.log"
}

echo "$(beat) watchdog démarré (pid $$) — contrôle toutes les 15 s"
while true; do
  curl -fs -o /dev/null --max-time 3 "http://127.0.0.1:$PORT/"  || restart_portal
  curl -fs -o /dev/null --max-time 3 "http://127.0.0.1:$TTYD_PORT/" || restart_terminal
  echo "$(beat)" > "$ROOT/var/watchdog.heartbeat"
  sleep 15
done
