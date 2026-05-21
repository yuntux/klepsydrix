# Dossier d'Architecture Logicielle (DAL) : Klepsydrix

**Version** : 1.1.0  
**Statut** : Approuvé  
**Dernière mise à jour** : 2026-05-18  

Ce document décrit l'architecture globale cible du projet Klepsydrix, notre outil open-source d'aide à la conception et d'optimisation d'emplois du temps scolaires. Il sert de cadre technique pour tous les plans d'implémentation spécifiques (`plan.md`).

---

## 1. Vision et Objectifs Architecturaux

Le logiciel Klepsydrix doit résoudre un problème d'optimisation hautement complexe (NP-complet) tout en offrant une réactivité digne d'une application de bureau. 

### Objectifs Clés
- **Performance RAM (In-Memory)** : Le moteur de calcul doit travailler intégralement en mémoire vive pour évaluer des millions de combinaisons par seconde.
- **Fluidité de l'IHM (60 FPS)** : L'interface utilisateur de la grille horaire doit être ultra-réactive et gérer le glisser-déposer sans temps de latence visible.
- **Extensibilité** : Le modèle de données doit être capable d'absorber des structures de cours très complexes (barrettes, alignements, groupes, co-enseignement).

---

## 2. Architecture Globale (3-Tiers Découplée)

Le système est structuré selon un modèle classique découplé en trois couches distinctes :

```mermaid
graph TD
    UI[Frontend: Vue 3 SPA / Vite] <-->|API REST / JSON| API[Backend: FastAPI / Python]
    API <-->|In-Memory RAM Data| Solver[Moteur de calcul: Timefold Solver]
    API <-->|SQLAlchemy ORM| DB[(Persistance: SQLite pour Dev / PostgreSQL Cible)]
```

### A. Couche Présentation (Frontend - SPA)
- **Technologie** : Vue 3 (via Vite) et TypeScript.
- **Styling** : CSS moderne (TailwindCSS) reposant sur un design système premium (thème sombre, Glassmorphism, transitions natives Vue).
- **Rôle** : Rendre la grille horaire interactive, gérer le Drag & Drop côté client pour une manipulation manuelle, et consommer l'API du backend.

### B. Couche Service & Moteur (Backend - API & Solveur)
- **Technologie Backend** : Python (FastAPI).
- **Couche d'Abstraction & Validation** : SQLAlchemy ORM (pour l'accès aux données) et Pydantic (pour la validation des schémas d'API).
- **Rôle API** : Exposer les endpoints REST sécurisés, orchestrer les données et valider les modifications.
- **Moteur d'Optimisation** : Timefold Solver (version Python).
  - *Fonctionnement* : Le backend convertit les données persistées en un graphe d'objets en mémoire (Planning Solution), configure les variables (créneaux et salles) et les contraintes (Hard/Soft), puis délègue la résolution au moteur de recherche locale Timefold.

### C. Couche Données (Persistance)
- **Technologie de Persistance (Développement & V1)** : SQLite (Base locale et légère).
- **Technologie de Persistance (Cible Production)** : PostgreSQL.
- **Rôle** : Assurer la cohérence stricte des données et la persistance à long terme des ressources et des emplois du temps validés. L'utilisation de SQLAlchemy ORM garantit une transition transparente de SQLite vers PostgreSQL en modifiant simplement la chaîne de connexion.

---

## 3. Isolation des Environnements et Containerisation

Pour éviter de polluer le système hôte avec des dépendances globales et garantir la portabilité du projet, Klepsydrix implémente une isolation stricte des environnements de développement.

### A. Backend Python : Environnement Virtuel (`.venv`)
Le backend utilise un environnement virtuel local pour isoler les packages Python :
- **Mécanisme** : Création d'un dossier `.venv` à la racine du sous-projet backend (`python -m venv .venv`).
- **Activation** : `source .venv/bin/activate` (Linux/macOS) pour s'assurer que toutes les dépendances (FastAPI, SQLAlchemy, Timefold) restent confinées localement au projet.

### B. Frontend Vue 3 : Isolation Native via `node_modules`
- **Mécanisme** : Contrairement à Python, l'écosystème Node.js isole **nativement** les dépendances. Lorsque nous exécutons `npm install` (ou `pnpm install`), toutes les dépendances de Vue 3, Vite et TypeScript sont téléchargées exclusivement dans le dossier local `node_modules` à la racine du frontend.
- **Sécurité** : Aucun package n'est installé globalement sur ton OS. Supprimer le dossier `node_modules` suffit à nettoyer entièrement ta machine.

### C. Gestion de la Configuration du Backend (`.env`)
Le backend utilise un système de configuration par variables d'environnement centralisé dans un fichier local.
- **Fichier** : Un fichier `.env` situé à la racine du sous-projet backend (non versionné sur Git pour la sécurité, mais documenté via un modèle `.env.example`).
- **Chargement** : Utilisation de **Pydantic Settings** (`BaseSettings`) pour charger et valider les configurations au démarrage du serveur FastAPI.
- **Variables minimales obligatoires pour la V1** :
  - `DATABASE_TYPE` : Indique le type de moteur SQL (ex: `sqlite` pour le développement, `postgresql` pour la production).
  - `DATABASE_URL` : Chaîne de connexion SQLAlchemy (ex: `sqlite:///./klepsydrix.db` en local, ou `postgresql://user:pass@host/db` en production).

### D. Script d'automatisation unifié (`start_services.sh`)
Pour simplifier les redémarrages de la machine virtuelle (VM) ou de l'environnement de développement, un script d'automatisation complet est disponible à la racine du projet :
- **Chemin** : `./start_services.sh`
- **Fonctionnalités** :
  - `start` : Lance le backend FastAPI et le frontend Vite en tâche de fond, redirigeant les sorties dans `backend.log` et `frontend.log`.
  - `stop` : Arrête proprement les processus écoutant sur les ports standard (`8000` et `3000`).
  - `status` : Affiche l'état des ports et les PIDs des services en cours d'exécution.
  - `logs` : Affiche les 10 dernières lignes de logs pour chaque service.
  - `restart` : Enchaîne un arrêt et un démarrage propre des services.

---

## 4. Flux d'Optimisation de l'Emploi du Temps

Le cycle de vie de la génération d'un emploi du temps suit le flux suivant :

```mermaid
sequenceDiagram
    participant UI as Interface Vue 3
    participant API as Backend FastAPI (SQLAlchemy)
    participant TF as Solveur Timefold
    participant DB as SQLite / PostgreSQL

    UI->>API: Déclenchement de la résolution (POST /solve)
    API->>DB: Lecture des ressources via ORM (profs, salles, cours non placés)
    DB-->>API: Données brutes (Modèles ORM)
    API->>API: Construction du graphe d'entités en RAM (Planning Solution)
    API->>TF: Démarrage de la recherche locale (SolverManager)
    loop Recherche en RAM (2-5 secondes)
        TF->>TF: Évaluation des contraintes (Hard & Soft)
    end
    TF-->>API: Solution optimale calculée
    API->>DB: Écriture et persistance de la solution via ORM
    API-->>UI: Retour du nouvel emploi du temps optimisé (JSON via Pydantic)
    UI->>UI: Rendu fluide instantané de la grille mis à jour
```

---

## 5. Moteur d'API Générique Dynamique et RPC

Pour accélérer le développement et supprimer le code chaudière (boilerplate), Klepsydrix utilise un moteur d'API 100% dynamique et réfléchi dans [generic.py](file:///home/ubuntu/klepsydrix/backend/app/api/generic.py).

### A. Découverte et Cartographie Automatique (MODEL_MAP)
Au démarrage du serveur, tous les modèles Python du dossier `backend/app/models` sont importés dynamiquement via `pkgutil` et `importlib`. Le moteur introspecte ensuite :
1. **Les modèles physiques SQL** : En lisant le registre des mappers de `Base.registry.mappers` et leurs propriétés `__tablename__`.
2. **Les modèles virtuels transitoires (`TransientModel`)** : En découvrant récursivement toutes les sous-classes de `TransientModel` pour les ajouter à la cartographie `MODEL_MAP`.

### B. Schémas Pydantic et Endpoints CRUD Déclarés à la Volée
Pour chaque ressource détectée dans `MODEL_MAP` :
- Le moteur génère dynamiquement deux schémas Pydantic V2 distincts (`CreatePayload` et `UpdatePayload`) via `pydantic.create_model` en introspectant le type de chaque colonne SQL.
- Le moteur enregistre automatiquement auprès de FastAPI les 5 routes CRUD standards (`GET /api/generic/{resource_name}`, `GET /{id}`, `POST`, `PUT`, `DELETE`).
- Les `TransientModel` sont intégrés de manière transparente pour les opérations de lecture (`GET`), mais lèvent automatiquement une exception `405 Method Not Allowed` pour les requêtes d'écriture.

### C. Moteur RPC Générique (Appels de Méthodes)
N'importe quelle méthode métier (de classe ou d'instance) déclarée sur un modèle peut être invoquée directement par le frontend via :
- **Méthodes de classe** : `POST /api/generic/{resource_name}/call/{method_name}`
- **Méthodes d'instance** : `POST /api/generic/{resource_name}/{item_id}/call/{method_name}`

```mermaid
sequenceDiagram
    participant Client as Frontend (Vue 3)
    participant API as generic.py (FastAPI)
    participant Model as Modèle Python (ex: School)
    participant DB as Session SQLAlchemy

    Client->>API: POST /api/generic/schools/1/call/test_instance_method <br> Payload: {"args": [], "kwargs": {"prefix": "Bienvenue"}}
    API->>DB: Récupération de l'instance par ID (1)
    API->>API: Introspection de la signature (inspect.signature)
    Note over API: Détection & Injection de la session 'db' active
    API->>Model: exécution: school.test_instance_method(db=db, prefix="Bienvenue")
    Model-->>API: Retourne le résultat ("Bienvenue à Ecole Test")
    API->>API: Sérialisation récursive (sqla_to_dict)
    API-->>Client: Réponse JSON ("Bienvenue à Ecole Test")
```

- **Injection Automatique de Session** : Le moteur utilise `inspect.signature` pour détecter si la méthode attend l'argument nommé `db` (Session). Si c'est le cas, la session active du pool de connexions est injectée automatiquement.
- **Sérialisation Récursive** : Le résultat de l'exécution est sérialisé dynamiquement (objets SQLAlchemy ou `TransientModel` individuels ou en listes, types primitifs), éliminant le besoin de schémas de sortie codés en dur.

---

## 6. Bibliothèques Frontend Tierces Adoptées

Pour ne pas réinventer la roue, certains composants UI standard sont délégués à des bibliothèques spécialisées et légères, intégrées via `npm`.

### A. `vue3-swatches` — Sélecteur de Couleurs par Palette

| Attribut | Valeur |
|---|---|
| **Package** | `vue3-swatches` v1.2.4 |
| **Usage** | Sélection d'une couleur dans une palette finie prédéfinie |
| **Composant encapsulant** | `frontend/src/components/ColorSwatchPicker.vue` |
| **Utilisé dans** | `GenericList.vue` (cellule éditable en ligne), `GenericForm.vue` (champ de formulaire) |

**Raisonnement** : Plutôt que de maintenir un composant custom fragile (popover, gestion du click-outside, accessibilité), ce package standard offre un widget éprouvé, accessible, et entièrement configurable. Le composant `ColorSwatchPicker.vue` agit comme un adaptateur mince qui pré-configure la palette de 30 couleurs communes et expose une interface `v-model`-compatible (`modelValue` / `@change`) pour s'intégrer sans friction dans le reste de l'application.

```
frontend/src/components/
└── ColorSwatchPicker.vue   ← adaptateur de vue3-swatches (palette 30 couleurs, v-model)
```

---

## 7. Principes de Développement Rattachés
- **Agnosticisme de la spécification** : Les besoins sont écrits sans mentionner cette stack.
- **Liaison avec la Constitution** : Cette architecture respecte scrupuleusement la constitution (Performance in-memory, typage strict, TDD).
- **Pas de réinvention de la roue** : Tout widget UI standard doit d'abord être recherché sous forme de package npm maintenu, avant d'envisager une implémentation maison.

---

## 8. Intégration des Contraintes Réglementaires (Enseignants & Divisions) dans Timefold

Nous avons modélisé et intégré l'ensemble des contraintes administratives et réglementaires des enseignants et des divisions (classes) au sein du solveur **Timefold**.

### A. Aperçu de l'Architecture

Pour maintenir la compatibilité générique et maximiser les performances de calcul, ces règles sont modélisées comme des **Faits de Problème** (Problem Facts) statiques au sein du solveur, chargés dynamiquement à partir de la base de données.

```mermaid
graph TD
    DB[(Base de données : ResourceConstraint)] -->|Chargé dans solver.py| PT[PlanningTimetable]
    PT -->|Collection de Faits| PC[PlanningResourceConstraint]
    PC -->|Évalué dans constraints.py| TF[Timefold Constraint Factory]
    TF -->|Pénalités de Score| HS[HardSoftScore]
```

### B. Contraintes Intégrées

Chaque contrainte est analysée de manière dynamique et évaluée à l'aide d'opérations d'ensembles Python hautement optimisées (via `to_set()`) pour rester 100% conforme aux types Python natifs et contourner toutes les limitations de conversion de types JVM lors de l'exécution.

#### 1. Réglementations des Enseignants
* **Limites d'Heures Journalières (`max_hours_per_day`)** : Le nombre total de sessions planifiées par jour ne doit pas dépasser la limite personnalisée de l'enseignant.
* **Limites d'Heures Matin / Après-midi (`max_hours_per_am` / `max_hours_per_pm`)** : Restreindre le volume horaire du matin (heure < 12) ou de l'après-midi (heure >= 12) sur chaque journée.
* **Limitation à une Demi-Journée (`only_one_half_day_per_day`)** : Interdiction stricte de travailler à la fois le matin et l'après-midi le même jour.
* **Heures de Début Tardif / Fin Anticipée (`late_start_limit` / `early_end_limit`)** : Imposer des restrictions d'heures limites de début ou de fin de journée sur la semaine.
* **Jours de Présence & Libérés (`max_presence_days` / `min_free_days`)** : Garantir le respect des quotas contractuels de jours travaillés et de jours libres.
* **Demi-Journées Travaillées (`max_worked_am` / `max_worked_pm`)** : Limiter le nombre total de matinées ou d'après-midi travaillés par semaine.

#### 2. Réglementations des Divisions
* **Limites d'Heures Journalières (`max_hours_per_day`)** : Encadrement de la charge de cours quotidienne totale subie par une classe.
* **Volume Horaire Matin / Après-midi (`max_hours_per_am` / `max_hours_per_pm`)** : Équilibrage standardisé des heures sur les demi-journées.

---

### C. Modèle d'Implémentation Technique

#### 1. Fait de Planification `PlanningResourceConstraint`
Nous avons introduit un fait de planification générique mappé directement sur le modèle ORM `ResourceConstraint`, évitant ainsi toute duplication de code :

```python
@dataclass
class PlanningResourceConstraint:
    id: int
    resource_type: str
    resource_id: typing.Optional[int]
    # Attributs réglementaires...
```

#### 2. Exposition des Faits via `PlanningTimetable`
La classe `@planning_solution` porte désormais la collection complète :
```python
resource_constraints: Annotated[List[PlanningResourceConstraint], ProblemFactCollectionProperty] = field(default_factory=list)
```

#### 3. Formulation de Contraintes Python Ultra-Optimisées
En utilisant `to_set()` sur le flux `UniConstraintStream` (avant de joindre les contraintes), nous obtenons des évaluations élégantes, extrêmement rapides et totalement sécurisées contre les conflits de types JPype :

```python
def teacher_late_start_limit(constraint_factory: ConstraintFactory) -> Constraint:
    return (
        constraint_factory.for_each(PlanningCourse)
        .filter(lambda course: course.timeslot is not None and course.teacher is not None)
        .group_by(
            lambda course: course.teacher,
            ConstraintCollectors.to_set(lambda course: course.timeslot)
        )
        .join(
            PlanningResourceConstraint,
            Joiners.equal(lambda teacher, timeslots_set: "Teacher", lambda rc: rc.resource_type),
            Joiners.equal(lambda teacher, timeslots_set: teacher.id, lambda rc: rc.resource_id)
        )
        .filter(lambda teacher, timeslots_set, rc: rc.late_start_time is not None and rc.late_start_days_per_week is not None)
        .filter(lambda teacher, timeslots_set, rc: len({ts.day_of_week for ts in timeslots_set if ts.hour < int(rc.late_start_time.split(':')[0])}) > (5 - rc.late_start_days_per_week))
        .penalize(
            HardSoftScore.ONE_HARD,
            lambda teacher, timeslots_set, rc: (len({ts.day_of_week for ts in timeslots_set if ts.hour < int(rc.late_start_time.split(':')[0])}) - (5 - rc.late_start_days_per_week)) * 10
        )
        .as_constraint("Teacher late start limit")
    )
```

---

## 9. Stratégie de Test et Prévention des Régressions (Timefold & Core)

La validation de la traduction du modèle en contraintes et la communication avec **Timefold** reposent sur une suite de tests unitaires et d'intégration très robuste et structurée, localisée dans `test_solver.py`.

Voici comment ces tests sont organisés pour garantir une non-régression absolue :

### A. Isolation Totale en Mémoire Vive (SQLite RAM)
Pour éliminer les effets de bord et garantir des temps d'exécution extrêmement rapides, les tests n'utilisent pas la base de données physique.
* Une base de données **SQLite en mémoire** (`sqlite:///:memory:`) est instanciée à chaque test.
* Une fixture pytest (`db_session`) s'occupe de créer les tables à blanc, d'injecter les données de socle obligatoires (structure de l'établissement, matières, disciplines) et de purger intégralement la mémoire après chaque exécution.

### B. Typage et Traduction Fidèle des Modèles en Faits
Chaque test simule le flux complet de production d'un emploi du temps :
* **Étape 1 (Base de données ORM)** : Insertion d'objets standard via SQLAlchemy (`Teacher`, `ResourceConstraint`, `Course`, etc.).
* **Étape 2 (Mapping de Faits de Planification)** : Appel à `_solve_timetable_job` qui exécute `_build_planning_problem` (dans `solver.py`). C'est cette fonction qui extrait les données et instancie les objets Python intermédiaires (`PlanningCourse`, `PlanningResourceConstraint`).
* **Étape 3 (Résolution Timefold)** : Lancement du solveur en mémoire et évaluation des règles par le Constraint Factory.
* **Étape 4 (Écriture & Assertions)** : Rechargement des objets persistés et assertions mathématiques sur le résultat final.

### C. Les Différents Scénarios Validés
* **Résolution de Base (`test_solver_resolves_timetable`)** : Garantit que deux cours partageant le même professeur ou la même division (classe) ne peuvent jamais être positionnés sur le même créneau horaire (règle dure de non-superposition).
* **Gestion des Liens de Groupes et Alternances de Semaines (`test_solver_group_link_and_week_alternation`)** :
  * Valide que des sous-groupes exclus (`ClassPartLink`) ne peuvent pas être planifiés en même temps.
  * Valide que si deux cours sont alternés (ex : Semaine A et Semaine B), ils peuvent coexister sur le même créneau horaire sans conflit.
* **Respect des Vœux et Préférences (`test_solver_respects_preferences`)** : S'assure que le solveur récompense le positionnement sur les créneaux préférés (`Preferred`) et évite les créneaux inadaptés (`Unsuited`).
* **Arbitrage de Score (`test_solver_preference_overrides_stability`)** : Valide la hiérarchie des scores (Soft Score) : un vœu d'enseignant (+10 soft) doit l'emporter sur la pénalité de stabilité (-1 soft) pour déplacer un cours.

### D. Taux de Couverture et Mesures Spécifiques
La couverture de code (Backend total à **88 %**) démontre l'excellence de la conception de la suite de tests :
* **`constraints.py`** : **98 %** de couverture de code (la totalité des fonctions et règles d'évaluation).
* **`solver.py`** : **79 %** de couverture de code (alimentation et instanciation du solveur).

> [!NOTE]
> **Limite technique de mesure JPype (JVM/Python)** : La fonction `weeks_overlap` ou d'autres petits segments exécutés au sein des threads d'arrière-plan natifs gérés par la Machine Virtuelle Java (JVM) ne sont pas toujours traçables par le traceur standard Python (`coverage.py` via `sys.settrace`), car les callbacks sont invoqués directement par la JVM. Ils sont néanmoins exécutés avec succès et testés de bout en bout par la suite d'assertions logiques.

### E. Pourquoi ce système protège efficacement votre application
* **Détection immédiate des régressions JVM/JPype** : Si un type de données converti en Python (par exemple via `to_set()`) n'était pas supporté par le moteur Java sous-jacent, le test lèverait immédiatement une erreur d'invocation de signature JPype.
* **Rapidité** : La totalité des résolutions unitaires s'exécute en moins de 20 secondes grâce à la configuration RAM.

---

## 10. Gestion du Temps et Granularité de la Grille

Le système opère une distinction fondamentale entre le stockage des créneaux temporels (Timeslots) et leur utilisation par le solveur afin de conjuguer flexibilité et performance.

### A. Stockage BDD : Finesse maximale (15 minutes)
Dans la base de données, les créneaux temporels (`Timeslots`) sont générés avec une granularité extrêmement fine (par pas de 15 minutes, ex: 8h00, 8h15, 8h30).
**Objectifs de cette architecture :**
- **S'adapter aux changements de configuration** : Si un établissement passe d'une grille de 30 minutes à 15 minutes, l'application fonctionne instantanément sans nécessiter de lourdes migrations de base de données.
- **SaaS et Multi-établissement (Cité Scolaire)** : Un collège et un lycée partageant la même base peuvent avoir des sonneries décalées (ex: 8h00 pour le lycée, 8h15 pour le collège). Le socle de données universel de 15 minutes couvre les deux.
- **Saisie précise des vœux** : Permettre aux professeurs de saisir des indisponibilités très granulaires (ex: "indisponible de 8h15 à 8h30") qui nécessitent l'existence physique du créneau élémentaire dans la base pour y rattacher la contrainte.

### B. Solveur : Filtrage par le Pas de la Grille (STANDARD_TIMESLOT_DURATION)
Avant de lancer le calcul d'optimisation, le solveur filtre les créneaux récupérés depuis la base pour ne conserver que ceux qui respectent la configuration de l'établissement (`STANDARD_TIMESLOT_DURATION`, ex: 30 minutes).
**Objectif : Contrôle de l'explosion combinatoire.**
Le solveur réduit drastiquement le champ des possibles en n'autorisant les cours à démarrer qu'à des heures rondes (8h00, 8h30, 9h00...). S'il devait évaluer chaque point de départ possible toutes les 15 minutes, le temps de calcul augmenterait de manière exponentielle.

### C. Découplage entre Heure de Début et Durée Réelle
Il ne faut pas confondre le pas de la grille (les heures de début autorisées) et la durée d'un cours une fois celui-ci démarré.
- **Pas de la grille (`STANDARD_TIMESLOT_DURATION`)** : Détermine les points d'ancrage possibles (ex: démarrage autorisé à 8h00, 8h30).
- **Durée réelle du cours (`c.duration_minutes`)** : Communiquée individuellement au solveur sous forme d'une variable `step` en heures (ex: `55 / 60.0 = 0.916`). Ainsi, un cours démarrant à 8h00 durera mathématiquement jusqu'à 8h55 pour le solveur, ce qui lui permettra de détecter précisément les chevauchements et conflits sans se laisser tromper par la taille des créneaux sous-jacents.
