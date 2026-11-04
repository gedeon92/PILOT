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
- [ ] Séparation dossier partagé / sources privées de mise à jour : à construire avec la boîte de mise à jour (phase 8)
- [ ] Remplacement d'un document avec conservation de la version précédente

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
- [ ] Liste des projets sans date
- [x] Fuseau horaire de l'espace
- [x] Annulation : retrait du calendrier actif, dossier et anciennes dates conservés

**Terminé quand :** CAL01 et CAL02 passent.

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

- [ ] Modèles `Alert` et `AlertPreference` (par utilisateur : règles actives, canal, heure du récapitulatif)
- [ ] Calcul des alertes dans le fuseau de l'espace, sans doublon (une alerte par règle, par objet et par jour)
- [ ] Centre de notifications dans l'application : cloche avec compteur, liste, « marquer comme lu », lien direct vers la fiche
- [ ] Bandeau « À faire aujourd'hui » en haut du tableau de bord
- [ ] Récapitulatif quotidien à l'heure choisie (7h par défaut), via le canal retenu en D6
- [ ] Déclenchement planifié côté serveur, indépendant du navigateur : en phase de test, un workflow GitHub Actions planifié (gratuit) appelle une route protégée de l'API
- [ ] Seuls les membres ayant un compte reçoivent des alertes ; un responsable saisi en texte libre est signalé « sans compte, pas de rappel »
- [ ] Désactivation possible par l'utilisateur, règle par règle

**Terminé quand :** une tâche à J-3 produit exactement une alerte pour le bon destinataire ; une tâche terminée ou annulée n'en produit plus ; un lecteur ne reçoit pas d'alerte sur une action qu'il ne peut pas faire ; le récapitulatif part à l'heure prévue dans le fuseau de l'espace.

## Phase 8 — Boîte de mise à jour par texte ou document (CDC §9, §10)

- [ ] Modèle `Proposal` (états : Reçue, À préciser, À valider, En conflit, Appliquée, Écartée)
- [ ] Saisie libre + dépôt de fichiers, sans choisir le projet avant l'analyse
- [ ] Extraction du texte (PDF texte, DOCX, XLSX, PPTX, TXT, CSV, Markdown) avec limites : 5 Mo lus, 40 pages, environ 30 000 caractères, délai maximal
- [ ] Moteur déterministe : normalisation des accents, titres, abréviations, mots-clés, nom du fichier
- [ ] Reconnaissance des champs : statut, avancement, échéance, responsable, situation, prochaine étape, décision
- [ ] Garde-fous CDC §10 : pas de % d'objectif lu comme avancement, pas de « sera terminé » lu comme Terminé, contradictions mises en attente, aucune conversion de date relative
- [ ] Écran de comparaison avant/après avec le passage source
- [ ] Validation puis application atomique avec vérification de version, sans double application
- [ ] Messages de fin de parcours (CDC §22)

**Terminé quand :** UPD01 à UPD05 et DOC02 passent.

## Phase 9 — Export, sauvegarde et fiabilisation (CDC §18, §19)

- [ ] Export complet d'un espace (données + catalogue des fichiers)
- [ ] Import de l'export dans un espace de test sans doublons
- [ ] Procédure de sauvegarde et de restauration documentée et testée (Neon : points de restauration)
- [ ] Pagination, chargement des pièces à la demande
- [ ] Tests des cas limites : réseau coupé, session expirée, titres longs, accents, doublons de noms
- [ ] Revue de sécurité (droits, CSRF, échappement HTML, fichiers reçus)

**Terminé quand :** EXP01 passe et une restauration a été testée sur la branche `staging`.

## Phase 10 — Mise en production

- [ ] Changer le mot de passe de la base Neon (il a circulé pendant la mise en place)
- [ ] Recette complète sur `pilot-staging`
- [ ] Domaine, HTTPS, variables de production
- [ ] Publication puis vérification des données réellement disponibles
- [ ] Documentation : installation, rôles, limites connues, procédure de livraison

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
| D7 | Style visuel | Inspiré de l'image de référence `4eb2950829ff621189b9d820b3e9d34c.webp` : police Plus Jakarta Sans, fond gris clair #F4F4F5, panneaux blancs à coins arrondis (16–20 px), bordures fines #ECECEE, orange #F26A1B pour la marque, #D0450A pour les boutons (contraste suffisant pour le texte blanc), statuts en pastilles (point + texte). Maquette : https://claude.ai/artifact/ReTWXj3VRy4WHS5EMBqXAL | Décidé (validé le 3 nov. 2026) |
