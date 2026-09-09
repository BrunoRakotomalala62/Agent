# Agent Computer — image Docker (Railway / Render / tout hôte Docker)
# UN SEUL PORT : portail + terminal intégré (xterm.js) + agent opencode.
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PORT=8125 \
    WS_DIR=/opt/agent-computer/machine \
    GEMINI_API_KEY="" \
    TERM_PASS="" \
    GITHUB_TOKEN="" \
    GIT_USER="Agent Computer" \
    GIT_EMAIL="agent@computer.local" \
    REPO_URL="https://github.com/BrunoRakotomalala62/Agent.git"

# 1) Outils système
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
      curl git ca-certificates gnupg >/dev/null \
 && rm -rf /var/lib/apt/lists/*

# 2) Node + opencode (agent de codage — le cerveau)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null 2>&1 \
 && apt-get install -y -qq nodejs >/dev/null \
 && npm install -g --silent opencode-ai >/dev/null 2>&1 || npm install -g --silent opencode \
 && rm -rf /var/lib/apt/lists/*

# 3) Dépendances webapp (portail + terminal intégré)
RUN pip install --no-cache-dir -q fastapi "uvicorn[standard]" >/dev/null

# 4) Projet
WORKDIR /opt/agent-computer
COPY webapp.py portal.py .env.example README.md DEPLOIEMENT.md ./
COPY scripts/ scripts/
RUN chmod +x scripts/entrypoint.sh
COPY machine/home/agent/ machine/home/agent/
RUN chmod +x scripts/*.sh && mkdir -p var/log

# 5) Volume persistant (sur Railway : le code survit ; sur Render free : la
#    sauvegarde est assurée par le push automatique de l'agent sur GitHub)
VOLUME ["/opt/agent-computer/machine"]

EXPOSE 8125
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fs http://127.0.0.1:8125/health >/dev/null || exit 1

ENTRYPOINT ["/opt/agent-computer/scripts/entrypoint.sh"]
