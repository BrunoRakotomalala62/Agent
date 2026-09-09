# Agent Computer — image Docker (Railway / Render / tout hôte Docker)
# Machine toujours active : portail + terminal web + agent opencode.
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PORT=8125 \
    TTYD_PORT=7681 \
    MACHINE_DIR=/opt/agent-computer/machine/home/agent \
    HOST=0.0.0.0 \
    GEMINI_API_KEY="" \
    TERM_USER="" \
    TERM_PASS=""

# 1) Outils système
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
      curl git ca-certificates gnupg >/dev/null \
 && rm -rf /var/lib/apt/lists/*

# 2) Node + opencode (agent de codage — le cerveau)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null 2>&1 \
 && apt-get install -y -qq nodejs >/dev/null \
 && npm install -g --silent opencode-ai >/dev/null 2>&1 || npm install -g --silent opencode \
 && rm -rf /var/lib/apt/lists/*

# 3) ttyd (terminal web) — binaire statique selon l'architecture
ARG TARGETARCH
RUN case "${TARGETARCH:-amd64}" in \
      amd64) T="ttyd.x86_64" ;; \
      arm64) T="ttyd.aarch64" ;; \
      *) T="ttyd.x86_64" ;; esac; \
    curl -fsSL -o /usr/local/bin/ttyd "https://github.com/tsl0922/ttyd/releases/download/1.7.7/$T" \
 && chmod +x /usr/local/bin/ttyd

# 4) Projet
WORKDIR /opt/agent-computer
COPY portal.py .env.example README.md ./
COPY scripts/ scripts/
RUN chmod +x scripts/entrypoint.sh
COPY machine/home/agent/ machine/home/agent/
RUN chmod +x scripts/*.sh && mkdir -p var/log

# 5) Volume persistant (le code survit aux redéploiements/redémarrages)
VOLUME ["/opt/agent-computer/machine"]

EXPOSE 8125 7681
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fs http://127.0.0.1:8125/health >/dev/null || exit 1

ENTRYPOINT ["/opt/agent-computer/scripts/entrypoint.sh"]
