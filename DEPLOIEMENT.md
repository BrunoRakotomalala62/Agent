# 🚀 Déploiement de l'Agent Computer (24/7 sur le cloud)

Le projet contient un `Dockerfile` : il peut tourner sur **Railway** (recommandé),
**Render**, ou n'importe quel hôte Docker / VPS.

> ⚠️ **Vercel et Netlify : impossible** pour cette machine (serverless : pas de
> processus permanent, pas de disque, pas de terminal).

## 🥇 Option recommandée : Railway (~5 $/mois, toujours actif + disque persistant)

1. Créez un compte sur **railway.com** (connexion GitHub).
2. **New Project → Deploy from GitHub repo** → choisissez `BrunoRakotomalala62/Agent`.
3. Railway détecte le `Dockerfile` automatiquement.
4. Onglet **Variables** → ajoutez (comme secrets) :
   | Variable | Valeur |
   |---|---|
   | `GEMINI_API_KEY` | votre clé Google AI Studio (cerveau de l'agent) |
   | `TERM_USER` | un nom d'utilisateur (ex. `admin`) |
   | `TERM_PASS` | un mot de passe FORT pour le terminal web |
5. Onglet **Volumes** → ajoutez un volume monté sur `/opt/agent-computer/machine`
   (le code survit aux redéploiements — c'est votre disque !).
6. Onglet **Settings** → *Public Networking* → générez les domaines pour les ports
   **8125** (portail) et **7681** (terminal).
7. Déployez. 🎉

Résultat :
- `https://<votre-app>.up.railway.app` → portail (état, fichiers)
- `https://<votre-app>-7681.up.railway.app` → terminal (protégé par mot de passe)

## Option Render (alternative)

1. **render.com** → New → **Web Service** → connecter le repo GitHub `Agent`.
2. Environnement : **Docker** (le Dockerfile est détecté).
3. Plan **payant** (le free s'endort après 15 min → contraire à « toujours actif »).
4. Ajoutez un **Disk** monté sur `/opt/agent-computer/machine`.
5. Variables identiques au tableau ci-dessus + port **8125**.
   (Render n'expose qu'UN port par service → le terminal 7681 demande un 2ᵉ Web
   Service avec `TTYD_PORT=7681`, ou utilisez Railway pour les deux.)

## VPS (alternative libre)

```bash
sudo bash scripts/install.sh --with-opencode   # systemd + démarrage au boot
```

## Vérifier que tout va bien

- Portail : `GET /health` → `{"status":"ACTIVE", ...}`
- Terminal : ouvre l'URL `…-7681…` → demande le mot de passe `TERM_USER`/`TERM_PASS`
- Agent : dans le terminal, tapez `opencode` (chat) ou `opencode run "consigne"`

## Sécurité

- **Toujours** définir `TERM_USER` + `TERM_PASS` : sans eux, le terminal est un shell
  ouvert sur Internet.
- Les clés IA (`GEMINI_API_KEY`) ne sont **jamais** dans le code : uniquement en
  variables d'environnement (secrets) de la plateforme.
