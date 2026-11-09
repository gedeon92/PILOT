# PILOT — Workflow de développement

Référence fonctionnelle : `PILOT_Cahier_complet_de_conception_et_workflows.docx` (cité « CDC §n »).
PILOT est ouvert à tous : chaque personne inscrite crée son espace et en devient propriétaire. Rien n'est codé en dur pour une organisation particulière.

## Stack

| Couche | Choix |
|---|---|
| Backend | Python 3.12 + FastAPI (API JSON sous `/api`) |
| Frontend | TypeScript + React + Vite, React Router, TanStack Query |
| Contrat front/back | Schéma OpenAPI généré par FastAPI → types TypeScript générés automatiquement (`openapi-typescript`) |
| Base de données | Neon (PostgreSQL) via SQLAlchemy 2 et psycopg |
| Migrations | Alembic |
| Hébergement frontend | Vercel (offre gratuite Hobby). `vercel.json` redirige `/api/*` vers l'API Render : le navigateur ne voit qu'un seul domaine, donc cookies de session simples et pas de CORS. |
| Hébergement API | Render, Web Service (offre gratuite pendant les tests ; Cron Job plus tard pour les notifications) |
| Tests | Backend : pytest + base Neon dédiée (branche Neon). Frontend : Vitest + Testing Library ; parcours de bout en bout : Playwright |
| Extraction de documents | Bibliothèques Python locales : pypdf, python-docx, openpyxl, python-pptx (aucun service externe) |

## Organisation du dépôt

```
PILOT/
├── backend/    # FastAPI, modèles, migrations, moteur de propositions
├── frontend/   # React + TypeScript
└── WORKFLOW.md
```

Chaque phase livre les deux côtés : l'API (avec ses contrôles de droits et ses tests) d'abord, puis les écrans qui l'utilisent.

## Règles de travail (valables à chaque phase)

1. Une phase commence seulement quand la précédente est validée.
2. Chaque fonctionnalité = comportement observable + données + acteur autorisé + test d'acceptation (CDC §2).
3. Les droits sont contrôlés côté serveur, jamais seulement en masquant un bouton.
4. Toute modification de structure passe par une migration Alembic. Aucun script de réinitialisation ne tourne en production.
5. Chaque phase se termine par : tests verts → déploiement sur l'environnement de test Render → vérification par la propriétaire du produit → passage en production.
6. Ne jamais présenter comme disponible une fonction non construite et vérifiée.

## Environnements

Phase de test : tout tourne sur les offres gratuites.

| Environnement | Base Neon | API (Render) | Frontend (Vercel) |
|---|---|---|---|
| Local | branche `dev` | `localhost:8000` | `localhost:5173` (proxy Vite vers l'API) |
| Tests automatiques | branche `test` (vidée à chaque exécution) | — | — |
| Recette | branche `staging` | `pilot-api-staging` | déploiements de prévisualisation Vercel |
| Production (plus tard) | branche `production` | `pilot-api` | domaine de production Vercel |

Limites connues des offres gratuites, acceptées pour la phase de test :
- Render gratuit met l'API en veille après environ 15 minutes sans visite ; le premier appel suivant prend 30 à 60 secondes. Le frontend doit afficher un état « démarrage du serveur ».
- Render gratuit ne garde pas les fichiers écrits sur disque entre deux déploiements (voir D2).
- Vercel Hobby est réservé à un usage non commercial : passer à l'offre Pro avant une ouverture publique payante.
- Neon gratuit : 1 Go de stockage, 10 branches par projet, mise en veille de la base quand elle est inactive (constaté le 3 nov. 2026). Région retenue : Europe (Frankfurt), comme l'API Render.

---

## Phase 0 — Préparation

- [x] Dépôt git local avec `backend/` et `frontend/`
- [x] Dépôt GitHub créé et code poussé (https://github.com/gedeon92/PILOT, CI verte)
- [x] Backend : `pyproject.toml` (uv), ruff, application FastAPI minimale avec route `/api/health` (vérifie la base), tests pytest
- [x] Frontend : Vite + React + TypeScript, oxlint, Prettier, Vitest ; page d'état qui appelle `/api/health` et gère le réveil de Render
- [x] Génération des types TypeScript depuis l'OpenAPI du backend (`npm run gen:api`)
- [x] Projet Neon `PILOT` créé (Frankfurt, PostgreSQL 18), connexion vérifiée depuis l'API
- [x] Branches Neon créées dès maintenant (décision du 3 nov. 2026) : `dev` (ordinateur), `staging` (Render), sans suppression automatique ; la branche d'origine `production` est réservée à la production
- [x] Variables d'environnement documentées dans `backend/.env.example`, `.env` exclu de git
- [x] `render.yaml` prêt (service `pilot-api-staging`, offre gratuite)
- [x] Service Render créé depuis le `render.yaml` (Blueprint « PILOT »), `DATABASE_URL` = branche Neon `staging` ; https://pilot-api-staging.onrender.com/api/health répond « database: ok »
- [x] `vercel.json` prêt (redirection `/api/*` vers Render)
- [x] Projet Vercel `pilot` créé (offre Hobby), relié au dossier `frontend/` : https://pilot-beta-swart.vercel.app
- [x] CI GitHub Actions : lint, tests et build backend + frontend, contrôle des types générés ; Render ne déploie que si la CI passe

**Terminé quand :** la page en ligne sur Vercel affiche l'état de l'API Render, et l'API est connectée à Neon.

✅ **Phase 0 terminée le 3 nov. 2026** : la page Vercel joint l'API Render (`/api/health` → `database: ok`).

## Phase 1 — Comptes, espaces et droits (CDC §4, §15)

- [x] Modèle : `User`, `AuthSession`, `Space`, `Membership` (rôle : lecteur / contributeur / propriétaire ; statut : invité / actif), `AuditLog` ; première migration Alembic, appliquée automatiquement au démarrage sur Render
- [x] Inscription, connexion, déconnexion ; mots de passe hachés (Argon2) ; session serveur dans un cookie HttpOnly, SameSite=Lax, Secure en ligne ; protection CSRF par en-tête obligatoire sur toute écriture
- [x] Création d'un espace → son créateur devient propriétaire ; fuseau horaire choisi à la création
- [x] Invitation par lien à usage unique (14 jours), valable seulement pour le compte de l'adresse invitée ; nouveau lien ; changement de rôle avec contrôle de version ; retrait
- [x] Dépendance serveur qui relit l'espace et le rôle en base à chaque requête (un retrait s'applique à la requête suivante)
- [x] Isolation stricte entre espaces (réponse 404 pour un non-membre)
- [x] Journal des actions sensibles (inscription, espace, invitations, rôles, retraits)
- [x] Écrans : connexion, inscription, création d'espace, vue d'ensemble, accès et membres, acceptation d'invitation
- [x] Tests : 29 côté API (base PostgreSQL réelle, schéma temporaire), 7 côté interface
- [x] « Mon compte » (ajout du 4 nov. 2026) : nom affiché, mot de passe (ferme les autres sessions), changement d'adresse e-mail confirmé par un lien envoyé à la nouvelle adresse (Brevo), valable 24 h et seulement pour le compte demandeur

**Terminé quand :** ACC01, ACC02, ACC03 passent, et un utilisateur d'un espace A ne peut lire aucune donnée de l'espace B, même en forgeant la requête.

✅ **Phase 1 terminée le 3 nov. 2026** (tests `test_reader_cannot_write_through_the_api`, `test_contributor_cannot_manage_access`, `test_revoking_contribution_applies_on_next_request`, `test_spaces_are_isolated`).

## Phase 2 — Structure de l'espace (CDC §5)

- [x] Modèles : `Portfolio` (nom, description, couleur), `Entity` (filiale, pays), `ProjectType` ; nom unique par espace sans tenir compte des majuscules
- [x] Types de projets proposés par défaut : Événement, Produit, Mission, Autre (ajoutés aussi aux espaces existants par la migration)
- [x] Page « Paramètres et structure » : nom et fuseau de l'espace, portefeuilles, filiales, types ; créer, modifier, archiver, restaurer ; affichage des éléments archivés
- [x] Pas de suppression : un élément archivé n'est plus proposé mais garde ses projets
- [x] Portefeuilles affichés dans le menu latéral avec leur couleur
- [x] Identifiants stables indépendants des noms ; contrôle de version sur chaque modification ; journal des créations, modifications, archivages
- [ ] Langue de l'espace : français seulement pour l'instant

**Terminé quand :** renommer un portefeuille ou une entité ne casse aucun lien, et un contributeur reçoit un refus serveur sur ces écrans.

✅ **Phase 2 terminée le 3 nov. 2026** (tests `test_rename_keeps_the_same_identifier`, `test_only_owner_changes_the_structure`, `test_structure_is_isolated_between_spaces`).

## Phase 3 — Projets et tâches (CDC §6, §8, §21, §22)

- [x] Nature des types de projets : « standard » ou « événement » (le comportement dépend de la nature, pas du nom du type)
- [x] Modèle `Project` selon le dictionnaire CDC §21 : situation, prochaine étape et décision attendue séparées ; avancement facultatif (vide si inconnu) ; dates exactes, période à préciser et certitude ; vigilance ; lieu ; lien externe
- [x] Modèle `Task` : livrable, responsable, statut, échéance proposée ou confirmée, retard calculé dans le fuseau de l'espace
- [x] Statuts : À cadrer, À lancer, En préparation, En cours, En attente de validation, Bloqué, Suspendu, Terminé, Annulé
- [x] Règles de transition : Terminé exige un bilan ; Annulé exige un motif et annule les tâches ouvertes (les tâches terminées restent) ; réouverture journalisée
- [x] Attribution du suivi : un membre de l'espace ou un nom libre (« Mon assistante »), sans création de compte, signalé « sans compte »
- [x] Champ `version` + détection de conflit ; la saisie est conservée et la version actuelle peut être rechargée
- [x] Journal avant/après et historique lisible par projet
- [x] « Réessayer » sans doublon (identifiant de requête envoyé par le formulaire)
- [x] Écrans : liste filtrable (recherche, portefeuille, statut), création rapide, fiche projet complète, tâches ; vue d'ensemble alimentée par les vrais projets (retards, blocages, échéances à 7 jours, timeline, « À faire aujourd'hui »)

**Terminé quand :** PRJ01, PRJ02, PRJ03 passent.

✅ **Phase 3 terminée le 3 nov. 2026** (API : 17 tests dont PRJ01-03 ; interface : création avec nom libre, bilan obligatoire, conflit sans perte de saisie).

## Phase 3B — Événements (CDC §6, §12, §21)

Demande du 3 nov. 2026 : suivre l'organisation des événements, les voir dans un calendrier, gérer les éditions récurrentes. Un événement est un projet dont le type a la nature « événement » : il garde tâches, responsable, documents et alertes, et reçoit en plus des détails propres, stockés à part pour ne pas les imposer aux autres projets. Hors périmètre : inscriptions et gestion des participants.

- [x] Modèle `EventDetails` (1 pour 1 avec le projet) : lieu, public visé, participants attendus, programme, édition ; les jours de l'événement sont les dates du projet, avec leur certitude (proposée, annoncée, confirmée), distincte du statut opérationnel
- [x] Les détails ne s'affichent que pour un type de nature « événement » ; ils sont conservés si le type change, et refusés (422) sur un projet standard
- [x] Modèle `Program` : un événement récurrent et ses éditions ; géré dans Paramètres comme les portefeuilles (archivable, jamais supprimé)
- [x] Suivi après l'événement jusqu'à J+15 : date calculée, rappel « Suivi J+15 » puis « Bilan » dans la vue d'ensemble, uniquement pour les événements
- [x] Annulation d'une édition : statut Annulé avec motif, tâches ouvertes annulées, dates et dossier conservés ; l'édition sort du calendrier actif
- [x] Replanification : changement de dates journalisé (avant / après) ; aucune réactivation automatique
- [x] Vue « Événements » : filtres programme, portefeuille, filiale, pays ; calendrier mensuel ; périodes à préciser à part (elles ne valent pas durée) ; événements sans date listés sans date inventée
- [x] Alerte de chevauchement avec sa règle affichée : au moins un jour commun entre deux événements non annulés

**Terminé quand :** CAL01 et CAL02 passent pour les événements ; une édition annulée disparaît du calendrier actif mais son dossier reste consultable ; un projet standard n'affiche aucun champ d'événement.

✅ **Phase 3B terminée le 3 nov. 2026** (API : 8 tests événements + programmes ; interface : règles de chevauchement, CAL01, CAL02).

## Phase 4 — Documents du projet (CDC §11)

- [x] Modèle `Document` (nom, format, taille, empreinte SHA-256, clé technique indépendante du nom, projet, auteur, date)
- [x] Téléversement et téléchargement avec contrôle des droits : tous les membres téléchargent ; contributeurs et propriétaire ajoutent et retirent
- [x] Limites de la phase de test : 3 fichiers par envoi, 4 Mo par fichier (réglage `MAX_UPLOAD_MB`) ; refus clair au-delà, vérifié aussi avant l'envoi
- [x] Sécurité : fichier toujours servi en pièce jointe (`nosniff`, jamais affiché dans la page) ; le nom n'est qu'un libellé nettoyé
- [x] Retrait sans suppression définitive, journalisé dans l'historique du projet
- [x] Page « Documents » : toutes les pièces de l'espace, recherche par nom
- [x] Stockage des fichiers : décision D2 appliquée (PostgreSQL/Neon derrière l'interface `FileStorage`)
- [x] Séparation dossier partagé / sources privées : les fichiers déposés dans la boîte de mise à jour restent des sources (privées par défaut) et n'entrent dans le dossier d'un projet que sur décision explicite (« Ajouter au dossier d'un projet »)
- [x] Remplacement d'un document avec conservation de la version précédente (bouton « Remplacer », versions précédentes téléchargeables, liens gardés à l'export et à l'import)

**Terminé quand :** DOC01 passe, et un fichier reste disponible depuis un autre appareil.

✅ **Phase 4 terminée le 3 nov. 2026** (tests `test_upload_then_download_returns_the_same_file`, `test_file_is_available_from_another_device`).

## Phase 5 — Tableau de bord, recherche et filtres (CDC §7, §13)

- [x] Tableau de bord : retards, blocages, vigilance élevée, échéances à 7 jours, décisions en attente, suivi J+15, projets sans responsable ou sans prochaine étape ; tient dans la hauteur de l'écran sur ordinateur (demande du 4 nov. 2026)
- [x] Règle de priorité écrite et affichable (« Comment c'est calculé ? »), règles partagées dans `attention.ts`
- [x] Chaque carte de chiffre ouvre la liste filtrée correspondante (`/projets?attention=…`)
- [x] Liste et timeline des projets : titre, portefeuille, filiale, statut, responsable, prochaine étape, échéance
- [x] Recherche globale ⌘K / Ctrl+K (projets, documents, pages ; sans tenir compte des accents ; clavier : flèches, Entrée, Échap)
- [x] Filtres : recherche, signal d'attention, portefeuille, filiale, pays, statut, période ; gardés dans l'adresse (partage, favoris)
- [x] Identité visuelle : remplacée par la charte D7 (Plus Jakarta Sans, orange) ; états chargement, vide, erreur, accès refusé, conflit présents sur les écrans
- [x] Responsive (menu replié sur téléphone, vue d'ensemble défilante sur petit écran) et accessibilité clavier (lien « Aller au contenu », focus visible, infobulles au clavier)

**Terminé quand :** on passe d'un signal d'attention à la fiche, à la source, puis à la prochaine action en quelques clics, sur ordinateur comme sur téléphone.

✅ **Phase 5 terminée le 4 nov. 2026** (tests : recherche ⌘K, filtres lus dans l'adresse, cartes vers listes filtrées).

## Phase 6 — Timeline et calendrier (CDC §12)

- [x] Trois natures de dates : exacte, période, inconnue (période en pointillés, projets sans date comptés à part)
- [x] Statut de calendrier distinct du statut opérationnel (certitude de la date)
- [x] Timeline « vivante » (4 nov. 2026, à la demande de l'utilisateur) : regroupement par portefeuille, dates sur les barres, échéance en losange (rouge et pulsée si dépassée), tâches en points, infobulle détaillée au survol ou au clavier, zoom mois / trimestre / semestre, navigation, ligne « Aujourd'hui », week-ends et semaines en vue mois, animation d'ouverture (désactivée si l'utilisateur réduit les animations)
- [x] Page « Timeline » : filtres portefeuille, filiale, nature (projets / événements), projets terminés ; version compacte sur la vue d'ensemble
- [x] Liste des projets sans date (sous la timeline ; le compteur « N sans date » y mène)
- [x] Fuseau horaire de l'espace
- [x] Annulation : retrait du calendrier actif, dossier et anciennes dates conservés

**Terminé quand :** CAL01 et CAL02 passent.

✅ **Phase 6 terminée le 6 nov. 2026.**

## Phase 7 — Alertes et rappels (CDC §16, §19)

Objectif : aider chaque utilisateur à tenir ses délais. Une alerte invite à vérifier une situation ; elle ne déclare jamais un projet en échec.

Règles d'alerte (seuils réglables par espace) :

| Règle | Déclencheur par défaut | Destinataires |
|---|---|---|
| Échéance proche | J-7, J-3, J-1 et jour J (projet, tâche, jalon) | Responsable du suivi + responsable de la tâche |
| En retard | Échéance dépassée et statut non clôturé | Responsable + propriétaire de l'espace |
| Bloqué | Passage au statut Bloqué | Responsable + propriétaire |
| Décision en attente | Décision attendue sans réponse depuis 7 jours | Décideur indiqué, sinon propriétaire |
| Suivi non actualisé | Projet actif sans mise à jour depuis 14 jours | Responsable |
| Information manquante | Projet actif sans responsable ou sans prochaine étape | Propriétaire |
| Proposition à valider | Proposition en attente depuis 2 jours | Auteur de la proposition |

- [x] Modèles `Alert` et `AlertPreference` (par utilisateur et par espace : règles actives, récapitulatif oui/non, heure)
- [x] Calcul des alertes dans le fuseau de l'espace, sans doublon (contrainte unique : personne, règle, objet, jour) ; recalcul à l'ouverture de la page et chaque heure
- [x] Page « Alertes » : alertes du jour et des 14 derniers jours, « marquer comme lu », « tout marquer comme lu », lien direct vers la fiche ; compteur dans le menu
- [x] « À faire aujourd'hui » sur la vue d'ensemble (phase 5)
- [x] Récapitulatif quotidien par e-mail via Brevo à l'heure choisie (7h par défaut), un seul par jour, pas d'e-mail vide ; nouvel essai l'heure suivante en cas d'échec ; e-mail de test depuis les préférences
- [x] Déclenchement planifié : `.github/workflows/rappels.yml` appelle chaque heure `POST /api/cron/daily`, protégé par la clé `CRON_SECRET`
- [x] Seuls les membres ayant un compte reçoivent des alertes ; un responsable en nom libre n'en reçoit pas (déjà signalé « sans compte »)
- [x] Désactivation possible par l'utilisateur, règle par règle
- [x] Mise en service (5 nov. 2026, e-mail de test reçu) : compte Brevo, expéditeur de test vérifié (adresse Gmail dédiée à PILOT), `BREVO_API_KEY`, `MAIL_SENDER_EMAIL` et `CRON_SECRET` dans Render, secret `CRON_SECRET` dans GitHub
- [x] Alerte « Proposition à valider » : proposition sans décision depuis 2 jours, rappelée à son auteur

**Terminé quand :** une tâche à J-3 produit exactement une alerte pour le bon destinataire ; une tâche terminée ou annulée n'en produit plus ; un lecteur ne reçoit pas d'alerte sur une action qu'il ne peut pas faire ; le récapitulatif part à l'heure prévue dans le fuseau de l'espace.

## Phase 8 — Boîte de mise à jour par texte ou document (CDC §9, §10)

- [x] Modèles `UpdateRequest` (demande : message, visibilité privée ou partagée, notes), `UpdateSource` (fichier conservé, état de lecture) et `Proposal` (états : À préciser, À valider, En conflit — calculé quand le projet a changé —, Appliquée, Écartée)
- [x] Saisie libre + dépôt de fichiers (3 au plus), sans choisir le projet avant l'analyse ; « Réessayer » sans doublon
- [x] Extraction du texte (PDF texte, DOCX, XLSX, PPTX, TXT, CSV, Markdown) avec limites : 5 Mo lus, 40 pages, 30 000 caractères, archives Office trop gonflées refusées ; tableaux avec une colonne « Projet » lus ligne par ligne ; pas d'OCR (PDF scanné et images signalés, conservés)
- [x] Moteur déterministe (`updates/engine.py`) : normalisation des accents, titres, sigles, ordre des mots, titre le plus précis, nom du fichier ; départage par filiale, ville, pays, édition ou programme ; sinon candidats à choisir
- [x] Reconnaissance des champs : statut, avancement, échéance, responsable (membre ou nom libre), situation, prochaine étape, décision, blocage, vigilance ; texte libre proposé comme situation
- [x] Garde-fous CDC §10 : pas de % d'objectif lu comme avancement, pas de « sera terminé » ni « n'est pas terminé » lu comme Terminé (Terminé et Annulé restent sur la fiche, avec bilan ou motif), contradictions mises de côté, aucune date relative ni sans année convertie, un projet cité dans une prochaine étape ne change pas la cible
- [x] Écran « Mises à jour » : comparaison actuel / proposé champ par champ (cases à cocher), passage source, choix du projet, recalcul en cas de conflit, écarter avec motif
- [x] Validation puis application atomique (verrou de ligne, vérification de version, journal « mise à jour validée »), sans double application
- [x] Messages de fin de parcours (CDC §22) : reçu, compris, incertain, changé ; projet non identifié, plusieurs projets possibles, fichier non analysé, déjà à jour

**Terminé quand :** UPD01 à UPD05 et DOC02 passent. ✅ (5 nov. 2026 : `tests/test_updates.py`, `tests/test_update_engine.py`)

## Phase 9 — Export, sauvegarde et fiabilisation (CDC §18, §19)

- [x] Export complet d'un espace (propriétaire) : ZIP avec `pilot-export.json` (structure, projets, tâches, événements, catalogue des pièces) et contenu des fichiers vérifiable par empreinte SHA-256 ; option « données seules » ; jamais de secret ni de demande privée
- [x] Import dans un **nouvel** espace (jamais d'écrasement) : structure rapprochée par nom, pièces vérifiées par empreinte, valeurs piégées neutralisées (liens, couleurs, fuseau), réimport du même fichier sans doublon (EXP01)
- [x] Procédure de sauvegarde et de restauration documentée : [docs/SAUVEGARDE.md](docs/SAUVEGARDE.md) (historique Neon de 6 h sur l'offre gratuite, branches hebdomadaires, export mensuel, responsabilités, restauration sans perte) — [ ] test de restauration sur `staging` à réaliser avec l'utilisateur
- [x] Pagination des documents (50 par page, « Afficher plus ») ; contenu des pièces toujours téléchargé à la demande, jamais dans les listes
- [x] Tests des cas limites : session expirée (retour à la connexion puis à la page), titres longs, accents et symboles, HTML saisi, doublons de noms, fichiers piégés, listes longues ; réseau coupé déjà signalé (« Le serveur ne répond pas »)
- [x] Revue de sécurité : test automatique « chaque route d'espace vérifie l'appartenance » et CSRF global ; e-mails échappés ; fichiers toujours en pièce jointe (`nosniff`) ; lecteurs XML sans entités externes (defusedxml, lxml) ; archives Office et ZIP plafonnées ; connexion freinée après 8 échecs en 15 min ; en-têtes de sécurité sur Vercel (CSP, X-Frame-Options, HSTS…)

**Terminé quand :** EXP01 passe et une restauration a été testée sur la branche `staging`.

## Compléments du cahier des charges (6 nov. 2026)

Écarts relevés en relisant le CDC section par section, puis comblés :

- [x] Contributeurs du projet, distincts du responsable, sans droit supplémentaire (§21)
- [x] Liens entre projets, symétriques et journalisés, sans duplication (§5)
- [x] ~~Tâches du « suivi général », sans projet~~ — **retiré le 9 nov. 2026** à la demande de la propriétaire du produit : une tâche appartient toujours à un projet. Les tâches sans projet déjà saisies sont rangées automatiquement dans un projet « Suivi général » de leur espace (migration `e56683f9014f`, journalisée) ; un ancien export qui en contient fait de même à l'import.
- [x] Vue hebdomadaire « Point hebdo » : à surveiller, décisions, échéances, changements, informations manquantes ; date et source affichées ; impression (§7)
- [x] Source et fraîcheur de la situation : saisie sur la fiche ou boîte de mise à jour, date et auteur (§21)
- [x] Origine du besoin à la création et sur la fiche (§6, étape 1)
- [x] Options de décision (3 au plus) avec leurs conséquences, sans jamais marquer d'option choisie (§7)
- [x] Repères visuels : emoji de portefeuille et drapeau du pays, toujours à côté du nom (§13)
- Décision : lecture **toujours avec un compte** (le lien public sans compte du CDC §15 n'est pas repris, plus sûr)

## Suite prévue : fonctions inspirées d'Asana (demandées le 6 nov. 2026 ; lots A, B et C faits les 8 et 9 nov.)

Ce qui manque à PILOT par rapport à Asana pour le travail d'équipe au quotidien. À lancer quand la propriétaire du produit le décide, un lot à la fois, chacun testé et mis en ligne à part.

**Règle commune : rien de ce qui existe ne change de comportement.**
- On ajoute, on ne remplace pas : les projets, tâches, rôles, alertes, documents, mises à jour, exports et sauvegardes actuels continuent de fonctionner à l'identique.
- Les données déjà saisies restent valables sans reprise.
- Les migrations de la base ne font qu'ajouter des tables et des colonnes facultatives.
- Chaque nouveauté est intégrée à ce qui existe déjà : journal, rappels, export/import, recherche, mode clair et mode sombre.
- Avant chaque lot, relecture du cahier des charges pour vérifier la cohérence. En cas de conflit, on décide avant de coder.

### Lot A — Tâches complètes (fait le 8 nov. 2026)
- [x] **Sous-tâches** : découper une tâche en petites étapes, avec un avancement « 2 sur 5 ».
  - Une sous-tâche est une tâche rattachée à une autre : mêmes statuts, même responsable possible, mêmes rappels.
- [x] **Commentaires sur une tâche**, avec mention **@nom** d'un membre.
  - La personne mentionnée est prévenue dans Alertes et dans son récapitulatif par e-mail.
- [x] **Abonnés** d'une tâche : ils sont prévenus des changements (statut, échéance, commentaire).
  - Le responsable et l'auteur de la tâche sont abonnés automatiquement ; chacun peut se désabonner.
- [x] **Dépendances** : « cette tâche attend la fin de telle autre ».
  - La tâche en attente est signalée comme bloquée tant que l'autre n'est pas terminée.
  - Une boucle (A attend B, qui attend A) est refusée.
- Réalisation :
  - Tout se passe dans une **fenêtre de la tâche**, ouverte en cliquant sur son titre depuis n'importe quelle page (adresse `?tache=…`, partageable). On peut aussi y modifier la tâche : titre, livrable, responsable, échéance.
  - Dans les listes, des repères : « En attente », sous-tâches « 1/3 », nombre de commentaires.
  - Décision du 9 nov. 2026, révisée le même jour (propriétaire du produit) : **tout se passe dans la fiche du projet**. « Tâches » est retiré du menu et la page `/taches` supprimée ; plus de tâche sans projet. Dans la fiche : liste ou tableau (bouton « Liste / Tableau »), « + Tâche », « + Sous-tâche ». Les sous-tâches restent dans leur tâche (fenêtre de la tâche, compteur ☑). Depuis une tâche, aucun lien ne renvoie ailleurs.
  - Décision du 9 nov. 2026 (propriétaire du produit) : l'**historique du projet** n'est plus affiché en permanence ; il s'ouvre avec le bouton « Historique » en haut de la fiche (panneau à droite, accessible aussi aux lecteurs).
  - Notifications (CDC §16) : une alerte « Mention » ou « Tâche suivie » apparaît tout de suite dans Alertes, et figure dans le récapitulatif e-mail du jour s'il n'est pas encore parti. Pas d'e-mail à chaque commentaire. Une seule alerte par tâche et par jour, mise à jour à chaque nouvel événement.
  - Lecteurs : consultent et peuvent suivre une tâche ; ils ne commentent pas et ne modifient rien.
  - Un commentaire est retiré seulement par son auteur ou par un propriétaire.
  - Journal du projet, export et import mis à jour. Les abonnements ne sont pas exportés : ils sont propres à chaque compte.

### Lot B — Tableau avec cartes à glisser (fait le 9 nov. 2026)
- [x] Nouvelle vue **Tableau** dans la fiche de chaque projet (bouton « Liste / Tableau ») : colonnes À faire / En cours / Terminé, avec la carte qu'on fait glisser d'une colonne à l'autre.
  - Une autre manière d'afficher les mêmes tâches : la vue Liste reste. Les statuts ne changent pas.
- [x] Tout reste faisable au clavier et sur téléphone, sans glisser, avec le choix du statut sur la carte.
- [x] Les lecteurs voient le tableau mais ne peuvent pas déplacer les cartes.
- Réalisation : la colonne Terminé montre les 30 plus récentes (toutes restent en vue Liste) ; une tâche annulée y apparaît avec l'étiquette « Annulée ». Les filtres de la page (en retard, 7 jours, projet, mes tâches, recherche) s'appliquent aussi au tableau. Une carte déplacée reste à sa place sans attendre le serveur ; en cas d'erreur, elle revient et un message s'affiche.

### Lot C — Droits plus fins (fait le 9 nov. 2026)
- [x] **Rôle par projet**, par exemple Contributeur sur un projet et Lecteur sur les autres.
  - Le rôle de l'espace (Propriétaire, Contributeur, Lecteur) reste la règle par défaut ; le rôle sur un projet ne fait que le préciser.
  - Un propriétaire de l'espace garde toujours tous les droits.
- [x] **Projets privés**, visibles seulement par leurs membres et par les propriétaires de l'espace.
  - Les projets existants restent ouverts à tout l'espace, comme aujourd'hui.
  - Un projet privé n'apparaît nulle part ailleurs (tableau de bord, timeline, recherche, alertes, Point hebdo, export) pour ceux qui n'y ont pas accès.
- [x] **Invités extérieurs** (prestataire, partenaire) : un compte limité à un ou plusieurs projets, sans voir le reste de l'espace.
- Réalisation :
  - Une seule règle, dans `access.py`, appliquée à **tous les chemins** (CDC §4, point de gouvernance) :
    - liste et fiche des projets ;
    - tâches, fenêtre d'une tâche, dépendances ;
    - documents : liste, versions, téléchargement ;
    - historique et projets liés ;
    - alertes, récapitulatif e-mail et notifications ;
    - boîte de mise à jour : reconnaissance des projets et propositions ;
    - recherche, tableau de bord, timeline et Point hebdo, qui s'appuient sur ces listes.
  - Un projet invisible répond « introuvable ».
  - Bouton **« Accès »** sur chaque fiche projet. Les propriétaires y rendent le projet privé et y ajoutent des personnes avec un rôle de projet (contributeur ou lecteur). Les autres membres consultent qui a accès. Chaque changement est journalisé (`project.access_changed`).
  - Rôle **« Invité »** à l'invitation : il ne voit que les projets où on l'ajoute, ne crée pas de projet et n'a pas la boîte de mise à jour.
  - Une marque 🔒 signale un projet privé.
  - Export : la case « privé » suit le projet. Les accès par projet, propres aux comptes, sont à redonner après un import.
  - Limite connue : un invité voit la liste des membres de l'espace (noms et adresses), nécessaire pour choisir un responsable. À restreindre si besoin.

**Hors de ces lots** (à décider plus tard) : sections dans un projet, une même tâche dans plusieurs projets, champs personnalisés, règles automatiques.

## Audit complet (9 nov. 2026)

Audit technique et fonctionnel de tout l'existant (serveur, base de données, écran), puis correction de **tous** les points relevés, avec l'accord de la propriétaire du produit.

État général : bon. Architecture saine, tests verts, base et code identiques, rien de sensible dans le dépôt public, pas d'erreur critique.

**Priorité élevée**
- [x] E1 — Partager un fichier de la boîte de mise à jour vers un projet exige le droit d'écriture sur ce projet.
- [x] E2 — Tableau : une carte déplacée vite ne reste plus bloquée ; une carte en cours d'enregistrement ne peut pas être redéplacée.

**Priorité moyenne**
- [x] M1 — L'e-mail d'aperçu filtre les projets invisibles, comme le récapitulatif (filtre commun dans `todays_alerts`).
- [x] M2 — Un projet invisible n'est plus nommé dans l'historique d'un projet lié, dans l'alerte « … est terminée » ni dans les notes de la boîte de mise à jour.
- [x] M3 — Modifications simultanées : la ligne est verrouillée pendant l'enregistrement. La seconde reçoit « modifié entre-temps » au lieu d'écraser la première.
- [x] M4 — Envoi de fichiers et import traités hors de la boucle principale : un gros fichier ne ralentit plus les autres.
- [x] M5 — Page Documents : l'envoi n'est proposé que vers les projets où l'on peut écrire.
- [x] M6 — Plus de « + Sous-tâche » dans un projet terminé ou annulé.
- [x] M7 — Retirer un membre efface ses abonnements, alertes et préférences dans l'espace.
- [x] M8 — Code devenu inutile depuis la suppression de la page Tâches retiré.
- [x] M9 — Panneaux (tâche, Historique, Accès) : focus gardé dans le panneau, rendu au bouton d'origine à la fermeture.

**Priorité faible**
- [x] F1 — Message et bouton « Réessayer » si les tâches d'un projet ne se chargent pas.
- [x] F2 — Confirmation « ✓ Accès enregistrés. »
- [x] F3 — Le compteur d'alertes se met à jour tout de suite après une action sur une tâche.
- [x] F4 — La recherche ne propose plus « Nouveau projet » ni « Mises à jour » aux lecteurs et invités.
- [x] F5 — « Écarter » et « Recalculer » une proposition exigent le droit d'écriture.
- [x] F6 — Doublon dû à deux actions simultanées : message clair (409) au lieu d'une erreur serveur.
- [x] F7 — L'import refuse les dépendances en boucle d'un fichier modifié, et nettoie les noms de fichiers.
- [x] F8 — L'import réutilise un portefeuille « Suivi général » existant (même archivé).
- [x] F9 — Documentation de l'API fermée en production (ouverte en test).
- [x] F10 — Index ajoutés (responsable de tâche, responsable de projet, contributeurs, alertes). Le projet devient obligatoire pour une tâche jusque dans la base (migration `f1f4e5967a9d`, avec garde-fou).
- [x] F11 — Le retour arrière du lot C refuse de s'exécuter s'il existe des projets privés.
- Adresse de retour après connexion durcie (`/\…` refusé).

## Fluidité de l'interface (10 nov. 2026)

Demande de la propriétaire du produit : l'interface paraissait lente.

Mesure avant : une page mettait **0,9 s** à finir d'apparaître après un clic. Après : **0,3 s**.

- Entrée des pages en 0,15 s, d'un seul bloc. Avant : 0,6 s par bloc, en cascade, avec un flou.
- Plus de « verre dépoli » (16 flous recalculés à chaque image derrière un fond animé). Les surfaces sont presque opaques, avec le même rendu.
- Plus d'animations qui redessinent sans arrêt : dégradés défilants des barres d'avancement, du nom et du logo, bordure tournante du bandeau, pulsation des pastilles.
- Le fond et les halos bougent sans flou calculé : seule la carte graphique travaille.
- Chiffres du tableau de bord animés en 0,35 s (au lieu de 0,7 s).
- Pages chargées à la demande puis préchargées en arrière-plan. Le programme téléchargé à l'ouverture passe d'environ 500 Ko à 317 Ko (−35 %).
- **Application vivante** (demande du même jour : « elle doit agir ») : des animations qui répondent aux actions, et rien qui tourne en continu.
  - Confirmations animées en bas à droite (« ✓ Tâche terminée », « ✓ Commentaire publié »…), une trentaine d'actions concernées.
  - Réaction immédiate : une tâche cochée ou déplacée change tout de suite à l'écran (moins de 0,2 s), puis le serveur confirme.
  - Tâche cochée qui « saute » et s'illumine ; nouveaux éléments qui glissent en place ; carte du tableau qui « atterrit » ; boutons qui répondent au survol et au clic ; compteur d'alertes qui saute quand il change.
  - Chargements en barres scintillantes au lieu du texte « Chargement… ».
  - Données rafraîchies seules toutes les 30 s quand l'onglet est visible.
- Limite qui reste (hébergement gratuit) : après 15 minutes sans visite, le serveur s'endort ; le premier accès prend alors 30 à 60 s. Elle disparaît avec l'offre Render payante (décision reportée).

## Phase 10 — Mise en production

- [ ] Changer le mot de passe de la base Neon (il a circulé pendant la mise en place)
- [ ] Expéditeur des e-mails dédié à PILOT sur un domaine à nous (ex. `notifications@<domaine>`), domaine authentifié dans Brevo (DKIM, DMARC), puis `MAIL_SENDER_EMAIL` dans Render. Une seule adresse pour tout PILOT ; les adresses des utilisateurs ne sont que des destinataires. (Pendant les tests : une adresse Gmail validée comme expéditeur dans Brevo.)
- [ ] Recette complète sur `pilot-staging`
- [ ] Domaine, HTTPS, variables de production
- [ ] Publication puis vérification des données réellement disponibles
- [ ] Documentation : installation, rôles, limites connues, procédure de livraison

Décisions du 9 nov. 2026 (propriétaire du produit) :
- **Adresse** : on garde pour l'instant `pilot-beta-swart.vercel.app`. Le nom de domaine et l'adresse d'expédition des e-mails dédiée viendront plus tard.
- **Hébergement** : on reste sur les offres gratuites tant que PILOT est en test.
- **Production séparée** : pas encore. L'application est toujours en construction ; on continue sur l'environnement actuel.

**Terminé quand :** la propriétaire du produit valide la recette en production.

## Après la V1 (non engagé)

Chacun de ces sujets demande une décision explicite avant d'être lancé (CDC §16) : connecteur SharePoint/OneDrive, intégration Outlook ou Teams, OCR, assistant IA conversationnel.

---

## Décisions à prendre

| # | Question | Recommandation | Statut |
|---|---|---|---|
| D1 | Mode de connexion | E-mail + mot de passe pour la V1 (aucun service d'e-mail nécessaire). Lien magique plus tard. | Décidé |
| D2 | Stockage des fichiers | Phase de test (gratuite) : fichiers stockés dans Neon, avec les limites de taille du CDC, derrière une interface `FileStorage` unique. Avant la production : passer à un stockage objet en changeant seulement l'implémentation de cette interface. Piste pour plus tard : le « stockage d'objets » proposé par Neon dans le même projet (sinon S3, R2 ou Vercel Blob). | Décidé pour la phase de test |
| D3 | Invitations | Sans service d'e-mail : la propriétaire saisit l'adresse et obtient un lien d'invitation à transmettre ; la personne crée son compte avec cette adresse et rejoint l'espace. Envoi automatique de l'e-mail par Brevo plus tard. | Décidé |
| D4 | Contributeurs et validation | Un contributeur valide ses propres propositions (comme dans le CDC). | Décidé |
| D5 | Droits par projet ou par filiale | Pas en V1 : les droits s'appliquent à tout l'espace. | Décidé |
| D6 | Canal des rappels | Alertes dans l'application + e-mail via **Brevo** (offre gratuite). Clé API Brevo stockée uniquement dans les variables d'environnement Render. Brevo servira aussi, si souhaité, aux e-mails d'invitation et de réinitialisation du mot de passe. | Décidé |
| D7 | Style visuel | **Révisé le 6 nov. 2026 (demande du manager) : style « PILOT 2040 »** — thème sombre, verre dépoli, lueurs néon orange → magenta → violet → cyan, fond animé, polices Space Grotesk (titres) et JetBrains Mono (repères), mouvements doux (désactivés si l'utilisateur réduit les animations) ; e-mails au même style (`email_theme.py`). **Deux modes d'affichage (6 nov. 2026)** : sombre (par défaut) et clair (fond blanc, texte noir), au choix de chaque personne avec le bouton « Mode clair / Mode sombre » en bas du menu et sur les pages de connexion ; le choix est gardé sur l'appareil. Version précédente :  Inspiré de l'image de référence `4eb2950829ff621189b9d820b3e9d34c.webp` : police Plus Jakarta Sans, fond gris clair #F4F4F5, panneaux blancs à coins arrondis (16–20 px), bordures fines #ECECEE, orange #F26A1B pour la marque, #D0450A pour les boutons (contraste suffisant pour le texte blanc), statuts en pastilles (point + texte). Maquette : https://claude.ai/artifact/ReTWXj3VRy4WHS5EMBqXAL | Décidé (validé le 3 nov. 2026) |
