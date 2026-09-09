# 📜 Règles permanentes de l'agent (AGENTS.md)

Tu es un agent de codage qui travaille sur une machine dont le disque peut être
**éphémère** (elle s'endort / redémarre). Ta mission inclut donc la SAUVEGARDE.

## Règle d'or : pousser après CHAQUE modification

Après avoir terminé une modification de fichier (ou une série de modifications
liées à une même tâche), **sauvegarde immédiatement sur GitHub** :

```bash
git add -A
git commit -m "Description claire et courte de ce que tu as fait"
git push origin HEAD
```

- Vérifie que le push a réussi (la sortie doit l'indiquer).
- Si tu n'as rien modifié, ne pousse pas.
- Si la commande git échoue, explique l'erreur et réessaie une fois
  (ex. : `git pull --rebase origin main` puis re-push).
- Rédige les messages de commit en français, précis et utiles.

## Pourquoi

Le disque de travail peut être effacé à tout moment (veille / redémarrage).
GitHub est la mémoire durable : chaque modification poussée est sauvegardée.
À chaque réveil, la machine récupère la dernière version depuis GitHub —
rien n'est perdu.
