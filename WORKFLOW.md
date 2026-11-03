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

- [ ] Modèles : `Portfolio`, `Entity` (filiale), `ProjectType`, paramètres de l'espace (fuseau, langue)
- [ ] Écrans de gestion réservés à la propriétaire : créer, renommer, archiver sans perte de projets
- [ ] Identifiants stables indépendants des noms

**Terminé quand :** renommer un portefeuille ou une entité ne casse aucun lien, et un contributeur reçoit un refus serveur sur ces écrans.

## Phase 3 — Projets et tâches (CDC §6, §8, §21, §22)

- [ ] Modèle `Project` complet selon le dictionnaire CDC §21 (situation, prochaine étape et décision attendue séparées ; avancement nullable ; certitude de date)
- [ ] Modèle `Task` (responsable, livrable, statut, échéance proposée ou confirmée)
- [ ] Statuts : À cadrer, À lancer, En préparation, En cours, En attente de validation, Bloqué, Suspendu, Terminé, Annulé
- [ ] Règles de transition : Terminé exige un bilan ; Annulé exige un motif et clôt les tâches ouvertes ; réouverture journalisée
- [ ] Attribution du suivi : « Moi », un membre de l'espace ou un nom libre (sans création de compte)
- [ ] Champ `version` + détection de conflit à l'enregistrement (formulaire préservé)
- [ ] Journal avant/après pour chaque modification
- [ ] Clic « Réessayer » sans doublon (clé d'idempotence)

**Terminé quand :** PRJ01, PRJ02, PRJ03 passent.

## Phase 4 — Documents du projet (CDC §11)

- [ ] Modèle `Document` (nom, format, taille, clé technique, rattachement, date)
- [ ] Téléversement et téléchargement avec contrôle des droits
- [ ] Limites : 3 fichiers de 15 Mo par demande ; refus clair au-delà
- [ ] Séparation entre dossier partagé du projet et sources privées de mise à jour
- [ ] Stockage des fichiers : **décision D2 à prendre**

**Terminé quand :** DOC01 passe, et un fichier reste disponible depuis un autre appareil.

## Phase 5 — Tableau de bord, recherche et filtres (CDC §7, §13)

- [ ] Tableau de bord : sujets d'attention (retard, blocage, risque, échéance proche), prochaines échéances, projets sans responsable ou sans prochaine action
- [ ] Règle de priorité écrite et affichable
- [ ] Chaque indicateur ouvre la liste filtrée correspondante
- [ ] Cartes projet : titre, entité, statut, responsable, prochaine étape
- [ ] Recherche globale + raccourci clavier
- [ ] Filtres : portefeuille, entité, pays, statut, période
- [ ] Identité visuelle : Nunito + Manrope, bleu roi et jaune ; états chargement, vide, erreur, accès refusé, conflit
- [ ] Responsive (ordinateur, tablette, téléphone) et accessibilité clavier

**Terminé quand :** on passe d'un signal d'attention à la fiche, à la source, puis à la prochaine action en quelques clics, sur ordinateur comme sur téléphone.

## Phase 6 — Timeline et calendrier (CDC §12)

- [ ] Trois natures de dates : exacte, période, inconnue
- [ ] Statut de calendrier distinct du statut opérationnel
- [ ] Timeline : changement de famille, filtres, zoom, bouton « aujourd'hui », ouverture de fiche
- [ ] Liste des projets sans date
- [ ] Fuseau horaire de l'espace
- [ ] Annulation : retrait du calendrier actif, dossier et anciennes dates conservés

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
| D2 | Stockage des fichiers | Phase de test (gratuite) : fichiers stockés dans Neon, avec les limites de taille du CDC, derrière une interface `FileStorage` unique. Avant la production : passer à un stockage objet en changeant seulement l'implémentation de cette interface. Piste à étudier en phase 4 : le « stockage d'objets » proposé par Neon dans le même projet (sinon S3, R2 ou Vercel Blob). | À valider |
| D3 | Invitations | Sans service d'e-mail : la propriétaire saisit l'adresse et obtient un lien d'invitation à transmettre ; la personne crée son compte avec cette adresse et rejoint l'espace. Envoi automatique de l'e-mail par Brevo plus tard. | Décidé |
| D4 | Contributeurs et validation | Un contributeur valide ses propres propositions (comme dans le CDC). | Décidé |
| D5 | Droits par projet ou par filiale | Pas en V1 : les droits s'appliquent à tout l'espace. | Décidé |
| D6 | Canal des rappels | Alertes dans l'application + e-mail via **Brevo** (offre gratuite). Clé API Brevo stockée uniquement dans les variables d'environnement Render. Brevo servira aussi, si souhaité, aux e-mails d'invitation et de réinitialisation du mot de passe. | Décidé |
| D7 | Style visuel | Inspiré de l'image de référence `4eb2950829ff621189b9d820b3e9d34c.webp` : police Plus Jakarta Sans, fond gris clair #F4F4F5, panneaux blancs à coins arrondis (16–20 px), bordures fines #ECECEE, orange #F26A1B pour la marque, #D0450A pour les boutons (contraste suffisant pour le texte blanc), statuts en pastilles (point + texte). Maquette : https://claude.ai/artifact/ReTWXj3VRy4WHS5EMBqXAL | Décidé (validé le 3 nov. 2026) |
