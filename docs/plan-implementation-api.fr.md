# Plan d’implémentation des capacités iClone 8

Ce plan suit les modules et limites documentés dans le wiki officiel
Reallusion. Chaque lot doit être compilé, testé sans modification, puis vérifié
dans iClone avant publication.

## Phase 1 — capacités fiables et utiles

- [x] Normaliser les réponses MCP et factoriser les validations communes.
- [x] Ajouter l’audio sur props et avatars avec WAV/MP3, boucles, fondus et découpe (runtime à vérifier).
- [x] Ajouter la sauvegarde spécialisée iAvatar, iProp, rlMotion, iTalk et iMotionPlus (runtime à vérifier).
- [ ] Vérifier les options de sauvegarde faciale et motion plus dans la build iClone installée.

## Checkpoint 1

- Compilation Python et tests MCP réussis.
- Test non destructif dans iClone.
- Test audio sur un avatar ou prop de test.
- Test de sauvegarde vers un nouveau fichier, sans écrasement.

## Phase 2 — fichiers et animation avancés

- [x] Ajouter un premier export USD avec les options documentées (runtime à vérifier).
- [x] Ajouter la lecture, l’animation et la suppression contrôlée des clés de morphs (runtime à vérifier).
- [ ] Compléter les options d’export GLB et FBX.
- [ ] Ajouter les options avancées de clips de motion.
- [ ] Ajouter les opérations documentées de gestion de visèmes et de clips faciaux.

## Phase 3 — intégration iClone

- [ ] Ajouter les événements et callbacks de scène avec arrêt propre du plugin.
- [ ] Ajouter la lecture/écriture audio avancée et l’enregistreur si l’API est disponible.
- [ ] Ajouter le diagnostic et le contrôle mocap body/hand/facial.
- [ ] Ajouter les clients TCP/UDP uniquement avec une configuration locale explicite.

## Phase 4 — couverture spécialisée

- [ ] Inspecter et ajouter les capacités RParticle/PopcornFX, sky et visual settings lorsque les classes sont disponibles.
- [ ] Ajouter les outils UI uniquement si une interaction MCP stable est utile.
- [ ] Documenter les opérations officiellement inopérables : mesh, contraintes, physique, Preview Camera, paramètres de rendu et lip-sync complet.

## Règles de validation

- Une API absente de la build iClone doit retourner une erreur explicite et stable.
- Les types RLPy doivent être convertis en types JSON simples.
- Les opérations destructives ou écrivant des fichiers demandent une confirmation ou refusent l’écrasement par défaut.
- Les opérations expérimentales sont marquées dans la description et testées séparément.
