# 🚀 Déploiement de l'Agent Computer

Deux modes de vie possibles :
- **🌙 Mode économique (0 €)** : la machine **s'endort quand elle est inactive** et se
  **réveille seule quand le site est ouvert** ou qu'une tâche démarre. → Replit ou Render gratuits.
- **⚡ Mode 24/7** : toujours active, sans sommeil. → Railway (~5 $/mois) ou VPS (~4 €/mois).

Le projet contient un `Dockerfile` (Render/Railway), un `render.yaml` (Render) et un guide Replit.

> ⚠️ **Vercel et Netlify : non** (serverless : pas de processus long, pas de terminal, pas de disque).

---

# 🌙 MODE ÉCONOMIQUE (gratuit) — réveil à la demande + veille auto

```
ouverture du site  →  la machine se réveille (2-5 s)
        ↓
   l'agent code (actif)
        ↓
  inactivité (~5-15 min)  →  la machine se met en veille (coût : 0 €)
```

## Option gratuite n°1 : Replit (recommandée pour essayer — terminal inclus)

1. **replit.com** → compte gratuit → **Create Repl → Import from GitHub**
   → `https://github.com/BrunoRakotomalala62/Agent` (langage : Python).
2. Onglet **Shell** (c'est le terminal de la machine) :
   ```bash
   cp .env.example .env      # collez GEMINI_API_KEY= (votre clé Google AI Studio)
   npm install -g opencode-ai
   ```
3. Lancez le portail (port 3000 = aperçu web Replit) :
   ```bash
   PORT=3000 HOST=0.0.0.0 python3 portal.py
   ```
4. L'aperçu web affiche le tableau de bord (statut, fichiers, journal).
5. Faire coder l'agent : dans le **Shell**, tapez `opencode` → il lit/écrit les
   fichiers du projet directement. Les fichiers sont conservés entre les sessions.

**Comportement gratuit** : le Repl dort après ~5 min d'inactivité, se réveille en 3-5 s
quand vous le rouvrez. Limites : CPU partagé, ~512 Mo-1 Go de RAM, 1 Repl publié.

## Option gratuite n°2 : Render (conteneur public)

1. **render.com** → **New → Blueprint** → collez `https://github.com/BrunoRakotomalala62/Agent`
   (le `render.yaml` est détecté automatiquement).
2. Saisissez les **secrets** dans le dashboard : `GEMINI_API_KEY`, `TERM_USER`, `TERM_PASS`.
3. Déployez → votre portail est en ligne (réveil ~30-60 s après un sommeil).

**Comportement gratuit** : Render endort le service après ~15 min sans visite et le
réveille à la prochaine requête. ⚠️ En gratuit : **pas de disque persistant** (les
fichiers créés par l'agent disparaissent au sommeil) et **un seul port** (portail,
pas de terminal web).

---

# ⚡ MODE 24/7 (toujours active)

## Option : Railway (~5 $/mois — jamais de sommeil, disque persistant, 2 ports)

1. Compte sur **railway.com** (connexion GitHub).
2. **New Project → Deploy from GitHub repo** → `BrunoRakotomalala62/Agent`
   (le `Dockerfile` est détecté).
3. Onglet **Variables** (secrets) :
   | Variable | Valeur |
   |---|---|
   | `GEMINI_API_KEY` | votre clé Google AI Studio |
   | `TERM_USER` | un nom d'utilisateur |
   | `TERM_PASS` | un mot de passe FORT |
4. Onglet **Volumes** → volume monté sur `/opt/agent-computer/machine` (votre disque).
5. Onglet **Settings → Public Networking** → domaines pour les ports **8125** (portail)
   et **7681** (terminal).
6. Déployez. Résultat :
   - `https://<app>.up.railway.app` → portail
   - `https://<app>-7681.up.railway.app` → terminal (mot de passe requis)

## Option : VPS (~4 €/mois — liberté totale)

```bash
sudo bash scripts/install.sh --with-opencode   # systemd + démarrage au boot
```

---

# ✅ Vérifications

- Portail : `GET /health` → `{"status":"ACTIVE", …}`
- Terminal : ouvre l'URL → demande `TERM_USER` / `TERM_PASS`
- Agent : dans le terminal, `opencode` (chat) ou `opencode run "consigne"`

# 🔐 Sécurité

- **Toujours** définir `TERM_USER` + `TERM_PASS` : sans eux, un terminal public = shell ouvert sur Internet.
- Les clés IA ne sont **jamais** dans le code : uniquement en variables d'environnement (secrets).
