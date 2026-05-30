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
  - *Architecture de Validation Duale* : Pour des raisons de performance, lors de la sauvegarde de la solution, le Solveur accède directement aux attributs ORM (Direct Attribute Assignment) et fait un `commit()` brut, sans appeler les méthodes de validation de l'API (ex: `Course.validate_placement_conflicts()`). Celà éviter de vérifier à nouveau en Python une règle métier déjà vérifiée par le solver Timefold (ex: chevauchements, débordement de grille).

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

### D. Abstraction ORM et Validation Métier (`CRUDMixin` & `@constrains`)
Le routeur d'API générique délègue l'intégralité de sa logique de persistance à une classe utilitaire fondamentale : le `CRUDMixin`. Hérité par l'ensemble des modèles SQLAlchemy du projet, ce mixin joue le rôle d'un composant intelligent agissant comme pont entre le JSON brut et l'ORM.

**1. Traitement Intelligent des Payloads (Relations N-à-N)**
- Plutôt que d'assigner manuellement chaque champ, l'API invoque simplement `Model.create(db, payload)` ou `instance.update(db, payload)`.
- Le `CRUDMixin` inspecte dynamiquement la requête. S'il détecte un attribut se terminant par `_ids` (ex: `teacher_ids`), il comprend automatiquement qu'il s'agit d'une relation *Many-to-Many*. Il exécute de lui-même les requêtes pour récupérer les objets cibles et met à jour les liaisons (rattachement ou détachement) sans aucune ligne de code supplémentaire dans les contrôleurs.
  - **Ordre des Collections (Nouveau)** : Si la relation `Many-to-Many` porte la métadonnée `"ordered_by": "sequence_order"` dans son dictionnaire `info`, le `CRUDMixin` respecte scrupuleusement l'ordre des `ids` envoyés par le frontend. Il mettra à jour automatiquement la colonne `sequence_order` de la table d'association `secondary` pour persister cet ordre.

**2. Validation Métier Déclarative (`@constrains`)**
Pour garantir l'intégrité métier des données avant leur enregistrement en base, le `CRUDMixin` intègre nativement un moteur de validation déclaratif (inspiré d'Odoo) qui s'exécute juste avant la fin de l'opération :
- **Déclaration sur le modèle** : Les règles d'intégrité strictes (ex: "impossible de lier deux parties de classe d'une même partition") sont codées sous forme de méthodes directement dans la classe du modèle SQLAlchemy (ex: `ClassPartLink`), annotées avec le décorateur `@constrains("champ_a", "champ_b")`.
- **Exécution automatique** : Lors d'un `.create()` ou d'un `.update()`, le `CRUDMixin` filtre les méthodes annotées par `@constrains`. Si les champs modifiés par le payload font partie de ceux surveillés par le décorateur, la méthode est automatiquement invoquée.
- **Sécurité et Feedback UI** : Si la règle métier est violée, la méthode lève explicitement une `ValueError`. Cette exception remonte jusqu'au gestionnaire de transaction (`get_db`) qui exécute un `db.rollback()` pour annuler l'intégralité des modifications. L'erreur est finalement transmise au frontend sous forme de code `HTTP 400 Bad Request`, affichant le texte de l'erreur directement dans le composant `GenericForm.vue` de l'utilisateur.
- **Génération automatique de relations/données dérivées** : Les méthodes de contraintes ou événements de cycle de vie sont également utilisés pour propager automatiquement des modifications de structure. Par exemple, la création d'une `ClassPart` au sein d'une partition engendre automatiquement la création de liens `ClassPartLink` d'exclusion avec toutes les autres parties de classe des autres partitions de la même division.

### E. Formulaires Réactifs et Pattern `@onchange` (Draft in-memory)
Pour offrir une expérience utilisateur ultra-réactive sans pour autant dupliquer la logique métier entre le frontend et le backend, Klepsydrix implémente un pattern inspiré de l'ORM Odoo : l'évaluation en mémoire des brouillons (Drafts) via le décorateur `@onchange`.

**1. Logique Backend Centralisée**
Les règles de synchronisation des champs (ex: décocher automatiquement "même journée" si l'utilisateur coche "demi-journées d'écart") sont écrites directement sur le modèle SQLAlchemy sous forme de méthodes de classe annotées avec `@onchange('champ_declencheur')`.
- Lorsqu'une modification intervient côté frontend, l'API générique (endpoint `POST /api/generic/{resource}/onchange`) est appelée avec les valeurs brutes du formulaire (le Draft) et le nom du champ modifié.
- Le `CRUDMixin` instancie alors un objet en mémoire (sans aucune transaction en base de données), peuple ses attributs, exécute dynamiquement les méthodes `@onchange` rattachées au champ déclencheur, puis calcule un "diff" des champs qui ont été altérés par la logique métier.
- Ce delta est renvoyé instantanément au frontend.

**2. Synchronisation Frontend Debouncée**
Côté Vue 3 (`GenericForm.vue`), un `watcher` intelligent observe les modifications locales du formulaire (`localModel`). Pour éviter de surcharger le réseau lors d'une saisie rapide, l'appel à l'API `/onchange` est "debouncé" (ex: 250ms). Dès réception de la réponse, le frontend fusionne le diff, ce qui déclenche la mise à jour réactive de l'interface (cases qui se cochent/décochent, valeurs forcées) sans aucun enregistrement manuel de la part de l'utilisateur.

**3. Expressions Dynamiques UI (`readOnlyExpr`, `requiredExpr`, `invisibleExpr`)**
Certains comportements purement visuels (comme griser un champ, rendre sa saisie obligatoire, ou le masquer entièrement si une certaine condition est remplie) ne nécessitent pas un aller-retour avec le backend. Ils sont gérés directement via des expressions JavaScript stockées dans le dictionnaire `info` du modèle Python (sous les clés `readOnlyExpr`, `requiredExpr`, et `invisibleExpr`) ou dans le fichier de structure `ui.json`.
- **Note importante sur le suffixe `*Expr`** : 
  - **Dans les modèles Python (`dict info`)** : L'utilisation des clés suffixées `readOnlyExpr`, `requiredExpr`, `invisibleExpr` est **obligatoire**. Les mots-clés standards `readOnly` et `required` sont strictement typés comme booléens (ou listes) par Pydantic et l'OpenAPI. Y passer une chaîne de caractères (l'expression) ferait crasher la génération du schéma (`500 Internal Server Error`).
  - **Dans le fichier `ui.json`** : Puisque ce fichier n'est pas soumis à la validation stricte de l'OpenAPI, le suffixe `*Expr` est optionnel. Vous pouvez très bien écrire `"readOnly": "model.type === '...'"` ; le frontend (`GenericForm.vue`) est conçu pour détecter que si la valeur de `readOnly` est une chaîne de caractères, il doit l'interpréter comme une expression dynamique.
- Exemple : `"readOnlyExpr": "model.target_subject_a_id !== model.target_subject_b_id"`
- Exemple masquage : `"invisibleExpr": "model.scope !== 'CUSTOM_HALF_DAYS'"`
- Ces expressions sont évaluées de manière sécurisée côté frontend (via `new Function()`) à chaque cycle de rendu pour ajuster l'état visuel et les règles de validation du formulaire en temps réel.

**4. Composants Widgets Spécifiques (ex: `many2many_ordered_list`)**
L'interface `GenericForm.vue` prend en charge l'attribut optionnel `widget` (et `widgetParams`) dans `ui.json` ou dans les informations du modèle.
- **Widget `many2many_ordered_list`** : Conçu spécifiquement pour les champs "Many-to-Many". Ce widget remplace le champ multi-sélection classique par une mini-vue liste. 
  - Il permet de visualiser plusieurs colonnes d'informations en interrogeant la propriété `rawData` injectée côté frontend.
  - Il inclut des contrôles pour **ordonner** les éléments de l'association. Les modifications d'ordre modifient l'ordre du tableau envoyé au backend.
  - Côté backend, grâce à la généricité du `CRUDMixin`, il suffit d'ajouter `"ordered_by": "sequence_order"` dans le dictionnaire `info` du modèle Python pour que ce nouvel ordre soit sauvegardé silencieusement dans la table d'association `secondary`.

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
Dans la base de données, les créneaux temporels (`Timeslots`) sont générés avec une granularité la plus fine possible dans l'application : **par pas de 15 minutes** (ex: 8h00, 8h15, 8h30).
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

---

## 11. Gestion des Transactions et Cycle de Vie (Unit of Work)

Klepsydrix utilise un modèle de transaction lié au cycle de vie de la requête HTTP (**Session per Request** ou **Unit of Work**). Ce mécanisme garantit l'atomicité des opérations : soit l'intégralité des modifications de la base de données effectuées durant une requête HTTP est sauvegardée, soit rien n'est conservé en cas d'erreur.

### A. Le mécanisme d'injection de dépendance (`yield db`)

Dans FastAPI, ce comportement est orchestré par le générateur `get_db()` utilisé comme dépendance (`Depends(get_db)`) dans les routes.

```python
def get_db():
    db = SessionLocal()
    try:
        yield db         # <--- PAUSE ICI pendant l'exécution de la route
        db.commit()      # <--- Exécuté si la route réussit
    except Exception:
        db.rollback()    # <--- Exécuté si la route lève une exception
        raise
    finally:
        db.close()       # <--- Toujours exécuté pour libérer la connexion
```

### B. Cycle de vie détaillé

1. **Avant la route (l'aller)** :
   Lorsqu'une requête arrive, FastAPI exécute `get_db()`. La fonction ouvre une session base de données, entre dans le bloc `try`, et atteint `yield db`.
   À cet instant, la fonction se met en **pause**. L'objet `db` généré est passé en tant que paramètre à la route HTTP (le *endpoint*).

2. **Pendant l'exécution de la route** :
   Le backend exécute sa logique métier. Il utilise `db.add()`, `db.delete()`, ou la méthode ORM `db.flush()` pour envoyer les requêtes SQL préparatoires à la base (ce qui permet d'obtenir les IDs auto-générés ou lever des erreurs d'intégrité précoces). **Aucun `db.commit()` n'est appelé manuellement dans la route.**

3. **Après la route (le retour)** :
   Une fois la route terminée (retour réussi ou levée d'une exception), FastAPI reprend l'exécution de `get_db()` exactement là où il s'était arrêté (juste après le `yield`).
   - **En cas de succès** : Le code continue, exécute le `db.commit()` final pour valider atomiquement toutes les opérations, puis ferme la session dans le bloc `finally`.
   - **En cas d'erreur (Exception)** : FastAPI "injecte" l'erreur déclenchée par la route à l'endroit du `yield`. Cela déclenche immédiatement le bloc `except Exception:`, qui exécute un `db.rollback()` pour annuler l'ensemble des modifications non confirmées, assurant ainsi qu'aucun état partiel n'est enregistré.

### C. Schéma d'exécution

```text
Requête HTTP reçue
       │
       ▼
[1] Exécution de get_db()
    db = SessionLocal()
    yield db ──────────────┐ (pause)
                           │
                           ▼
               [2] Exécution de la route (ex: update_course)
                   course.update(db, vals)
                   return {"status": "success"}
                           │
    ┌──────────────────────┘
    │
    ▼ (reprise)
[3] Si succès : db.commit()
    Si erreur : db.rollback()
    Toujours  : db.close()
       │
       ▼
Réponse HTTP envoyée au client
```

Cette architecture centralisée rend le code des endpoints purement métier, très lisible, et garantit une résilience totale aux pannes inattendues.

---

## 12. Stratégie d'Affectation des Salles et Cours Composés (Timefold)

L'intégration du solveur Timefold au sein de Klepsydrix soulève des défis spécifiques concernant l'affectation des salles (qui est une variable de planification au même titre que les créneaux horaires) et la gestion des cours complexes (Pôle Sciences, Co-enseignement).

### A. Phase de Construction (CH) vs Optimisation (LS)
Timefold procède systématiquement en deux phases :
1. **Construction Heuristic (CH)** : Le solveur construit le premier brouillon de l'emploi du temps en évaluant de manière exhaustive (produit cartésien) chaque créneau horaire et chaque salle pour chaque cours, sans jamais revenir en arrière. En raison de la complexité des contraintes Python (surcoût JPype), cette phase demande un temps incombressable (ex: 20 à 30 secondes).
2. **Local Search (LS)** : Le solveur permute des cours existants pour améliorer le score global.
*Corollaire* : Une limite de temps trop stricte (`SOLVER_TIME_LIMIT_SECONDS=5`) forcera le solveur à s'arrêter en plein milieu de la phase CH, générant un emploi du temps partiellement vide. La limite doit être dimensionnée pour permettre aux deux phases de s'exécuter (ex: 60 secondes).

### B. Mémorisation et Immobilisation des Salles Pré-assignées
Dans Timefold, la variable `classroom` est une `@PlanningVariable`. Par défaut, le solveur a la liberté totale d'écraser une salle saisie manuellement s'il trouve une meilleure optimisation globale.
Pour gérer et protéger le placement manuel des salles tout en laissant de la flexibilité au solveur, deux mécanismes distincts coexistent :

1. **Le Cours est Épinglé (`is_pinned = True` via l'icône de Punaise dans l'IHM)** :
   - L'entité `PlanningCourse` complète est annotée avec `@PlanningPin`.
   - **Comportement** : Le solveur a l'interdiction absolue de modifier cette entité. **Le créneau horaire (`timeslot`) et la salle (`classroom`) sont 100 % gelés** et ne bougeront jamais lors du solving.

2. **Le Cours n'est pas Épinglé, mais possède une Salle Initiale** :
   - Le créneau et la salle servent de point de départ pour la recherche du solveur.
   - **Comportement** : Le solveur a techniquement le droit de modifier la salle pour optimiser le planning. Cependant, nous utilisons une règle d'immobilité :
     - **Mémorisation** : Lors de l'instanciation de `PlanningCourse`, on enregistre la salle initiale dans `original_classroom_id`.
     - **Règle Forte (`classroom_immobility`)** : Une contrainte stricte (Hard Score -100) pénalise toute altération de cette salle. Ainsi, le solveur n'écrasera une salle manuelle que dans une situation extrêmement critique (par exemple pour résoudre une contrainte plus grave), garantissant une très haute stabilité du placement manuel des salles.

### C. Le Modèle des Cours Composés (Optimisation Architecturale)
L'outil a été conçu autour d'une optimisation critique : **seul le cours parent est envoyé au solveur**.
- *Pourquoi ?* Si l'on envoyait les cours enfants au solveur, il faudrait créer de lourdes contraintes forçant leur synchronisation temporelle stricte, ce qui ferait exploser l'espace de recherche (la combinatoire).
- *La limite du modèle* : Un cours parent n'est représenté que par une seule entité `PlanningCourse`, et n'a donc physiquement la place que pour contenir **une seule salle** (`classroom`).
- *La protection BDD* : Les cours composés (ex: Pôle Sciences) ont besoin de plusieurs salles (héritées des enfants). Si le solveur tente de sauvegarder son unique salle, il corrompra la base de données en écrasant la liste des salles du parent. Pour contrer cela, le mécanisme de sauvegarde dans `solver.py` **ignore délibérément l'affectation de salle renvoyée par le solveur si le cours est composé (`if not db_course.is_composed`)**. 
Cette architecture est un choix assumé : elle retire la complexité d'affectation spatiale au solveur pour les cours très complexes (qui sont de toute façon paramétrés manuellement via l'IHM) afin de garantir des performances optimales sur le placement temporel.

---

## 13. Aide au Placement (Interactive Heatmap) & Explicabilité

Pour faciliter l'interaction homme-machine (IHM) et le placement manuel des cours, Klepsydrix intègre une architecture d'évaluation incrémentale en mémoire (Heatmap).

### A. Architecture d'Évaluation en RAM (Stateless)
Lorsqu'un utilisateur sélectionne un cours et active l'Aide au placement, le système doit calculer le score de placement de ce cours sur l'intégralité des créneaux temporels de l'établissement (ex: 120 créneaux). Pour garantir une réponse sous les 100ms :
1. **Aucun `commit` en BDD** : Le backend effectue un "snapshot" de la base de données (une lecture seule via SQLAlchemy) et reconstruit l'objet `PlanningProblem` en RAM.
2. **ScoreDirector Incrémental** : Au lieu de relancer un `Solver` complet, l'API instancie un `ScoreDirector` jetable. Le moteur déplace virtuellement l'entité `Course` d'un créneau à l'autre en RAM, évalue les contraintes incrémentalement (`calculateScore()`), et annule l'opération.

```mermaid
sequenceDiagram
    participant UI as Frontend (TimetableGrid)
    participant API as FastAPI (Heatmap Endpoint)
    participant SD as Timefold ScoreDirector (RAM)

    UI->>API: GET /api/courses/{id}/heatmap
    API->>API: Lecture DB & Construction Problem (RAM)
    API->>SD: Initialisation du ScoreDirector
    loop Pour chaque Timeslot (ex: 120)
        API->>SD: Déplacement virtuel du cours
        SD->>SD: Évaluation incrémentale du Score
        SD-->>API: Hard/Soft Score & ConstraintMatches
    end
    API-->>UI: Dictionnaire des scores par Timeslot
    UI->>UI: Rendu des couleurs (Background Layer)
```

### B. Explicabilité des Contraintes (Tooltips)
Au-delà de la simple couleur (Vert/Orange/Rouge) induite par les scores `Hard` et `Soft`, le système exploite la fonction d'explicabilité (Explainability) native de Timefold.
Le `ScoreDirector` extrait la liste des `ConstraintMatch` (les contraintes enfreintes ou récompensées). L'API filtre cette liste pour ne renvoyer à l'interface que les justifications impliquant explicitement le cours ciblé. L'IHM affiche ces justifications dans des infobulles au survol, transformant un outil purement répressif en un assistant de planification pédagogique.

---

## 14. Gestion des Problèmes Surcontraints (Overconstrained Planning)

Dans la réalité des établissements scolaires, il arrive fréquemment que les contraintes soient contradictoires (ex: volume d'heures d'un enseignant supérieur à ses disponibilités). Plutôt que de bloquer la résolution en renvoyant un échec ou un emploi du temps rempli de conflits durs physiques, Klepsydrix implémente le patron d'**Overconstrained Planning** (Planification surcontrainte).

### A. Variables Nullables (`allows_unassigned`)
La variable de planification `timeslot` de la classe `PlanningCourse` est configurée avec `allows_unassigned=True`. Cela autorise le solveur à laisser la variable à `None` (cours non placé), ce qui se traduit dans l'IHM par un cours dans l'état `UNPLACED` sans créneau horaire associé.

### B. Le Piège du Score Trap (Pénalité Soft vs Hard)
Une implémentation classique de l'Overconstrained Planning consiste à pénaliser la non-assignation dans le score `Soft` (ex: `-1 000 000 Soft`) pour donner une priorité absolue à l'assignation par rapport aux vœux. Cependant, en présence de contraintes `Hard` strictes, cette configuration crée un **piège de score (score trap)** :
* Un cours non placé a un score de `0 Hard / -1 000 000 Soft`.
* Le placer sur un créneau occupé (conflit de professeur) dégrade le score à `-1 Hard / 0 Soft`.
* Les scores `Hard` étant strictement prioritaires sur les `Soft` dans Timefold, le solveur considère `-1 Hard` comme infiniment pire que `0 Hard`. Il refuse donc de faire passer temporairement un cours à l'état conflictuel pour réorganiser l'emploi du temps, ce qui bloque la recherche locale dans un minimum local.

### C. Alignement des Pénalités sur le Score Hard (`ONE_HARD`)
Pour surmonter cette impasse, Klepsydrix applique une pénalité de non-assignation directement dans le score **`Hard`** via la contrainte `penalize_unassigned_course` avec un poids de `1` (`HardSoftScore.ONE_HARD`).

```mermaid
graph TD
    classDef state fill:#f9f,stroke:#333,stroke-width:2px;
    classDef good fill:#bbf,stroke:#333,stroke-width:2px;
    
    A["Non assigné (-1 Hard)"] -->|Transition à coût nul| B("Placé avec Conflit (-1 Hard)")
    B -->|Résolution du conflit| C("Placé sans Conflit (0 Hard)")
    
    class C good;
```

* **Transition en plateau** : Comme la non-assignation et un conflit dur (ex: professeur occupé) coûtent tous deux `-1 Hard`, le solveur peut temporairement placer un cours sur un créneau conflictuel sans dégrader son score Hard. Il effectue ainsi des mouvements horizontaux pour "shuffler" le planning.
* **Résolution** : Une fois le cours positionné, le solveur résout le conflit en décalant le cours gênant vers un créneau libre, élevant le score à `0 Hard` (amélioration acceptée).
* **Résilience** : Si le problème est réellement insoluble, le solveur choisira de laisser le cours non placé (`-1 Hard`) plutôt que de forcer son affectation sur un créneau qui générerait des conflits multiples en cascade (qui cumuleraient un score de `-2 Hard` ou pire).

