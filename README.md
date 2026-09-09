# 🖥️ Agent Computer — VOTRE machine virtuelle de codage IA, toujours active

Une machine à VOUS, indépendante des sandbox Tembo (qui s'endorment quand on ne
les utilise pas). Ici, **le code vit sur votre disque**, les services tournent en
permanence et **un watchdog les relance automatiquement** s'ils tombent.

```
┌──────────────────────────  Agent Computer  ──────────────────────────┐
│                                                                      │
│   🌐 Portail web (:8125)      statut machine, fichiers, journal      │
│   🖥️ Terminal web (:7681)     bash DANS machine/home/agent           │
│   📁 Dossier de travail       machine/home/agent  (= votre code)     │
│   🤖 Agent opencode           (optionnel) modifie le code, git push  │
│   🛡️ Watchdog                 contrôle tout / 15 s, relance les morts│
│                                                                      │
│   Le tout redémarre au boot (systemd) → ACTIF 24h/24, 7j/7           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 1. Démarrage rapide (sur votre ordinateur, pour essayer)

```bash
cd agent-computer
./scripts/start.sh          # portail :8125 · terminal :7681 · watchdog
./scripts/start.sh status   # voir l'état
./scripts/start.sh stop     # tout arrêter
```

Ouvrez ensuite :
- **http://localhost:8125** → tableau de bord (état, fichiers, journal)
- **http://localhost:7681** → le terminal de la machine (vous êtes dans `machine/home/agent`)

Test anti-panne : `kill $(cat var/ttyd.pid)` → regardez le terminal revenir seul ~15 s plus tard
(relancé par le watchdog, tracé dans `var/log/lifecycle.log`).

## 2. Déploiement 24/7 sur un vrai serveur (recommandé)

Une machine toujours allumée = un petit serveur (VPS à partir de ~4-5 €/mois —
Hetzner, DigitalOcean, Contabo…, ou un vieux PC chez vous).

```bash
# sur le serveur Ubuntu/Debian :
sudo bash scripts/install.sh --with-opencode
```

Résultat : 3 services **systemd** actifs, avec `Restart=always` et démarrage au boot :

```bash
sudo systemctl status agent-computer-portal agent-computer-ttyd agent-computer-watchdog
```

⚠️ **Sécurisez l'accès** (le terminal donne un vrai shell !) : pare-feu (`ufw allow 22,80,443`),
et idéalement un reverse-proxy nginx avec mot de passe devant les ports 8125/7681.

## 3. Rendre l'agent intelligent (le point important)

Le moteur d'agent **opencode** (le même que Tembo utilise en interne) est inclus.
Mais pour être **100 % indépendant de Tembo**, il faut brancher VOTRE propre clé de
modèle IA — l'API publique de Tembo ne permet pas d'appeler ses modèles depuis une
machine externe.

```bash
cp .env.example .env   # puis remplissez UNE clé :
#   GEMINI_API_KEY=...  → clé Google AI Studio (aistudio.google.com) — GRATUITE et testée ✅
#   OPENROUTER_API_KEY=... → 1 clé pour tous les modèles (Claude, GPT, DeepSeek…)
#   ou ANTHROPIC_API_KEY=... / OPENAI_API_KEY=...
```

✅ **Testé et validé (2026-09) : clé Google AI Studio + Gemini 3.6 Flash** → l'agent
opencode corrige des bugs réels dans `machine/home/agent` (édition de fichier + exécution
de vérification automatique). C'est la combinaison recommandée : gratuite et fiable.

Puis, dans le terminal web : tapez `opencode` (interface de chat) ou
`opencode run "corrige le bug dans le fichier X"` (commande unique) →
l'agent lit le code de la machine, le modifie, vous montrez la diff.

## 4. Brancher GitHub (stocker + pousser le code)

```bash
# 1) GitHub → Settings → Developer settings → Personal access tokens → créez un token (scope repo)
# 2) remplissez .env :  GITHUB_TOKEN=...  GIT_USER=...  GIT_EMAIL=...
# 3) clonez votre dépôt DANS la machine :
./scripts/git-setup.sh clone https://github.com/vous/votre-projet
# 4) après les modifications de l'agent :  git add -A && git commit -m "…" && git push
```

Le code est ainsi **stocké à deux endroits sûrs** : sur votre machine (disque) ET sur
GitHub (sauvegarde). Le token reste dans la machine (jamais dans le code).

## 5. Structure

```
agent-computer/
├── portal.py            portail web (statut, fichiers, journal) — stdlib Python
├── machine/home/agent/  ⬅ LE DISQUE : votre code, votre espace de travail
├── bin/ttyd             terminal web (binaire autonome)
├── scripts/
│   ├── start.sh         démarrer / arrêter / statut
│   ├── watchdog.sh      auto-réparation (toutes les 15 s)
│   ├── install.sh       installation serveur + systemd (24/7)
│   └── git-setup.sh     GitHub : token, identité, clone
├── systemd/             unités systemd (démarrage au boot)
└── var/log/             journaux (lifecycle.log, watchdog.log…)
```

## 6. Dépannage

| Problème | Solution |
|---|---|
| Un service est mort | attendre ≤ 15 s (watchdog) ou `./scripts/start.sh start` |
| Voir ce qui s'est passé | `tail -f var/log/lifecycle.log` et `var/log/watchdog.log` |
| Le portail répond mais pas le terminal | le watchdog le relance tout seul |
| opencode ne trouve pas la clé | vérifier `.env` puis relancer le terminal (`start.sh start`) |

---

*Construit pour fonctionner sans dépendre des machines Tembo : votre code, votre
disque, votre terminal, votre clé d'IA, vos heures de disponibilité.*
