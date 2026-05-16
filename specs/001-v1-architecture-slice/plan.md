# Plan d'Implémentation : Tranche Verticale de la V1

**Branch**: `001-v1-architecture-slice` | **Date**: 2026-05-16 | **Spec**: [spec.md](spec.md)

**Input**: Spécification fonctionnelle de la tranche verticale V1 depuis `/specs/001-v1-architecture-slice/spec.md`

---

## 1. Résumé
Ce plan d'implémentation structure la réalisation de la première **Tranche Verticale V1** de Klepsydrix. L'objectif est de poser les bases de l'architecture cible découplée en trois tiers (Frontend SPA / Backend API / Moteur d'Optimisation) et de valider un cycle complet de planification (chargement, résolution automatique, édition manuelle, persistance).

### Approche Technique globale :
- **Frontend** : Application monopage (SPA) fluide développée avec **Vue 3**, **Vite** et **TypeScript**. L'IHM utilisera du CSS Vanilla moderne, respectera une charte sombre minimaliste et performante, avec des transitions fluides et un support natif du Drag & Drop pour la grille hebdomadaire.
- **Backend** : Service d'API REST robuste avec **FastAPI** (Python 3.11+). La configuration sera lue via **Pydantic Settings** depuis un fichier local `.env`.
- **Persistance** : Couche d'accès aux données gérée par l'ORM **SQLAlchemy** sur une base locale légère **SQLite**, conçue pour être compatible avec **PostgreSQL** sans modification de code.
- **Moteur d'Optimisation** : Intégration en mémoire vive de **Timefold Solver** (Python) pour résoudre les contraintes d'exclusion mutuelle (enseignants et salles) et optimiser les contraintes souples distinctes de "trous" dans les emplois du temps (pour les enseignants d'une part, et pour les divisions d'élèves d'autre part, avec des pondérations modulables).

---

## 2. Contexte Technique

- **Language/Version** : Python 3.11+ (Backend), Node.js v18+ & TypeScript 5+ (Frontend).
- **Primary Dependencies** : 
  - *Backend* : `fastapi`, `uvicorn`, `sqlalchemy`, `pydantic`, `pydantic-settings`, `timefold` (ou algorithme de recherche locale en mémoire), `pytest`.
  - *Frontend* : `vue`, `vite`, `typescript`, `@types/node`.
- **Storage** : SQLite en local (développement), compatible PostgreSQL en production via SQLAlchemy.
- **Testing** : `pytest` (tests unitaires et d'intégration du backend), `vitest` ou tests unitaires natifs côté frontend. **Note : Pas d'automatisation des tests d'IHM par navigateur.**
- **Target Platform** : Linux local (Ubuntu/Debian) avec isolation des environnements via `.venv` (Python) et `node_modules` (Node.js).
- **Project Type** : Application Web 3-tiers découplée exécutable localement (Offline-first par nature de déploiement local).
- **Performance Goals** : 
  - Résolution automatique sous la barre des **5 secondes** pour le jeu de données V1 (30 cours).
  - Rendu et interaction avec la grille à **60 FPS** (sans geler l'interface).
- **Constraints** : 
  - Pas d'authentification utilisateur dans ce lot (accès anonyme local).
  - Zéro conflit dur autorisé en base de données après résolution.
- **Scale/Scope** : Périmètre de validation fixé à un maximum de 10 enseignants, 5 divisions, 5 salles et 30 cours.

---

## 3. Évaluation de la Constitution

*GATE: Le plan respecte scrupuleusement la constitution ratifiée v1.1.0.*

| Règle / Principe | Statut de Conformité | Justification technique |
|:---|:---|:---|
| **I. Clean Architecture** | ✅ Conforme | Strict découplage des dossiers `frontend/` et `backend/`. Code fortement typé (TypeScript côté front, Type Hints côté Python). |
| **II. Rigorous Testing** | ✅ Conforme | Développement dirigé par les tests (TDD). Interdiction formelle d'utiliser des outils de tests automatisés par navigateur (Playwright, Chromium, etc.). Tests unitaires `pytest` sur les modèles et le solveur. |
| **III. Clear Modern UX** | ✅ Conforme | Utilisation de Vue 3 + Vite. Design système minimaliste sombre et animations de transition natives Vue. Grille interactive réactive. |
| **IV. High-Performance** | ✅ Conforme | Calculateur Timefold opérant entièrement en mémoire vive pour des exécutions ultra-rapides (< 5s). Persistance SQL gérée via SQLAlchemy. |
| **V. French & English** | ✅ Conforme | Spécifications et documentations rédigées en français de manière pédagogique. Code source, variables et base de données rédigés en anglais. |
| **Sécurité & Fluidité** | ✅ Conforme | Le solveur s'exécute de manière non-bloquante pour l'IHM (via requêtes asynchrones HTTP vers le backend FastAPI). |

---

## 4. Structure du Projet

L'application sera divisée en deux répertoires principaux situés à la racine de la workspace `/home/ubuntu/klepsydrix`.

```text
/home/ubuntu/klepsydrix/
├── backend/                  # Sous-projet Backend (FastAPI / SQLAlchemy / Timefold)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py           # Point d'entrée de l'application FastAPI
│   │   ├── core/
│   │   │   ├── config.py     # Configuration Pydantic Settings (.env)
│   │   │   └── database.py   # Connexion SQLAlchemy & Sessionmaker
│   │   ├── models/
│   │   │   ├── base.py       # Base déclarative SQLAlchemy
│   │   │   ├── teacher.py
│   │   │   ├── classroom.py
│   │   │   ├── division.py
│   │   │   ├── course.py
│   │   │   └── timeslot.py
│   │   ├── schemas/
│   │   │   └── schemas.py    # Schémas de validation et d'API Pydantic
│   │   ├── api/
│   │   │   └── endpoints.py  # Routes REST (/timetable, /timetable/solve)
│   │   └── solver/
│   │       ├── solver.py     # Intégration du moteur Timefold
│   │       └── constraints.py# Définition des contraintes (Hard & Soft)
│   ├── tests/
│   │   ├── test_api.py       # Tests d'intégration des endpoints FastAPI
│   │   └── test_solver.py    # Tests unitaires du solveur et des contraintes
│   ├── .env.example          # Modèle de configuration des variables d'environnement
│   ├── requirements.txt      # Dépendances Python
│   └── README.md             # Guide d'installation et de lancement backend
│
├── frontend/                 # Sous-projet Frontend (Vue 3 / Vite / TypeScript)
│   ├── src/
│   │   ├── assets/
│   │   │   └── main.css      # Thème sombre et styles premium Vanilla CSS
│   │   ├── components/
│   │   │   ├── TimetableGrid.vue  # La grille hebdomadaire interactive
│   │   │   ├── Sidebar.vue        # Panneau latéral (cours non placés)
│   │   │   └── HeaderControls.vue # Boutons d'action (Résoudre, Enregistrer)
│   │   ├── services/
│   │   │   └── api.ts        # Client API HTTP
│   │   ├── types/
│   │   │   └── index.ts      # Interfaces TypeScript pour le typage IHM
│   │   ├── App.vue           # Composant racine
│   │   └── main.ts           # Point d'entrée Vue 3
│   ├── index.html
│   ├── package.json          # Dépendances Node.js (Vite, Vue, TS)
│   ├── tsconfig.json         # Configuration TypeScript
│   ├── vite.config.ts        # Configuration du build Vite (proxy API local)
│   └── README.md             # Guide d'installation et de lancement frontend
│
└── specs/                    # Dossiers de spécifications et plan techniques
    └── 001-v1-architecture-slice/
        ├── spec.md           # Spécification fonctionnelle
        ├── plan.md           # Le présent plan technique
        ├── research.md       # Phase 0 : Choix techniques consolidés
        ├── data-model.md     # Phase 1 : Détail des tables & relations
        ├── quickstart.md     # Phase 1 : Guide de démarrage rapide dev
        └── contracts/
            └── api.md        # Phase 1 : Contrats d'interfaces API JSON
```

**Décision de Structure** : Architecture multi-projets (Option 2 du modèle original) isolant proprement le `frontend/` et le `backend/` dans leurs dossiers respectifs, facilitant les démarrages séparés, le cloisonnement des tests et le confinement des dépendances.

---

## 5. Suivi de la Complexité

> *Aucune violation de la constitution n'étant relevée, ce tableau n'est pas applicable.*

---

## 6. Prochaines Étapes Techniques

Pour achever la planification, les livrables suivants sont générés de manière concomitante :
1. **[research.md](research.md)** : Synthèse des choix de technologies et des meilleures pratiques pour FastAPI, SQLAlchemy, Vue 3 et Timefold.
2. **[data-model.md](data-model.md)** : Modèle physique de données SQL pour SQLite/PostgreSQL et schéma des relations.
3. **[contracts/api.md](contracts/api.md)** : Modèles de données d'entrées/sorties JSON pour les points de communication de l'API.
4. **[quickstart.md](quickstart.md)** : Procédure exacte de création du `.venv`, de l'installation de Node, du chargement du jeu de données mocké et de l'exécution des serveurs locaux.
5. **[AGENTS.md](../../AGENTS.md)** : Mise à jour du contexte pour guider l'implémentation.
