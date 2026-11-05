# PILOT — Sauvegarde et restauration

Ce document répond au CDC §19 : il dit **quoi** est sauvegardé, **comment**, **qui** en est
responsable, **combien de temps** les sauvegardes sont gardées, et **comment restaurer** sans
perdre les mises à jour faites depuis.

## 1. Ce qu'il faut protéger

| Élément | Où il vit | Sauvegardé par |
|---|---|---|
| Comptes, espaces, projets, tâches, propositions, alertes | Base Neon (PostgreSQL) | Historique Neon + branches de sauvegarde |
| Contenu des fichiers (documents, sources de mise à jour) | Base Neon, table `stored_files` (décision D2) | Les mêmes : les fichiers sont dans la base |
| Photographie d'un espace (données + fichiers vérifiables) | Fichier ZIP téléchargé | Export depuis **Paramètres > Sauvegarde et export** |
| Code de l'application | GitHub `gedeon92/PILOT` | Git (chaque version est conservée) |
| Secrets (clé Brevo, `DATABASE_URL`, `CRON_SECRET`) | Render, GitHub, `backend/.env` | **Jamais dans une sauvegarde** ; les recréer si besoin |

Comme les fichiers sont stockés dans la base, une sauvegarde de la base contient aussi les
fichiers : le lien entre une fiche et son contenu ne peut pas se perdre. Chaque pièce garde son
empreinte SHA-256, et l'import d'un export la vérifie.

## 2. Les trois niveaux de sauvegarde

### Niveau 1 : retour arrière immédiat (Neon, automatique)
- Neon garde l'historique de toutes les modifications. Sur l'offre gratuite, cet historique
  couvre **6 heures** (réglage *Settings > Instant restore*). Les offres payantes vont jusqu'à
  7 ou 30 jours.
- Il sert à réparer une erreur récente (suppression accidentelle, mauvaise manipulation).

### Niveau 2 : branche de sauvegarde (Neon, manuelle)
- Une branche Neon est une **copie complète** de la base à un instant donné. Elle ne disparaît
  pas au bout de 6 heures.
- **Quand en créer une :** avant chaque mise en production, avant une migration importante et,
  en production, **une fois par semaine** (le lundi matin).
- **Comment :** console Neon > projet PILOT > *Branches* > *Create branch*. Branche parente :
  `production` (ou `staging`). Nom : `sauvegarde-AAAA-MM-JJ`.
- **Conservation :** garder les 4 dernières (un mois), puis supprimer la plus ancienne.
  L'offre gratuite limite le nombre de branches : `production`, `dev`, `staging` et
  4 sauvegardes tiennent dans cette limite.

### Niveau 3 : export de l'espace (PILOT, manuel)
- **Paramètres > Sauvegarde et export > Télécharger l'export complet** (rôle Propriétaire).
- Le ZIP contient `pilot-export.json` (structure, projets, tâches, événements, catalogue des
  pièces) et le dossier `fichiers/`. Il ne contient jamais de mot de passe, de session, de lien
  d'invitation ni de demande de mise à jour privée.
- **Quand :** une fois par mois, et avant toute opération risquée sur un espace.
- **Où le ranger :** dans un dossier privé (OneDrive, Google Drive…) accessible à la seule
  propriétaire. Ce fichier contient des données de l'organisation : ne pas l'envoyer par
  e-mail et ne jamais le déposer dans le dépôt GitHub (il est public).
- **Conservation :** 12 mois.

## 3. Responsabilités

| Rôle | Responsabilité |
|---|---|
| Propriétaire de chaque espace | Télécharge l'export mensuel de son espace et le range en lieu sûr |
| Administrateur technique (titulaire du compte Neon) | Crée les branches de sauvegarde hebdomadaires, supprime les anciennes, réalise les tests de restauration |
| Propriétaire du produit | **Autorise** toute restauration en production (décision écrite : date, motif, point de restauration choisi) |

Seul le titulaire du compte Neon peut accéder aux branches. Les exports ne sont accessibles
qu'aux personnes à qui la propriétaire les confie.

## 4. Restaurer sans perdre les mises à jour récentes

Règle du CDC : une restauration ne doit pas effacer, sans décision explicite, ce qui a été
saisi depuis le point de sauvegarde. On ne remplace donc **jamais** directement la base de
production. On procède ainsi :

1. **Créer une branche de contrôle** à partir du point voulu : Neon > *Branches* >
   *Create branch* > *Past data* (date et heure, dans les 6 dernières heures), ou à partir d'une
   branche `sauvegarde-…`.
2. **Comparer** : relier temporairement une copie de l'application à cette branche (ou
   l'ouvrir dans le *SQL Editor* de Neon) et vérifier ce qui manque ou ce qui est erroné.
3. **Décider** avec la propriétaire du produit :
   - *Erreur limitée à un espace* : exporter l'espace depuis la branche de contrôle, puis
     l'importer dans PILOT. L'import crée un **nouvel espace**, à côté de l'actuel, et ne touche
     à rien d'autre. Les données sont ensuite reprises à la main ou par la boîte de mise à jour.
   - *Erreur générale* (base abîmée) : utiliser *Restore* sur la branche `production` vers le
     point choisi. Neon garde automatiquement l'état d'avant sous la forme d'une branche
     `production_old_…`, ce qui permet de récupérer ensuite les saisies récentes.
4. **Noter** dans le journal d'exploitation : date, motif, point restauré, personne qui a
   autorisé, éléments repris à la main.

## 5. Tester la restauration (au moins une fois par trimestre)

Test à faire sur la branche `staging`, jamais sur `production` :

1. Dans PILOT (version de test), noter un projet et sa valeur (par exemple *barometre*, avancement 20 %).
2. Le modifier (avancement 60 %) et noter l'heure exacte.
3. Dans Neon : *Branches* > *Create branch* > parente `staging` > *Past data* > une heure
   **avant** la modification. Nom : `test-restauration-AAAA-MM-JJ`.
4. Ouvrir le *SQL Editor* sur cette branche et lancer :
   `select title, progress, updated_at from projects where title = 'barometre';`
   Résultat attendu : 20 %, l'ancienne valeur.
5. Faire aussi le test de l'export : **Paramètres > Télécharger l'export complet**, puis
   **Importer un export**. Vérifier dans le nouvel espace les projets, les tâches et que chaque
   pièce s'ouvre (EXP01).
6. Supprimer la branche `test-restauration-…` et l'espace importé, puis noter le résultat
   ci-dessous.

### Journal des tests de restauration

| Date | Branche | Test | Résultat | Par |
|---|---|---|---|---|
| | `staging` | Historique Neon + export/import | à faire | |
