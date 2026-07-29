# mc-iclone8-mcp v0.1.3

## Corrections de la revue de code

- `camera.set_camera` utilise maintenant le helper partagé `current_time()`.
- `follow_path`, `release_path`, `set_path_position` et `set_path_offset` utilisent maintenant `current_frame()`.
- Les dimensions des lumières rectangulaires utilisent désormais `require_success` pour standardiser les erreurs.
- `diagnostics._call` ne masque plus les exceptions inattendues ; seules les erreurs d’accès API absente ou invalide utilisent la valeur par défaut.
- Le cas sans lumière renvoie déjà une `ValueError` explicite au lieu d’une erreur d’attribut ultérieure.

## Vérification

- Compilation Python réussie.
- Les 4 tests unitaires MCP passent.
- Les fichiers corrigés ont été copiés dans le dossier du plugin iClone 8.
- Aucun appel à iClone 7 n’a été introduit.

Les opérations iClone expérimentales doivent toujours être validées avec des
assets compatibles dans la version iClone 8 installée.
