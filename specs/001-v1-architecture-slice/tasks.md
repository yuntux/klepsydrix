# Liste de Tâches : Tranche Verticale de la V1

**Input**: Documents de conception depuis `/specs/001-v1-architecture-slice/`

**Prerequisites**: [plan.md](plan.md) (requis), [spec.md](spec.md) (requis), [data-model.md](data-model.md), [contracts/api.md](contracts/api.md)

**Tests**: TDD requis par la Constitution. Écrire les tests unitaires/intégration en premier et vérifier qu'ils échouent avant d'implémenter les fonctionnalités associées.

---

## Format : `[ID] [P?] [Story] Description`
- **[P]** : Tâche parallélisable (fichiers distincts, sans dépendances directes sur des tâches en cours).
- **[Story]** : Représente la User Story associée (ex : US1, US2). Le format strict des lignes est respecté.

---

## Phase 1: Setup (Infrastructures Partagées)

**Purpose**: Initialisation physique du projet et isolation des environnements de développement.

- [x] T001 Créer l'arborescence des dossiers `backend/` et `frontend/` selon le plan technique dans le workspace local
- [x] T002 Initialiser le projet backend avec le fichier de dépendances `backend/requirements.txt`
- [x] T003 [P] Initialiser le projet frontend Vue 3 avec Vite, TypeScript et npm dans `frontend/package.json`
- [x] T004 Créer le fichier de configuration initial `backend/app/core/config.py` (Pydantic Settings pour le chargement du `.env`)
- [x] T005 [P] Configurer le fichier d'exemple `backend/.env.example` et le fichier de configuration du proxy `frontend/vite.config.ts`

---

## Phase 2: Foundational (Prérequis Bloquants)

**Purpose**: Infrastructure de persistance SQLAlchemy et connexion à SQLite nécessaire pour toutes les User Stories.

**⚠️ CRITICAL**: Aucun travail sur les User Stories ne peut débuter tant que cette phase n'est pas intégralement achevée et validée.

- [ ] T006 Créer la base déclarative et la connexion sessionmaker dans `backend/app/core/database.py`
- [ ] T007 [P] Créer la base de modèles partagés dans `backend/app/models/base.py`
- [ ] T008 [P] Implémenter les schémas de base SQLAlchemy dans `backend/app/models/teacher.py`, `backend/app/models/classroom.py` et `backend/app/models/division.py`
- [ ] T009 [P] Implémenter les modèles restants dans `backend/app/models/timeslot.py` et `backend/app/models/course.py`
- [ ] T010 Créer le script d'initialisation de la base de données et de chargement du jeu de données d'exemple mocké (10 enseignants, 5 classes, 5 salles, 30 cours non placés) dans `backend/app/core/init_db.py`
- [ ] T011 Configurer le routeur principal de l'API FastAPI et le middleware de gestion CORS dans `backend/app/main.py`

**Checkpoint** : Fondations de données validées. SQLite est opérationnel, le schéma est créé avec le mock de données de départ.

---

## Phase 3: User Story 1 - Visualisation et Résolution Automatique de la Grille (Priority: P1) 🎯 MVP

**Goal**: Charger le planning hebdomadaire d'exemple (lundi au samedi) depuis le backend, l'afficher dans l'IHM et lancer le solveur Timefold pour affecter automatiquement tous les cours en respectant scrupuleusement les contraintes d'exclusion.

**Independent Test**: L'utilisateur ouvre l'application, voit la grille avec les créneaux vides et la liste des cours à planifier dans le panneau latéral. Il clique sur "Résoudre" : en moins de 5 secondes, la grille se remplit de cours résolus sans chevauchement.

### Tests pour User Story 1 (TDD)
- [ ] T012 [P] [US1] Écrire le test d'intégration unitaire pour le solveur dans `backend/tests/test_solver.py` (vérifier qu'il échoue à résoudre des conflits simples en l'absence de code)
- [ ] T013 [P] [US1] Écrire le test de contrat API pour le chargement et la résolution dans `backend/tests/test_api.py` (vérifier l'échec des requêtes `GET /api/timetable` et `POST /api/timetable/solve`)

### Implémentation pour User Story 1
- [ ] T014 [US1] Définir les schémas d'API Pydantic d'entrées/sorties pour le planning global dans `backend/app/schemas/schemas.py`
- [ ] T015 [US1] Implémenter le service d'évaluation des contraintes de Timefold (contraintes dures de chevauchements et contraintes souples distinctes de "trous" pour les enseignants d'une part, et pour les divisions d'élèves d'autre part) dans `backend/app/solver/constraints.py`
- [ ] T016 [US1] Implémenter le service d'exécution et de déclenchement du solveur Timefold dans `backend/app/solver/solver.py`
- [ ] T017 [US1] Implémenter les routes REST `GET /api/timetable` et `POST /api/timetable/solve` dans `backend/app/api/endpoints.py` (en cas d'insolvabilité, lever l'erreur 422 "Résolution impossible")
- [ ] T018 [P] [US1] Créer les interfaces TypeScript pour le typage IHM dans `frontend/src/types/index.ts`
- [ ] T019 [P] [US1] Développer le client HTTP de requêtage API dans `frontend/src/services/api.ts`
- [ ] T020 [P] [US1] Créer le thème visuel sombre premium de l'application dans `frontend/src/assets/main.css`
- [ ] T021 [US1] Implémenter la barre d'outils et les contrôles (chargement, bouton Résoudre) dans `frontend/src/components/HeaderControls.vue`
- [ ] T022 [US1] Créer le panneau latéral affichant les cours non encore planifiés dans `frontend/src/components/Sidebar.vue`
- [ ] T023 [US1] Développer le composant de grille hebdomadaire affichant les plannings du lundi au samedi (créneaux de 1 heure) dans `frontend/src/components/TimetableGrid.vue`
- [ ] T024 [US1] Assembler les composants dans `frontend/src/App.vue` et initialiser l'application Vue dans `frontend/src/main.ts`
- [ ] T025 [US1] Exécuter la validation manuelle de bout en bout du flux de résolution automatique en local

**Checkpoint** : La User Story 1 (MVP) est intégralement fonctionnelle et testable de bout en bout.

---

## Phase 4: User Story 2 - Édition Manuelle et Résolution des Conflits de la Grille par Drag & Drop (Priority: P2)

**Goal** : Permettre à l'utilisateur de déplacer des cours manuellement sur la grille en glisser-déposer, de les réaffecter ou de les retirer, avec validation immédiate du backend pour empêcher tout conflit de ressource dur.

**Independent Test** : L'utilisateur glisse un cours de mathématiques d'un créneau A vers un créneau B. Si l'enseignant est déjà occupé sur le créneau B, le backend refuse la mise à jour (erreur 409) et le cours retourne automatiquement à sa place d'origine.

### Tests pour User Story 2 (TDD)
- [ ] T026 [P] [US2] Écrire les tests unitaires de conflits manuels dans `backend/tests/test_api.py` (vérifier que l'API bloque les chevauchements en renvoyant une erreur 409)

### Implémentation pour User Story 2
- [ ] T027 [US2] Implémenter le service de vérification manuelle de conflits en base de données avant modification dans `backend/app/api/endpoints.py`
- [ ] T028 [US2] Implémenter les endpoints `PUT /api/courses/{course_id}` et `POST /api/timetable/reset` dans `backend/app/api/endpoints.py`
- [ ] T029 [P] [US2] Mettre à jour le client de requêtage front pour le reset et le déplacement dans `frontend/src/services/api.ts`
- [ ] T030 [US2] Ajouter le support natif HTML5 de Drag & Drop dans le composant de carte de cours `frontend/src/components/TimetableGrid.vue`
- [ ] T031 [US2] Gérer le retour visuel (drop zones valides ou invalides) dans `frontend/src/components/TimetableGrid.vue`
- [ ] T032 [US2] Coder la gestion du glisser-déposer depuis le panneau latéral (`Sidebar.vue`) vers la grille (`TimetableGrid.vue`)
- [ ] T033 [US2] Implémenter le comportement de retour à la case départ (Revert) en cas d'erreur API 409 reçue du serveur dans `frontend/src/App.vue`
- [ ] T034 [US2] Ajouter le bouton de réinitialisation complète de la grille dans `frontend/src/components/HeaderControls.vue`
- [ ] T035 [US2] Valider manuellement le flux complet d'édition interactive et de refus des chevauchements en local

**Checkpoint** : La User Story 2 est validée. L'utilisateur dispose d'une planification interactive robuste.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Validation finale de l'isolation, nettoyage et documentation.

- [ ] T036 Rédiger la documentation technique d'utilisation des API dans `backend/README.md`
- [ ] T037 Rédiger le guide de contribution et de lancement de l'IHM dans `frontend/README.md`
- [ ] T038 Exécuter l'intégralité de la suite de tests unitaires et d'intégration `pytest` pour s'assurer d'une couverture à 100% de la logique métier
- [ ] T039 Effectuer une passe finale de revue de code (conformité TypeScript strict, typage Python avec MyPy)
- [ ] T040 [P] Valider le guide `quickstart.md` en ré-exécutant l'installation complète dans de nouveaux dossiers `.venv` et `node_modules` locaux

---

## Dépendances & Ordre d'Exécution

### Dépendances de Phase
1. **Setup (Phase 1)** : Aucune dépendance. Peut démarrer immédiatement.
2. **Foundational (Phase 2)** : Dépend de Phase 1. Bloque absolument les phases suivantes.
3. **User Story 1 (Phase 3)** : Dépend de Phase 2. Représente notre MVP.
4. **User Story 2 (Phase 4)** : Dépend de Phase 2. Peut être démarrée en parallèle de US1 si l'équipe le souhaite, mais requiert l'intégration de la grille finale.
5. **Polish (Phase 5)** : Dépend de la complétude des phases 3 et 4.

### Opportunités de Parallélisation
- Durant la phase de Setup, les tâches backend (`T002`, `T004`) et frontend (`T003`, `T005`) peuvent être exécutées de manière concurrente.
- Durant la phase Foundational, la création des modèles SQLAlchemy unitaires (`T008`, `T009`) peut être parallélisée.
- Durant l'implémentation de la US1, l'écriture du solveur backend (`T015`, `T016`, `T017`) et le développement des composants visuels front (`T020`, `T021`, `T022`, `T023`) peuvent être menés en parallèle par deux développeurs distincts.

---

## Exemple de Parallélisation : Phase 3 (US1)

```bash
# Développeur A : Backend et Moteur d'Optimisation
T012 : Écrire le test d'intégration pour le solveur
T015 : Implémenter le service d'évaluation de score (Timefold)
T016 : Implémenter l'intégration du solveur
T017 : Coder les endpoints API REST

# Développeur B : Frontend et Composants Visuels
T018 : Déclarer les interfaces TypeScript
T020 : Mettre en place le thème CSS Vanilla sombre
T021 : Développer HeaderControls.vue
T022 : Développer Sidebar.vue
T023 : Développer TimetableGrid.vue
```

---

## Stratégie d'Implémentation

### MVP d'abord (Tranche Verticale US1)
1. Réaliser Phase 1 (Setup) et Phase 2 (Foundational).
2. Réaliser toutes les tâches de la Phase 3 (User Story 1 - Résolution Automatique).
3. **ARRÊTER et VALIDER** : Démarrer les serveurs en local, s'assurer que cliquer sur "Résoudre" place instantanément les cours sans erreur. Si cette étape échoue, interdiction de commencer la US2.

### Livraison Incrémentale
1. Le socle stable (Setup + Foundational) est poussé sur la branche de dev.
2. La US1 est livrée ➡️ Version 0.1.0 fonctionnelle (Visualisation + Solveur).
3. La US2 est intégrée ➡️ Version 0.2.0 interactive (Glisser-Déposer avec blocage de conflits).
4. La phase de Polish clôture la tranche verticale avant fusion finale.
