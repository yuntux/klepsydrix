---
description: "Task list for feature implementation"
---

# Tasks: 002-yearly-timetabling-core

**Input**: Design documents from `/specs/002-yearly-timetabling-core/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure pour la V2

- [X] T001 Vérifier l'environnement Python et Node.js selon `quickstart.md`
- [X] T002 [P] Créer les fichiers vides pour les nouveaux modèles SQLAlchemy dans `backend/app/models/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Implémenter l'entité pivot `School` dans `backend/app/models/school.py` avec `standard_timeslot_duration`
- [X] T004 Implémenter les entités nomenclatures (`Discipline`, `Subject`, `Mef`, `Site`, `Material`, `Mission`, `ElectionMethod`) dans `backend/app/models/`
- [X] T005 Implémenter les entités temporelles (`Period`, `Alternation`) dans `backend/app/models/`
- [X] T006 Mettre à jour les modèles existants (`Teacher`, `Division`, `Classroom`) dans `backend/app/models/` avec les nouvelles clés étrangères (ex: `school_id`)
- [X] T007 Scinder le modèle Cours V1 en `Course` et `Session` dans `backend/app/models/course.py` et `backend/app/models/session.py` (avec les liaisons N-à-N pour le co-enseignement et les co-ressources)
- [X] T008 Implémenter les entités de groupes (`Group`, `ClassPart`, `ClassPartLink`) dans `backend/app/models/group.py`
- [X] T009 Créer le script de migration SQLite V1 vers V2 dans `backend/app/core/database.py` suivant les étapes de `data-model.md`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Saisie et gestion du socle via le CRUD Générique (Priority: P1) 🎯 MVP

**Goal**: Ajouter, modifier, lister et supprimer l'ensemble des ressources de base via des formulaires et listes unifiés.

**Independent Test**: Créer un nouveau Matériel ou Site depuis l'IHM et vérifier son apparition dans la base de données.

### Implementation for User Story 1

- [X] T010 [P] [US1] Créer le routeur API générique `backend/app/api/generic.py` pour gérer le CRUD des modèles SQLAlchemy
- [X] T011 [US1] Intégrer les routes génériques dans `backend/app/api/endpoints.py` (ou `backend/app/main.py`)
- [X] T012 [P] [US1] Créer le composant Vue 3 `GenericList.vue` dans `frontend/src/components/` en intégrant une librairie externe (ex: PrimeVue DataTable) pour gérer nativement la pagination (30/page), le tri, le filtrage, le redimensionnement, le réordonnancement (drag-and-drop) et le sélecteur de colonnes.
- [X] T013 [P] [US1] Créer le composant Vue 3 `GenericForm.vue` dans `frontend/src/components/`
- [X] T014 [US1] Câbler l'interface utilisateur pour accéder au CRUD des 10 entités de base

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Planification avancée annuelle (Alternances A/B, Groupes) (Priority: P1)

**Goal**: Gérer les cours en quinzaine, les sous-groupes, et le contexte multi-établissement pour le solveur.

**Independent Test**: Lancer le solveur sur la Semaine A pour le Groupe 1 et vérifier que la planification respecte la durée (`duration_minutes` / `standard_timeslot_duration`) et les contraintes de groupe sans impacter l'autre école.

### Implementation for User Story 2

- [X] T015 [P] [US2] Mettre à jour `GET /api/timetable` dans `backend/app/api/endpoints.py` pour filtrer par `school_id`
- [X] T016 [US2] Adapter le convertisseur de modèle mathématique `_build_planning_problem` dans `backend/app/solver/solver.py` pour gérer `school_id`, convertir `duration_minutes` en créneaux, et geler les séances externes (`is_pinned=True`)
- [X] T017 [US2] Ajouter les règles Timefold (Chevauchement de groupes `ClassPartLink`, Alternances `week_type`) dans `backend/app/solver/solver.py`
- [X] T018 [US2] Ajouter l'endpoint de diagnostic de dépositionnement (`POST /api/timetable/structures/simulate-change`) dans `backend/app/api/endpoints.py`
- [X] T018b [US2] Créer la boîte de dialogue de confirmation UI pour l'impact des modifications de groupes dans `frontend/src/components/`

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - IHM Métier : La Fiche Cours Cumulée "Fiche T" (Priority: P2)

**Goal**: Afficher une popin unifiée consolidant visuellement les données de multiples cours sélectionnés, et la rendre déplaçable.

**Independent Test**: Sélectionner plusieurs cours, ouvrir la Fiche T, vérifier la consolidation par chips (ex: `[2/3]`), et déplacer la popin avec la souris.

### Implementation for User Story 3

- [X] T019 [P] [US3] Créer le composant de puce consolidée `ConsolidatedChip.vue` dans `frontend/src/components/`
- [X] T020 [US3] Créer le composant de la Fiche T `CoursePopin.vue` dans `frontend/src/components/` avec la logique d'agrégation des attributs divergents
- [X] T021 [US3] Implémenter le drag-and-drop natif (coordonnées absolues) pour l'en-tête de `CoursePopin.vue`

**Checkpoint**: All user stories up to US3 should now be functional

---

## Phase 6: User Story 4 - Saisie et Gestion Générique des Vœux et Indisponibilités (Priority: P2)

**Goal**: Colorer une grille pour définir les préférences (Rouge, Orange, Vert) de n'importe quelle ressource.

**Independent Test**: Placer une indisponibilité rouge sur une salle, lancer le solveur, et vérifier que la contrainte stricte (Hard Constraint) empêche le placement d'un cours.

### Implementation for User Story 4

- [X] T022 [P] [US4] Implémenter le modèle polymorphique `ResourcePreference` dans `backend/app/models/preference.py`
- [X] T023 [US4] Ajouter le CRUD des préférences dans l'API `backend/app/api/endpoints.py`
- [X] T024 [US4] Créer la grille interactive de saisie (Rouge/Orange/Vert) `PreferenceGrid.vue` dans `frontend/src/components/`
- [X] T025 [US4] Ajouter les pénalités / récompenses souples (Soft Constraints) et dures (Hard Constraints) dans `backend/app/solver/solver.py`
- [X] T025b [US4] Implémenter l'alerte UI lors du placement manuel d'un cours sur un créneau "Rouge" verrouillé dans `frontend/src/components/`

**Checkpoint**: All user stories should now be independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T026 Ajouter la synthèse budgétaire TRMD (`GET /api/timetable/trmd/{school_id}`) dans `backend/app/api/endpoints.py`
- [X] T027 Mettre à jour la suite de tests avec `pytest tests/test_solver.py -v` (conflits, quinzaines, vœux)
- [X] T028 Vérifier les migrations et lancer le seed V2 (via `quickstart.md`) pour validation finale

---

## Phase 8: User Story 5 - Navigation fluide et structurée via Notebooks Imbriqués et Multi-panneaux (Priority: P2)

**Goal**: Structurer l'ergonomie globale en notebooks configurables par JSON et panneaux verticaux redimensionnables.

**Independent Test**: Charger une configuration d'onglet avec 2 panneaux verticaux (liste + formulaire), et glisser-déposer le séparateur pour vérifier le redimensionnement.

### Implementation for User Story 5

- [X] T029 [P] [US5] Créer le fichier de configuration JSON des onglets `frontend/src/config/notebooks.json` avec la structure de base (Emploi du temps, Paramètres et sous-onglets du socle).
- [X] T030 [P] [US5] Créer le composant Vue 3 `NotebooksTree.vue` dans `frontend/src/components/` gérant la navigation récursive, l'affichage et l'en-tête stylisé (fond coloré ou liseré supérieur).
- [X] T031 [P] [US5] Créer le composant Vue 3 `SplitPanel.vue` dans `frontend/src/components/` implémentant le séparateur (splitter) interactif avec glisser-déposer de la souris pour recalculer les largeurs.
- [X] T032 [US5] Remplacer le squelette de mise en page dans `frontend/src/App.vue` pour utiliser `NotebooksTree` comme structure de navigation principale, alimentée par `notebooks.json`, affichant les panneaux configurés.
- [X] T033 [US5] Ajuster le style global (`frontend/src/assets/main.css`) pour appliquer le thème clair premium avec la couleur d'arrière-plan `bg-gray-300` (gris doux).

---

## Dependencies & Execution Order


### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### Parallel Opportunities

- Les entités de la Phase 2 peuvent être codées en parallèle.
- Le développement Frontend (Vue 3) des phases 3, 5 et 6 peut commencer dès que les endpoints API sont esquissés.
- Les logiques du solveur Timefold (Phase 4 et 6) peuvent être développées indépendamment de l'IHM métier.
