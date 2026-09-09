# 🚀 Déploiement de l'Agent Computer

La machine a maintenant **UN SEUL PORT** : le site contient tout (tableau de bord +
**terminal intégré** + fichiers) → compatible même avec les plateformes à port unique.

Deux modes de vie :
- **🌙 Mode économique (0 €)** : la machine s'endort quand elle est inactive et se
  réveille seule quand le site est ouvert ou qu'une tâche démarre → **Replit ou Render gratuits**.
- **⚡ Mode 24/7** : toujours active → Railway (~5 $/mois) ou VPS (~4 €/mois).

> ⚠️ Vercel et Netlify : non (serverless : pas de processus long ni de terminal).

# 🌙 MODE ÉCONOMIQUE (gratuit)

```
ouverture du site  →  réveil (2-5 s)  →  agent code dans le terminal intégré
                                            ↓
                         inactivité ~5-15 min  →  veille (0 €)
```

## Option gratuite n°1 : Replit

1. **replit.com** → compte gratuit → **Create Repl → Import from GitHub**
   → `https://github.com/BrunoRakotomalala62/Agent` (Python).
2. Panneau **Secrets** (cadenas 🔒) → ajoutez : `GEMINI_API_KEY` (votre clé Google AI Studio).
3. Dans le **Shell**, une fois :
   ```bash
   pip install -q fastapi "uvicorn[standard]"
   npm install -g opencode-ai
   ```
4. Configuration du bouton **Run** de Replit :
   ```bash
   uvicorn webapp:app --host 0.0.0.0 --port 3000
   ```
5. L'aperçu web s'ouvre → onglet **💻 Terminal** → tapez `opencode` → l'agent code
   dans vos fichiers, SANS quitter le site.

**Gratuit** : dort après ~5 min d'inactivité, réveil en 3-5 s, fichiers conservés.

## Option gratuite n°2 : Render

1. **render.com** → **New → Blueprint** → collez l'URL du dépôt GitHub (`render.yaml` détecté).
2. Secrets dans le dashboard : `GEMINI_API_KEY`, `TERM_PASS` (mot de passe du terminal).
3. Déployez → **un seul domaine** : portail + terminal intégré (mot de passe requis).

**Gratuit** : dort après ~15 min, réveil à la prochaine visite (~30-60 s).
⚠️ En gratuit : pas de disque persistant (les fichiers créés par l'agent sont perdus au
sommeil ; les fichiers du dépôt, eux, sont relus à chaque réveil).

# ⚡ MODE 24/7

## Railway (~5 $/mois — jamais de sommeil, disque persistant)

1. **railway.com** → **New Project → Deploy from GitHub repo** → `BrunoRakotomalala62/Agent`.
2. **Variables** : `GEMINI_API_KEY`, `TERM_PASS`.
3. **Volumes** : volume monté sur `/opt/agent-computer/machine` (votre disque).
4. **Settings → Public Networking** → domaine pour le port **8125** (un seul suffit,
   le terminal est dans la page).
5. Déployez → `https://<app>.up.railway.app` : portail + terminal + agent.

## VPS (~4 €/mois)

```bash
sudo bash scripts/install.sh --with-opencode   # systemd + démarrage au boot
# variante tout-en-un : sudo python3 -m pip install fastapi "uvicorn[standard]"
# puis : uvicorn webapp:app --host 0.0.0.0 --port 8125
```

# ✅ Vérifications & 🔐 Sécurité

- Portail : `/health` → `{"status":"ACTIVE", ...}`
- Terminal : onglet 💻 Terminal — demande `TERM_PASS` s'il est défini
- **Toujours** définir `TERM_PASS` sur un déploiement public (sinon n'importe qui
  ayant l'URL obtient un shell sur la machine)
- Les clés IA (`GEMINI_API_KEY`) : uniquement en secrets de plateforme, jamais dans le code.
