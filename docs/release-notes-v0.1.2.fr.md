# mc-iclone8-mcp v0.1.2

## Validation

- `ping_iclone` et `get_api_version` validés avec iClone 8 RLPy.
- 95 outils MCP exposés après redémarrage du plugin.
- Inventaire non destructif réussi pour avatars, props, caméras, lumières et paths.
- Scène installée vérifiée : Eddy, Shadow Catcher, Preview Camera, quatre lumières et aucun path.
- Eddy ne fournit actuellement aucun morph.
- Preview Camera lisible mais non animable par transformation ; une caméra de scène réelle est nécessaire pour l’animation caméra.

## Corrections et ajouts

- Correction de `list_objects` pour les builds iClone qui renvoient des listes imbriquées avec `FindObjects`.
- Validation des sources audio et ajout de pistes audio aux props/avatars.
- Sauvegarde spécialisée iAvatar, iProp, motion, iTalk et iMotionPlus.
- Export USD expérimental avec options documentées.
- Clés de poids de morphs et suppression contrôlée des clés.
- Création et suppression expérimentales de clips visèmes.
- Guides français/anglais et skill expert iClone 8 mis à jour.

## Limitations connues

L’audio, les sauvegardes spécialisées, les exports USD/GLB/OBJ/Alembic, les
morphs et l’édition des clips visèmes restent expérimentaux et doivent être
testés avec des assets compatibles dans la version iClone installée. Les paths
existants peuvent être contrôlés, mais l’API Python publique ne fournit pas de
création fiable des paths ni d’édition de leurs points de courbe.
