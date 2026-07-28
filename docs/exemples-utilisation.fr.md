# Exemples d’utilisation du MCP iClone 8

Chaque prompt demande à l’agent d’inspecter la scène avant modification. Utiliser les noms exacts retournés par `list_objects` ; `Preview Camera` ne doit pas être utilisée pour une animation de transformation.

## Diagnostic et inspection

Prérequis : iClone 8 est ouvert, le plugin est chargé et le serveur affiche `http://127.0.0.1:8766/mcp`.

Prompt :

> Vérifie la connexion MCP et la version de l’API iClone 8. Liste ensuite les caméras, props, avatars, lumières et paths sans modifier la scène.

## Primitives et mise en place

Prérequis : un projet ouvert ; choisir une zone libre ou fournir explicitement l’origine et les unités.

Prompt :

> Inspecte d’abord la scène. Crée un cube nommé `Test_Box` en `(0, 0, 50)`, à l’échelle `(100, 100, 100)`, crée un sol dessous puis vérifie les noms, bornes et transformations. Ne supprime aucun objet existant.

## Matériaux et textures

Prérequis : l’objet cible existe, `get_materials` permet d’identifier l’index du matériau et les textures sont des fichiers locaux.

Prompt :

> Trouve le prop exact `Test_Box`, liste ses matériaux, mets la couleur diffuse du matériau 0 en rouge `(1, 0, 0)`, conserve la texture sauf si elle empêche la couleur d’être visible, puis relis le matériau pour vérifier.

## Lumières

Prérequis : une lumière compatible existe ; fournir son nom exact et ne pas modifier les autres lumières.

Prompt :

> Liste les lumières et inspecte `Key_Light`. Augmente son intensité à 2.0, applique une couleur chaude, active les ombres et vérifie les propriétés finales. Ne crée pas de nouvelle lumière.

## Caméras et tournage

Prérequis : une vraie caméra de scène comme `Camera1`, le sujet et la plage d’images sont connus.

Prompt :

> Inspecte `Camera1` et `Orbit_Sphere`. Anime la caméra aux frames 0, 300 et 600 avec un décalage relatif régulier, oriente-la vers la sphère à chaque clé, active `Camera1` et vérifie les clés. N’utilise pas `Preview Camera`.

## Animation et paths

Prérequis : l’objet existe ; un path iClone doit déjà exister, car l’API Python publique ne permet pas de créer ou modifier fiablement les points de courbe.

Prompt :

> Supprime d’abord uniquement l’animation de transformation de `Orbit_Sphere` en conservant sa position actuelle. Inspecte ensuite les paths existants, fais suivre à la sphère le path `Orbit_Path` de la frame 0 à 600 et vérifie les transformations aux frames 0, 300 et 600.

## Avatars, expressions et voix

Prérequis : un avatar compatible existe ; pour la voix, fournir un chemin local WAV/MP3. Pour le corps, préférer les motions natives.

Prompt :

> Inspecte l’avatar `Eddy` pour confirmer la présence des composants visage et visèmes. Conserve son point d’ancrage, active le clignement automatique, applique une séquence d’expression neutre-vers-sourire de 0 à 120 et signale toute opération faciale non supportée au lieu d’inventer un résultat.

## Import, export et sauvegarde

Prérequis : les fichiers sources existent et le dossier de destination existe déjà. Les exports sont expérimentaux dans l’API officielle.

Prompt :

> Vérifie l’existence de `C:\\Assets\\chair.iProp`, importe-le, retourne le nom et les bornes du nouvel objet, sauvegarde le projet dans `C:\\Projects\\shot.iProject`, puis exporte l’objet en FBX vers `C:\\Exports\\chair.fbx`. Ne remplace aucun fichier sans confirmation.

## Rendu

Prérequis : une vraie caméra active, un projet configuré, un chemin de sortie explicite. Le rendu crée un fichier externe et demande confirmation.

Prompt :

> Lis les réglages de rendu et la caméra active, indique la plage d’images et la résolution, puis attends ma confirmation avant de rendre vers `C:\\Renders\\shot.mp4`.

## Limites importantes

- Le plugin cible exclusivement iClone 8 ; aucune API des motion bones d’iClone 7 n’est utilisée.
- La création de paths et l’édition de leurs points de courbe ne sont pas exposées de manière fiable par l’API Python publique.
- OBJ, GLB, Alembic, visage/visèmes et plusieurs opérations de lumières/matériaux sont expérimentaux et doivent être vérifiés dans la version installée.
- L’édition directe des sommets/arêtes/faces, l’attachement parent arbitraire et la création native de contraintes physiques/path ne sont pas exposés comme opérations publiques fiables.
