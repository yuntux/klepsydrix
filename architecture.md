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

**Polymorphisme plutôt que branchement par type (`if issubclass(model, TransientModel)`)** : les endpoints génériques (`generic.py`) ne testent jamais le type concret du modèle pour décider quoi faire — ils appellent uniformément `model.read()`, `model.count()`, `model.clean_payload()`, `model.create()`/`instance.update()`/`instance.delete()`, et laissent chaque classe fournir sa propre implémentation :
- `CRUDMixin` (modèles réels) implémente ces méthodes avec de vraies requêtes SQL.
- `TransientModel` fournit ses propres versions : `count()` retombe sur `len(read(...))`, `clean_payload()` renvoie le payload tel quel (pas de colonne SQL à typer), et `create()`/`update()`/`delete()` lèvent `UnsupportedOperationError` — que `generic.py` traduit en `405` (à distinguer du `400` générique réservé aux erreurs de validation métier `ValueError`).
- **Limite connue, acceptée** : `update`/`delete` sur un `TransientModel` dont `read()` exige un domaine précis (ex: `TrmdSynthesis`, qui exige `school_id`) renvoient `404` ("introuvable") plutôt que `405` ("non supporté") si l'enregistrement n'est pas trouvable sans ce domaine — l'endpoint cherche l'enregistrement par `id` seul avant d'appeler `update()`/`delete()`, qui ne sont donc jamais atteints pour lever `UnsupportedOperationError`. Non corrigé délibérément : `trmd_syntheses` est le seul `TransientModel` du projet et n'est appelé nulle part dans le frontend (aucun menu, aucun composant) — corriger un code HTTP sur un chemin inatteignable en pratique ne justifiait pas le code supplémentaire (une méthode `supports_write()` sur les deux classes + deux gardes dans `generic.py`, testée puis retirée après discussion).
- Le filtre `?ids=1,2,3` (section 15.L) est lui aussi devenu générique à ce niveau : une valeur liste sur la clé `"id"` d'un `domain` est reconnue comme un `IN(...)` par `CRUDMixin._apply_domain`, au lieu d'une branche dédiée dans l'endpoint liste.

Seul le point d'entrée `make_pydantic_model` (génération du schéma OpenAPI, section B) garde un test de type explicite : il n'a pas de colonnes SQL à introspecter pour un `TransientModel`, ce qui est une différence structurelle (schéma vs CRUD à l'exécution), pas la même préoccupation.

**Nullabilité réelle vs. "Optional" du schéma (piège du bouton "effacer")** : `make_pydantic_model` enveloppe en `Optional[type]` tout champ possédant un default Python (pour permettre son omission d'un payload de mise à jour partiel), y compris des colonnes SQL déclarées `nullable=False` avec `default=0` (ex: `Service.weekly_duration_split_minutes`). Le JSON Schema résultant (`anyOf: [type, null]`) ne dit donc **pas** si `null` est une valeur de domaine valide — seulement si le champ peut être omis. Pour cette information réelle, chaque propriété de colonne porte désormais un champ `nullable` distinct, copié directement depuis `column.nullable` (pas déduit du wrapping `Optional`). Le frontend (`App.vue::getFormFieldsConfig`) le propage sur chaque définition de champ et les widgets `SearchableSelect.vue`/le `<select>` natif de `GenericForm.vue` n'affichent leur option/bouton "effacer" (→ `null`) que si `field.nullable !== false` — un champ non-nullable n'expose que ses vraies options (ex: l'entrée "Aucune" à `0` injectée par `get_duration_options(include_zero=True)`), qui est sa véritable représentation d'"absence" au niveau métier.

Côté écriture, `CRUDMixin.clean_payload(payload_dict, allow_null=False)` ignore par défaut toute valeur `None` du payload (utile en création : laisser les defaults SQL s'appliquer). `make_update_endpoint` appelle `clean_payload(..., allow_null=True)` : les éditeurs génériques (édition en ligne de `GenericList.vue`, formulaire de `GenericForm.vue`) renvoient l'enregistrement complet, donc un champ que l'utilisateur vient d'effacer arrive à `None` dans ce payload précis — le filtrer silencieusement rendait le bouton "×" inopérant sans aucun retour visible. Avec `allow_null=True`, ce `None` atteint réellement `instance.update()` ; s'il cible une colonne `NOT NULL`, l'`IntegrityError` SQL remonte normalement en `400` — un vrai message d'erreur plutôt qu'un silence trompeur, filet de sécurité pour tout champ dont le frontend aurait, par erreur, quand même proposé l'effacement.

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
- **Piège découvert : un `create()` surchargé qui ne passe jamais par `CRUDMixin.create()` ne déclenche JAMAIS `@constrains`** (`ResourcePreference.create()`, `backend/app/models/preference.py`, voir `attribution_week_type_auto.md` Échange 9). Certains modèles ont une logique de création trop spécifique pour la boucle générique (ici : upsert, scission et fusion de plages A/B/W en une grille de préférences) — leur `create()` construit alors les instances `cls(...)` directement et fait `db.add()`/`db.flush()` sans jamais appeler `super().create()`. Comme le dispatch `@constrains` vit *dans* `CRUDMixin.create()`/`update()`, un tel `create()` personnalisé ne le traverse jamais : une règle purement déclarée en `@constrains` y reste silencieusement lettre morte, sans erreur ni avertissement à l'écriture de la méthode. Le correctif générique n'est pas d'éviter ce pattern (l'upsert/scission reste le plus clair pour ce cas), mais de **valider explicitement en tête d'un tel `create()` personnalisé**, en plus (pas à la place) du `@constrains` classique qui continue de couvrir `update()` — une méthode statique partagée entre les deux évite la duplication de la règle elle-même. Avant de faire confiance à un `@constrains` sur un modèle donné, vérifier que son `create()` (s'il est surchargé) appelle bien `super().create()` quelque part.

### E. Formulaires Réactifs et Pattern `@onchange` (Draft in-memory)
Pour offrir une expérience utilisateur ultra-réactive sans pour autant dupliquer la logique métier entre le frontend et le backend, Klepsydrix implémente un pattern inspiré de l'ORM Odoo : l'évaluation en mémoire des brouillons (Drafts) via le décorateur `@onchange`.

**1. Logique Backend Centralisée**
Les règles de synchronisation des champs (ex: décocher automatiquement "même journée" si l'utilisateur coche "demi-journées d'écart") sont écrites directement sur le modèle SQLAlchemy sous forme de méthodes de classe annotées avec `@onchange('champ_declencheur')`.
- Lorsqu'une modification intervient côté frontend, l'API générique (endpoint `POST /api/generic/{resource}/onchange`) est appelée avec les valeurs brutes du formulaire (le Draft) et le nom du champ modifié.
- Le `CRUDMixin` instancie alors un objet en mémoire (sans aucune transaction en base de données), peuple ses attributs, exécute dynamiquement les méthodes `@onchange` rattachées au champ déclencheur, puis calcule un "diff" des champs qui ont été altérés par la logique métier.
- Ce delta est renvoyé instantanément au frontend.

### F. Mécanisme des Actions Personnalisées (`__actions__`)
Klepsydrix permet d'enrichir les interfaces génériques (`GenericForm.vue`, `GenericList.vue`) en injectant des boutons d'actions contextuels directement pilotés par le modèle backend.

**Déclaration sur le modèle**
L'attribut de classe `__actions__` définit la liste des actions disponibles pour la ressource. L'API générique lit cet attribut et l'envoie au frontend en même temps que le schéma.
```python
    __actions__ = [
        {
            "id": "compose_course",
            "label": "Décomposer le cours",
            "type": "wizard",
            "component": "CourseCompositionWizard",
            "icon": "fa-sitemap",
            "condition": "record.is_composed === true && record.status !== 'COMPLETELY_PLACED'"
        }
    ]
```

**Types d'actions supportées**
- **Type `api`** : Déclenche un appel RPC asynchrone vers une méthode backend d'instance via l'endpoint générique `POST /api/generic/.../call/{id}`. C'est idéal pour un bouton d'action simple ("Valider", "Générer", etc.).
- **Type `wizard`** : Ouvre une modale contenant soit un composant Vue.js bespoke (déclaré via `component`, échappatoire pour un besoin qui ne rentrerait pas dans le moule générique), soit — cas par défaut quand `component` est absent — `GenericWizard.vue`, piloté par une liste `steps` déclarée sur l'action elle-même. Voir section 15.M pour le détail du mécanisme `steps`.

**Affichage dynamique (Condition)**
La clé `condition` accepte une expression JavaScript brute. Le frontend l'évalue dynamiquement à chaque rendu (via une sandbox basique) en lui passant l'état actuel du `record`. Cela permet d'afficher ou de cacher instantanément un bouton selon les valeurs du formulaire (ex: afficher le bouton uniquement si le cours est composé et non placé).

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

- **Mode association (`widgetParams.pickResource`)** : Extension du même widget pour les relations One-to-Many pointant vers un **objet de liaison possédé** (ex: `MefDivision`, qui porte ses propres attributs comme `forecast_student_count`), par opposition à une vraie relation `secondary=` où l'on rattache des lignes déjà existantes. Contrairement au mode standard, il n'existe ici aucune ligne "libre" à sélectionner : chaque ligne appartient dès sa création à l'enregistrement parent.
  - Déclenché dès que `widgetParams.pickResource` est renseigné (ex: `"mefs"`) : le sélecteur "Ajouter" interroge alors ce `pickResource` (au lieu des options de la relation elle-même) et exclut les éléments déjà liés.
  - `widgetParams.parentField` / `widgetParams.pickField` indiquent respectivement la clé étrangère vers le parent (ex: `division_id`) et vers l'élément choisi (ex: `mef_id`) à envoyer lors de la création.
  - **Ajouter** déclenche un `POST` direct sur la ressource de la relation (ex: `/api/generic/mef_divisions`), créant immédiatement une nouvelle ligne — pas un simple ajout dans le tableau en attente de l'enregistrement du formulaire parent.
  - **Retirer** déclenche un `DELETE` immédiat de la ligne (et non un simple détachement), car la ligne n'a pas d'existence en dehors de cette association.
  - Une colonne peut être marquée `"editable": true` : elle se rend alors comme un champ `<input>` et déclenche un `PATCH` direct sur la ligne au changement (ex: la saisie de l'effectif prévu), indépendamment du bouton "Enregistrer" du formulaire parent.
  - **Invalidation du cache FK après écriture directe** : puisque `Ajouter`/`Retirer`/l'édition de colonne écrivent directement sur `field.resource` (ex: `mef_services`) en dehors du cycle de soumission du formulaire parent, ce dernier n'invalide jamais ce cache (il n'invalide que sa propre ressource, ex: `mefs`). Le widget émet donc lui-même un `window.dispatchEvent(new CustomEvent('resource:mutated', { detail: { resource_name: field.resource } }))` après chaque écriture réussie ; le listener global dans `App.vue` (`onMounted`) invalide alors systématiquement `fkOptionsCache`/le cache TanStack Query de cette ressource. Sans ce signal, tout consommateur de `fkOptionsCache[resource]` (y compris le repli `field.options` du widget lui-même pour les lignes pas encore éditées dans la session en cours) affiche des données périmées jusqu'au prochain changement de menu actif — un bug réel rencontré et corrigé sur le widget "Services MEF".
  - Exemple (`Division.mef_links`, dans `backend/app/models/division.py`) :
    ```python
    info={
        "widget": "many2many_ordered_list",
        "widgetParams": {
            "pickResource": "mefs",
            "pickField": "mef_id",
            "parentField": "division_id",
            "columns": [
                {"key": "mef_id", "label": "MEF"},
                {"key": "forecast_student_count", "label": "Effectif prévu", "editable": True},
                {"key": "computed_student_count", "label": "Effectif calculé"}
            ]
        }
    }
    ```

### G. Garde-fou de Réentrance sur Cascades ORM (drapeau ambiant sur `db`, pendant du contexte Odoo)
Certains `@constrains` (section D) déclenchent, en cascade, des écritures sur d'AUTRES enregistrements du même modèle (ex: propager une modification vers des enregistrements liés). Or ces écritures repassent elles-mêmes par `create()`/`update()`/`delete()`, donc redéclenchent potentiellement le même `@constrains` — boucle infinie, ou pire, un calcul dérivé exécuté sur un état intermédiaire (incomplet) d'une cascade encore en cours plutôt que sur son état final.

**1. Le mécanisme : un attribut dynamique posé sur l'objet `Session`**
Python autorise à poser n'importe quel attribut sur n'importe quel objet — `db._nom_du_drapeau = True` fonctionne sans déclaration préalable, purement en mémoire. Puisque `db` (la `Session` SQLAlchemy) est déjà systématiquement passée en paramètre à chaque `create()`/`update()`/`delete()`/méthode `@constrains` de ce code, l'accrocher directement dessus évite d'introduire un second paramètre de contexte partout :
```python
def _fonction_sensible_a_la_reentrance(db: Session, ...):
    if getattr(db, "_drapeau", False):
        return  # une cascade équivalente est déjà en cours plus haut dans la pile
    db._drapeau = True
    try:
        ...  # écritures qui peuvent redéclencher cette même fonction, en toute sécurité
    finally:
        db._drapeau = False
```
Le `try`/`finally` garantit que le drapeau retombe même si une exception interrompt la cascade.

**2. Portée : la durée de vie de `db`, jamais partagée entre utilisateurs**
`get_db()` (`backend/app/core/database.py`) crée une instance de `Session` **par requête HTTP** et la détruit à la fin (`finally: db.close()`). Le drapeau ne vit donc que le temps d'une requête, sur l'objet `db` de cette requête précise — deux utilisateurs (ou deux onglets) travaillant en parallèle ont chacun leur propre `db`, donc leur propre drapeau, sans aucune interférence possible. C'est l'équivalent fonctionnel du dictionnaire de contexte d'Odoo (`self.env.context`), lui-même scopé à l'`Environment`/transaction courante — la différence est le support : Odoo transporte un `context` explicite en paramètre de chaque appel ORM, alors qu'ici on réutilise `db`, déjà omniprésent, plutôt que d'ajouter un paramètre dédié partout.

**3. Variante : identifiant plutôt que booléen, pour de la réentrance imbriquée mais distincte**
Un simple booléen bloque *toute* réentrance, y compris légitime (ex: une cascade sur le service A qui doit normalement continuer à déclencher un traitement sur un service B différent). Quand il faut distinguer "je suis en train de traiter CET enregistrement précis" de "un traitement quelconque est en cours ailleurs", on stocke un identifiant plutôt qu'un booléen, avec sauvegarde/restauration de la valeur précédente (pile implicite via une variable locale) :
```python
if getattr(db, "_traitement_en_cours_pour_id", None) == self.id:
    return
precedent = getattr(db, "_traitement_en_cours_pour_id", None)
db._traitement_en_cours_pour_id = self.id
try:
    ...
finally:
    db._traitement_en_cours_pour_id = precedent
```
Ceci autorise un traitement imbriqué sur un AUTRE enregistrement (id différent) à s'exécuter normalement, tout en bloquant la boucle immédiate sur le même enregistrement.

**4. Piège associé : ne pas laisser un recalcul dérivé s'exécuter sur un état intermédiaire**
Quand une cascade fait plusieurs écritures successives (ex: supprimer puis recréer plusieurs lignes liées) et qu'une fonction dérivée dépend de l'ENSEMBLE de ces lignes, la garder « auto-déclenchée » à chaque écriture individuelle expose des états transitoires incomplets (ex: 0 ligne juste après la suppression, 1 ligne sur 2 après la première recréation). La garde de réentrance suffit à éviter la boucle infinie, mais pas ce problème-là : il faut en plus **suspendre totalement** le recalcul dérivé pendant toute la durée de la cascade, puis l'appeler explicitement **une seule fois**, une fois la cascade stabilisée — plutôt que de compter sur ses déclenchements automatiques.

**Implémentation de référence** : `_sync_aligned_repartitions` / `_recompute_service_weekly_durations` (`backend/app/models/service.py`) combinent les trois techniques ci-dessus — garde par identifiant (`db._weekly_duration_sync_service_id`) pour la réentrance directe, garde booléenne (`db._syncing_alignment_repartitions`) pour suspendre un recalcul dérivé pendant toute une cascade multi-écritures, puis appel explicite unique de ce recalcul une fois la cascade terminée.

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

### C. Couplage Strict entre le Pas de la Grille et la Durée
Contrairement à une approche libre, Klepsydrix impose un couplage fort entre le pas de la grille de l'établissement et la durée réelle des cours pour garantir la stabilité algorithmique, notamment lors des décompositions complexes (barrettes, chevauchements).
- **Pas de la grille (`STANDARD_TIMESLOT_DURATION`)** : Détermine la taille des blocs de construction de l'emploi du temps (ex: 5, 10, 15, 30 ou 60 minutes).
- **Durée réelle du cours (`c.duration_minutes`)** : Doit obligatoirement être un **multiple exact** du pas de la grille. Par exemple, avec un pas de 60 minutes, un cours peut durer 60, 120, ou 180 minutes, mais pas 90. Cette règle assure que chaque cours occupe un nombre entier de "créneaux de base", permettant au solveur d'utiliser des matrices d'occupation binaires et garantissant l'intégrité des découpages (offsets entiers) lors des compositions mathématiques (ex: Modes 3 et 4).

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

### D. Résolution de l'Alternance A/B pour les Cours "Q" (Phase C)

Le `week_type` (`A`/`B`/`W`/`Q`, voir `attribution_week_type_auto.md`) peut être résolu automatiquement par le solveur, en plus du placement manuel par glisser-déposer (§ ci-dessous, IHM), aussi bien pour un cours simple qu'un cours composé. Ceci s'appuie sur une capacité Timefold jusqu'ici inutilisée dans le projet : le **`ValueRangeProvider` à portée ENTITÉ**.

- **Différence avec `timeslotRange`/`classroomRange`** : ces derniers sont déclarés une seule fois, au niveau de `PlanningTimetable` (`@planning_solution`), et partagés par tous les `PlanningCourse` — l'espace de valeurs possibles est identique pour chaque cours. Pour `week_type`, l'espace de valeurs légales dépend de CE cours précis (un cours en semaine `W` n'a par définition aucune raison de pouvoir devenir `A`/`B`, voir `spec.md`). Timefold permet de déclarer un `ValueRangeProvider(id=...)` directement sur un champ *stocké* de l'entité elle-même (`week_type_range: Annotated[List[str], ValueRangeProvider(id='weekTypeRange')]`, dans `PlanningCourse`, `backend/app/solver/constraints.py`), peuplé à la construction — chaque instance a alors son propre range. **Vérifié par un spike dédié** (deux scripts autonomes exécutés directement contre le `timefold` réel du projet, 1.24.0b0) avant toute implémentation : (1) le mécanisme fonctionne bien via un champ stocké — PAS une méthode/`@property` calculée (`@ValueRangeProvider(...)` sur une méthode lève `TypeError: 'ValueRangeProvider' object is not callable`, ce n'est pas un décorateur) ; (2) le type doit être un générique paramétré (`List[str]`, pas `list` nu — sinon `IllegalArgumentException: ... has no generic parameters` côté JVM) ; (3) `@PlanningPin` gèle une variable à portée entité exactement comme les variables à portée globale, sans code additionnel.
- **Calcul du range** (`_build_planning_problem`, `backend/app/solver/solver.py`) : tout cours — simple OU composé — dont le `week_type` BDD (`c.week_type`, agrégat `_sync_parent_week_type` pour un composé) vaut `A`, `B` ou `Q` reçoit `week_type_range = ["A", "B"]`. Seul `W` reste singleton (`["W"]`) — jamais de choix, comportement identique à avant cette phase. Ceci ne distingue plus `is_composed` : la règle `_sync_parent_week_type` (§ ci-dessous, `course.py`) garantit qu'un parent composé n'affiche `A`/`B`/`Q` QUE si TOUS ses enfants partagent uniformément cette même valeur — un cours composé porte donc, exactement comme un cours simple, une ambiguïté A/B réellement résoluble par le solveur dès que son agrégat n'est pas `W`.
- **Valeur de départ** : `None` pour un cours `Q` (comme `timeslot`/`classroom`), sa valeur actuelle pour un cours déjà résolu `A`/`B` (point de départ naturel pour la recherche, comme pour `classroom` § B ci-dessus — rien n'empêche pour autant le solveur de la faire basculer si c'est meilleur). Important : la valeur de départ doit toujours être `None` ou un membre du range déclaré — une valeur hors range (ex: laisser `"Q"` alors que le range est `["A","B"]`) n'est pas reprise en compte par le solveur et peut y rester bloquée indéfiniment.
- **`_sync_parent_week_type` (`course.py`)** : le parent remonte en `W` en cas de vrai conflit (un enfant `W`, ou à la fois un enfant `A` et un enfant `B`) ; s'il n'y a pas de conflit et que tous les enfants partagent exactement `A` (ou exactement `B`), le parent prend cette valeur ; dans tous les autres cas (tous `Q`, ou un mélange `A`+`Q`, ou `B`+`Q`), le parent est `Q` (voir `spec.md`, tableau de vérité complet). Un parent `Q` peut donc regrouper des enfants déjà individuellement résolus (`A` ou `B`) aux côtés d'enfants encore `Q` : la cascade ci-dessous peut alors faire basculer un enfant déjà résolu si c'est la lettre retenue pour l'ensemble du groupe.
- **Écriture en retour et cascade** (`_solve_timetable_job`) : `db_course.week_type = pc.week_type` pour le cours de premier niveau (vérifié empiriquement que SQLAlchemy coerce correctement une chaîne Python brute vers la colonne `Enum(CourseWeekType, ...)`). Pour un cours **composé**, la lettre résolue est ensuite reportée à tous les enfants — même boucle que la cascade de `timeslot_id` déjà existante (`for child in db_course.children: ...`) — mais uniquement si le `week_type` du parent a changé pendant le solving (comparaison avec sa valeur avant écriture, capturée juste avant). Un cours composé resté stable (déjà sur sa lettre) ne touche donc jamais ses enfants.

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

---

## 15. Architecture Frontend (Performance et Design System)

Le frontend a été réarchitecturé pour garantir des performances d'affichage (60 FPS) même avec de gros volumes de données, tout en réduisant la dette technique.

### A. Gestion d'État Centralisée (Pinia)
Les ressources métiers de base (Cyles, Classes, Enseignants, Salles, etc.) sont chargées une seule fois via l'API et stockées dans des stores Pinia (`stores/data.ts`).
- **Indexation O(1)** : Plutôt que de rechercher dans des listes via `Array.find()` (complexité O(N)), le store maintient des index sous forme de dictionnaires ou de `Map` indexés par ID. Cela accélère de manière exponentielle le rendu des grosses grilles.
- **Réactivité Ciblée** : Les composants ne s'abonnent qu'aux fragments d'état nécessaires.

### B. Stratégie de Cache SWR (TanStack Vue Query)
Pour soulager le backend et améliorer l'expérience utilisateur, les appels d'API (listes génériques, options de filtres) sont interceptés par **TanStack Vue Query**.
- **Stale-While-Revalidate (SWR)** : Les données sont considérées "fraîches" (`staleTime: 60000` par défaut). Si l'utilisateur navigue entre plusieurs vues, la réponse est servie instantanément depuis le cache en RAM.
- **Invalidation Fine** : Lors de la modification d'une ressource (via un formulaire), seules les requêtes associées à cette ressource sont invalidées, déclenchant un refetch silencieux en arrière-plan.

### C. Rendu Virtuel (Virtual Scrolling)
Pour l'affichage de tables très volumineuses (ex: des milliers de créneaux temporels générés), l'utilisation d'une simple pagination a été remplacée ou complétée par du **Virtual Scrolling** (`GenericList.vue`).
- Seules les lignes du DOM physiquement visibles à l'écran (plus une petite marge de pré-rendu `overscan`) sont générées. 
- Au fil du défilement, les éléments du DOM sont recyclés avec de nouvelles données, maintenant un compte d'éléments DOM bas et constant.

### D. Design System Atomique et Tokens CSS
Afin d'éviter la prolifération de CSS dupliqué ou de couleurs en dur, l'application repose sur un ensemble strict de tokens CSS et de composants de base (Atomes).
- **Fichier de Tokens Centralisé (`main.css`)** : L'ensemble des couleurs (`--accent-primary`, `--bg-surface`, etc.), des espacements (`--spacing-md`) et des ombres (`--shadow-lg`) sont définis comme des variables natives (`:root`) dans `frontend/src/assets/main.css`. Il est strictement interdit d'utiliser des couleurs hexadécimales en dur ailleurs dans le projet.
- **Composants `Base*`** : Toute interaction utilisateur passe par des composants mutualisés (ex: `BaseButton.vue`, `BaseInput.vue`, `BaseModal.vue`, `BaseToggle.vue`).
- **Thème 100% CSS Variables** : Les couleurs et opacités sont construites de manière dynamique avec la fonction native CSS `color-mix()` (ex: `color-mix(in srgb, var(--accent-primary) 20%, transparent)`), garantissant qu'un changement de variable dans `main.css` se répercute uniformément dans toute l'application sans casser le design (ex: les halos de focus, les backgrounds de modales).

### E. Panneaux Maître/Détail (`GenericList` avec `role: "detail"`)
Pour afficher deux listes liées côte à côte dans un même onglet (ex: les classes à gauche, filtrées vers les services de la classe sélectionnée à droite), `App.vue` supporte un second type de panneau `GenericList`, entièrement piloté par `ui.json` — aucun composant Vue dédié n'est nécessaire pour un nouveau menu de cette forme.

**Déclaration** : un panneau avec `"component": "GenericList"` et `"role": "detail"` devient automatiquement le panneau détail de l'onglet. Sa configuration porte deux clés supplémentaires dans `listConfig` :
- `filterFromMasterField` : le champ de l'élément sélectionné dans la liste maître à utiliser comme filtre (accepte un scalaire ou un tableau de valeurs, ex: `service_ids`)
- `filterByField` : le champ de la ressource détail à comparer à ces valeurs (ex: `id`)

**Fonctionnement** (`App.vue`) : dès qu'une seule ligne est sélectionnée côté maître, `loadDetailListItems()` récupère la ressource détail dans son intégralité (`limit: 1000`, comme le reste de l'application) puis filtre **côté client** par appartenance (`Set.has`) — pas de filtre `IN` côté API générique. Ce choix évite de dépendre d'un seul filtre scalaire quand le champ maître est un tableau à plusieurs valeurs (ex: une classe liée à plusieurs MEF).

**Édition en ligne** : contrairement au panneau maître (`GenericList` standard), le panneau détail n'a par défaut aucun gestionnaire d'événement câblé. Pour le rendre éditable, il faut à la fois `"editableInline": true` dans son `listConfig` et un handler `@update-item` explicite côté `App.vue` (`onUpdateDetailGenericInline`, calqué sur `onUpdateGenericInline` mais opérant sur `detailListItems` plutôt que `genericItems`).

**Protection des champs structurants** : `isColumnReadOnly` (`GenericList.vue`) respecte désormais aussi le `readOnly` déclaré côté backend (via `info={"readOnly": True}` sur un `related_field`, propagé au schéma OpenAPI), en plus des surcharges `listConfig.columns[key].readOnly` de `ui.json`. Pour les champs sans déclaration backend (propriétés calculées, relations à cascade destructrice type `delete-orphan`), il reste nécessaire de forcer `"readOnly": true` explicitement dans `ui.json`.

**Ajout de ligne depuis le panneau détail** : comme pour l'édition, le panneau détail n'a par défaut aucun handler `@add` câblé (le bouton "Ajouter" du `GenericList` reste un no-op tant que rien n'écoute l'événement) — il faut à la fois `"disableAdd": false` dans son `listConfig` et un handler `@add` explicite (`onAddDetailGeneric`, calqué sur `onAddGeneric` mais opérant sur `detailListItems`). La ligne créée est un brouillon local (`id` préfixé `new_`) non persisté tant qu'aucune cellule n'a été éditée — la création réelle (`createGenericItem`) n'a lieu qu'à la première édition inline, exactement comme pour le panneau maître. Pour pré-remplir automatiquement une FK structurante à partir de l'élément maître sélectionné, voir la section I (`default_get`) — pas de config `ui.json` dédiée à ce panneau, le mécanisme est générique et s'applique à tout point d'entrée de création. `onAddDetailGeneric` reste câblé même si aucun panneau détail actuel ne l'active (voir ci-dessous) : c'est une capacité générique prête pour un futur panneau, pas du code mort.

**Masquer l'ajout et la suppression pour une ressource "gérée par propagation"** : certaines ressources ne doivent jamais être créées/supprimées à la main dans l'IHM parce qu'un autre mécanisme s'en charge entièrement (ex: `Service`, toujours généré/supprimé via la propagation `MEFService`/`MefDivision` — voir modèle `Service` et `project_service_layer.md`). Deux flags symétriques dans `listConfig`, tous deux à `false` par défaut :
- `disableAdd` : masque la ligne "Ajouter" (déjà existant)
- `disableDelete` : masque le bouton de suppression par ligne (`GenericList.vue`, ajouté à cette occasion)

Ce sont des restrictions **UI uniquement** — l'API générique (`POST`/`DELETE /api/generic/{resource}`) reste fonctionnelle (utile pour l'administration directe, les scripts, les migrations). La garantie de fond (ex: "un `Service` a toujours un `mef_service_id`") doit être imposée séparément au niveau du modèle (`nullable=False`, `@constrains()`) — `ui.json` ne fait que guider l'utilisateur vers le bon flux, il ne remplace jamais la validation métier.

### F. Champs Calculés et Stockés (pattern `@constrains()` sans validation)
Certains champs doivent être **recalculés à chaque création/modification et persistés** (contrairement aux propriétés `@exposed` classiques, calculées à la demande et jamais stockées) — ex: `ServiceRepartition.name` (`"2x1h(H)"`, dérivé de `occurrence_count`/`duration_minutes`/`periodicity`).

Le `CRUDMixin` exécute un second `db.flush()` juste après la boucle des méthodes `@constrains`, ce qui permet de détourner ce mécanisme de validation pour du calcul-et-stockage : une méthode `@constrains()` (sans argument, donc toujours exécutée) qui se contente d'assigner `self.name = ...` au lieu de lever une exception voit sa valeur automatiquement persistée par ce flush, aussi bien en création qu'en modification. Toute donnée insérée en SQL brut (seed `init_db.py`) contourne ce mécanisme et doit donc porter la valeur calculée à la main.

### G. Génération en Cascade à la Création, Propagation Forcée sur Modification (gabarit → objets générés)
Quand la création d'un objet A doit automatiquement engendrer des objets B liés (ex: un `MefService` génère un `Service` par `MefDivision` déjà rattachée à son MEF, et symétriquement un `MefDivision` génère un `Service` par `MefService` déjà existant), le pattern est de surcharger `create()` sur le modèle A plutôt que d'ajouter une méthode séparée à appeler manuellement :

```python
@classmethod
def create(cls, db, vals: dict):
    instance = super().create(db, vals)
    # ... requêtes pour trouver les objets liés déjà existants, puis génération de B ...
    return instance
```

**Points clés (création)** :
- La **génération de nouvelles lignes B** n'a lieu **qu'à la création de A** — un `MefService`/`MefDivision` supplémentaire ne va jamais faire apparaître de nouveaux `Service` en dehors de ce moment-là.
- Factoriser les champs copiés dans un tuple partagé (ex: `Service._MEF_SERVICE_MIRROR_FIELDS`), réutilisé à la fois par le générateur et par l'indicateur de dérive, pour éviter que les deux listes divergent silencieusement.
- Extraire la génération elle-même dans un `classmethod` dédié sur le modèle B (ex: `Service.generate_from_mef_service(db, mef_service, mef_division)`), appelé par les deux sens de la cascade — évite de dupliquer la logique de construction du dict `vals`.
- **Ajouter une contrainte d'unicité** (`@constrains()` interrogeant `db.query(...)` pour un doublon) sur la clé qui identifie l'objet B généré (ici le couple `(mef_service_id, mef_division_id)`), dès qu'une cascade automatique existe : sans elle, une création manuelle redondante du même B passe silencieusement et produit un doublon. Ce garde-fou a d'ailleurs immédiatement révélé un test existant qui recréait manuellement un `Service` déjà auto-généré.
- Le seed (`init_db.py`) insère en SQL brut et ne passe jamais par `create()` : la cascade ne s'y déclenche donc pas, cohérent avec le reste du seed qui contourne systématiquement la logique métier ORM.

**Propagation forcée sur `update()`** : contrairement à la génération de lignes (create-only), la **valeur des champs miroirs** peut rester autoritaire côté gabarit A même après la création de B — c'est un choix produit à trancher explicitement, pas une évidence technique. Pour `MefService` → `Service`, le choix retenu est que le gabarit reste autoritaire à vie : toute modification d'un `MefService` réécrase les champs miroirs sur **tous** ses `Service` déjà générés, y compris ceux ayant déjà divergé manuellement — la dérive détectée par `is_synced_with_mef_service` n'est donc jamais durable, seulement le reflet de l'écart jusqu'à la prochaine modification du gabarit :

```python
def update(self, db, vals: dict):
    instance = super().update(db, vals)
    mirror_vals = {field: getattr(self, field) for field in Service._MEF_SERVICE_MIRROR_FIELDS}
    for service in db.query(Service).filter(Service.mef_service_id == self.id).all():
        service.update(db, dict(mirror_vals))
    return instance
```
- Surcharge de l'**instance method** `update()` (pas un `classmethod` comme `create()`), puisqu'on modifie un objet A déjà existant.
- Requêter les `Service` liés via `db.query(...)` plutôt que via la collection de relation `self.services` : cette dernière peut rester obsolète en mémoire dans la même session après une mise à jour de FK faite depuis l'« autre côté » de la relation (piège déjà rencontré sur `Course.children`, `Alignment.services`).
- La propagation reste asymétrique : modifier un `Service` n'impacte jamais son `MefService` d'origine, dans aucun des deux sens de la relation.

### H. Suppression en Cascade Pilotée par le Schéma (`CRUDMixin._cascade_delete_dependents`)

**Le problème de fond** : `Base` porte un listener global `before_delete`/`before_update` qui rejette (`RuntimeError`) toute écriture ne passant pas par `CRUDMixin.update()`/`delete()` (repérée via les flags d'instance `_via_crud_mixin_update`/`_via_crud_mixin_delete`) — un garde-fou contre les écritures directes (`db.delete(obj)`/`setattr` sans passer par l'API). Mais SQLAlchemy propose DEUX mécanismes de suppression totalement indépendants et souvent mal alignés :
- **Côté base de données**, le `ondelete=` du `ForeignKey(...)` (`CASCADE`, `SET NULL`, `RESTRICT`, `NO ACTION`) — systématiquement déclaré sur chaque FK de ce projet.
- **Côté ORM**, le `cascade=` du `relationship(...)` (`delete`, `delete-orphan`, absent par défaut) — déclaré seulement sur quelques relations (`Course.children`, `Service.repartitions` avant ce correctif), et surtout combiné dans ce projet à `passive_deletes="all"` sur la quasi-totalité des relations 1-N, qui dit explicitement à l'ORM *« ne charge pas les enfants, laisse la BDD gérer via `ondelete=` »*.

Conséquence concrète : dès que `passive_deletes` est utilisé (la norme ici), une suppression en cascade `CASCADE`/`SET NULL` se produit **entièrement en SQL**, sans jamais instancier les objets Python concernés — donc sans jamais déclencher `@constrains()` ni les listeners `before_update`/`before_delete`. C'est exactement ce qui laissait `MefDivision → Service` non protégé : supprimer un `MefDivision` mettait silencieusement `Service.mef_division_id` à `NULL` en BDD, pouvant laisser un `Service` sans aucune structure (ni Division, ni Groupe) sans que `_check_structure_exclusivity` ne s'en aperçoive jamais.

**Pourquoi pas un correctif par relation (`cascade="all, delete-orphan"` + surcharge de `delete()` au cas par cas)** : ça a été la première approche (voir historique), mais elle a deux défauts rédhibitoires : (1) toute relation *déclarée* comme `delete-orphan` fait toujours l'objet d'un doublon de traitement avec le `before_delete` (la cascade ORM native ne pose jamais le flag `_via_crud_mixin_delete`) — donc il aurait fallu un correctif par modèle, un par un, en espérant n'en oublier aucun ; (2) et surtout, une relation qui n'a **jamais été déclarée côté ORM** (le cas `MefDivision → Service`, qui n'a même pas de collection `services` sur `MefDivision`) reste invisible à toute solution basée sur `mapper.relationships` — aucun audit, aussi rigoureux soit-il, ne garantit qu'on ne l'oubliera pas pour un futur modèle.

**La solution retenue, générique et indépendante de toute déclaration ORM** : `CRUDMixin._cascade_delete_dependents()` (`backend/app/models/base.py`) parcourt, avant chaque suppression, le **schéma** lui-même (`Base.metadata`) — pas les `relationship()` — à la recherche de toute table portant une FK vers la table de l'objet supprimé, et traite chaque ligne trouvée selon le `ondelete=` de cette FK :

```python
def _cascade_delete_dependents(self, db):
    table = self.__class__.__table__
    table_to_class = {m.local_table: m.class_ for m in Base.registry.mappers}
    for other_table in Base.metadata.tables.values():
        for fk in other_table.foreign_keys:
            if fk.column.table is not table or fk.ondelete not in ("CASCADE", "SET NULL"):
                continue
            child_cls = table_to_class.get(other_table)
            if child_cls is None:
                continue  # table d'association pure (secondary=) : pas de logique métier à protéger
            fk_attr = class_mapper(child_cls).get_property_by_column(fk.parent).key
            for child in db.query(child_cls).filter(getattr(child_cls, fk_attr) == self.id).all():
                if fk.ondelete == "CASCADE":
                    child.delete(db)                    # cascade réelle, récursive
                else:
                    child.update(db, {fk_attr: None})   # vrai update() : @constrains() s'exécute

def delete(self, db):
    self._via_crud_mixin_delete = True
    self._cascade_delete_dependents(db)
    db.delete(self)
    db.flush()
```

**Ce que ça garantit, structurellement** :
- Fonctionne pour **toute** FK du projet, déclarée ou non côté `relationship()` — plus de zone d'ombre possible pour un futur modèle : le mécanisme se base sur une information (`ondelete=`) déjà systématiquement obligatoire dans ce projet, jamais sur une convention à retenir en plus.
- `ondelete="CASCADE"` → suppression réelle et récursive (chaque enfant traite à son tour ses propres dépendants via son propre `.delete()`).
- `ondelete="SET NULL"` → passe par un vrai `.update()`, donc `@constrains()` s'exécute réellement : si la mise à `NULL` violerait un invariant métier (`_check_structure_exclusivity` sur `Service`), l'`update()` lève une erreur qui annule toute la suppression (transaction entière annulée) — la corruption silencieuse devient un échec bloquant et explicite, sans qu'aucune règle n'ait eu besoin d'être écrite spécifiquement pour `MefDivision`.
- `RESTRICT`/`NO ACTION` : rien à faire, la BDD bloque nativement.
- Les tables d'association pures (`secondary=`, ex: `service_teachers`) sont ignorées : aucune classe mappée, donc aucune logique métier possible sur ces lignes — leur propre `ondelete=CASCADE` suffit.

**Conséquence sur les déclarations existantes** : les `cascade="all, delete-orphan"` de `Course.children` et `Service.repartitions` ont été retirés (devenus redondants et risquant un double traitement/avertissement SQLAlchemy) — la suppression en cascade de ces deux relations est désormais entièrement portée par ce mécanisme générique, pilotée par le `ondelete="CASCADE"` déjà présent sur `Course.parent_id`/`ServiceRepartition.service_id`. `passive_deletes="all"` reste présent ailleurs dans le projet sans risque : ce mécanisme traite tout **avant** que SQLAlchemy n'ait la moindre chance de gérer quoi que ce soit lui-même, donc `passive_deletes` (qui ne fait que désactiver la gestion *native* de l'ORM) n'entre jamais en conflit avec lui.

**Cas concret résolu par ce mécanisme sans code dédié** : `Service.mef_service_id` porte désormais `ondelete="CASCADE"` (changé depuis `SET NULL`, décision métier explicite : un `Service` généré ne doit jamais survivre à la suppression de son gabarit) — supprimer un `MefService` supprime donc ses `Service` (et transitivement leurs `ServiceRepartition`) sans aucune surcharge `delete()` sur `MefService`. `Service.mef_division_id` reste en `SET NULL` ; supprimer un `MefDivision` est désormais **bloqué** tant qu'un `Service` généré en dépend encore (aucun `group_id` de repli), avec le message d'erreur métier existant (`_check_structure_exclusivity`), sans qu'aucune ligne de code n'ait été écrite spécifiquement pour ce cas.

### I. Valeurs par Défaut Dépendantes d'un Contexte (`default_get`, pendant d'Odoo)

**Le besoin** : lors de la création d'un nouvel enregistrement depuis un écran filtré/contextuel (ex: ajouter un `Service` depuis le panneau détail "Services par classe", filtré par la classe sélectionnée à gauche), certains champs devraient se pré-remplir automatiquement à partir de ce contexte (ex: `mef_division_id`) — pas seulement à partir d'une valeur statique (`column.default` côté SQLAlchemy) qui, elle, ne peut jamais dépendre de la sélection courante de l'utilisateur.

**Solution rejetée** : une première version passait par deux clés `ui.json` dédiées au panneau détail (`masterFillField`/`masterFillSourceField`) calculant le pré-remplissage **côté frontend**. Rejetée explicitement ("c'est lourdingue") au profit d'un mécanisme générique, symétrique à `default_get()` côté Odoo, où le calcul reste entièrement en Python sur le modèle concerné — pas de config déclarative par écran.

**Mécanisme retenu** :
- `CRUDMixin.default_get(cls, db, context) -> dict` (`backend/app/models/base.py`) : point d'extension à surcharger par modèle, retourne `{}` par défaut. Contrairement à `@onchange`/`process_onchange` (évaluation en mémoire, sans BDD — voir plus haut), `default_get` reçoit une vraie session `db` et peut donc interroger la base.
- `POST /api/generic/{resource}/defaults` (`backend/app/api/generic.py`, `make_defaults_endpoint`) : fusionne les défauts statiques déjà connus du schéma (même extraction que `make_pydantic_model`, `column.default.arg`) avec le résultat de `model.default_get(db, payload.context)`.
- `api.fetchDefaults(resource, context)` (`frontend/src/services/api.ts`) : appelle cet endpoint ; retourne `{}` silencieusement en cas d'échec (un défaut manquant ne doit jamais bloquer un ajout, contrairement à un vrai échec de `create`/`update`).
- Exemple (`Service.default_get`, `backend/app/models/service.py`) :
  ```python
  @classmethod
  def default_get(cls, db, context: dict) -> dict:
      if context.get("resource") == "divisions" and context.get("id"):
          mef_division = db.query(MefDivision).filter(MefDivision.division_id == context["id"]).first()
          if mef_division:
              return {"mef_division_id": mef_division.id}
      return {}
  ```

**Placé haut dans la pile frontend, appelé par TOUT point d'entrée de création** (exigence explicite : ne pas limiter l'appel au seul panneau détail) — `onAddGeneric` (panneau maître/liste standard) et `onAddDetailGeneric` (panneau détail) appellent tous les deux `api.fetchDefaults(...)` avant de construire le brouillon local, avec un `context` différent selon le point d'entrée (`{}` pour une liste standalone, `{resource, id}` de l'élément maître sélectionné pour un panneau détail). N'importe quel modèle bénéficie donc automatiquement de son propre `default_get()`, depuis n'importe quel écran qui l'affiche, sans que le frontend ait besoin de connaître la logique métier concernée.

**`context` est un contrat libre**, pas un schéma déclaré : chaque `default_get()` lit les clés qui l'intéressent (ici `resource`/`id`) et ignore le reste — pas de validation Pydantic stricte sur sa forme, à l'image du `context` dict d'Odoo.

### J. Popin CRUD pour une Relation Possédée (`parentField` + `GenericListModal`)

**Le besoin** : une colonne `_ids` de type liste (ex: `Service.repartition_ids`) peut représenter deux choses très différentes, qui appellent des IHM opposées :
- un **many-to-many vers des enregistrements indépendants** (ex: `teacher_ids` — les profs existent en dehors du service, on *choisit* parmi eux) → le picker `SearchableMultiSelect` déjà en place est le bon outil ;
- une **relation 1-à-N "possédée"** (ex: `repartition_ids` — une `ServiceRepartition` n'a aucun sens hors de son `Service`) → il ne faut jamais un picker de sélection, mais un vrai CRUD (créer/modifier/supprimer les enregistrements enfants eux-mêmes).

**Solution rejetée** : un nouveau type de `widget` à déclarer par colonne dans `ui.json` (ex: `"widget": "related_list_popin"`). Rejetée explicitement (déjà assez de widgets qui font la même chose) au profit d'une distinction **automatique**, dérivée du schéma déjà généré par le moteur générique — zéro configuration `ui.json` à écrire au-delà de retirer un éventuel `readOnly: true`.

**Mécanisme retenu** :
- `make_pydantic_model` (`backend/app/api/generic.py`), dans la boucle qui génère les champs `_ids` pour chaque relation `uselist`, ajoute désormais `"parentField": <nom de la FK de retour>` **uniquement quand `rel.secondary is None`** (donc jamais pour un vrai m2m comme `teacher_ids`) — la FK est déduite de `rel.local_remote_pairs`, exactement comme pour `CRUDMixin._cascade_delete_dependents` (section H) :
  ```python
  if rel.secondary is None:
      for local_col, remote_col in rel.local_remote_pairs:
          if remote_col.table is rel.mapper.class_.__table__:
              rel_schema_extra["parentField"] = rel.mapper.get_property_by_column(remote_col).key
              break
  ```
- `GenericList.vue` : toute colonne dont le `FormField` porte à la fois `resource` **et** `parentField` (et qui n'est pas en lecture seule) affiche un résumé (`getDisplayValue`, déjà existant) + un bouton crayon (œil si lecture seule) au lieu du picker multiselect par défaut. Le clic ouvre `relatedListModal` (état local du composant).
- `GenericListModal.vue` (nouveau composant, léger) : `BaseModal` + `GenericList` réutilisés tels quels. Charge ses propres données via `fetchGenericList(resource, 0, 1000, undefined, {[parentField]: item.id})` — le filtrage par FK arbitraire est déjà supporté nativement par l'endpoint liste générique (`generic.py`, boucle sur `request.query_params`), aucun changement backend necessaire pour ça. Dérive `fields`/`columns` depuis le schéma OpenAPI de la ressource enfant (même logique que `App.vue::getFormFieldsConfig`, réimplémentée en version minimale plutôt que partagée — voir "Pourquoi pas un composable partagé" ci-dessous). Add/update/delete passent par les mêmes fonctions génériques que partout ailleurs (`createGenericItem`/`updateGenericItem`/`deleteGenericItem`), et émettent `resource:mutated` (section E) pour invalider le cache FK au bon endroit.

**Pourquoi pas un composable partagé avec `App.vue::getFormFieldsConfig`** : cette fonction gère aussi des cas propres à `App.vue` (options d'heures dérivées de la grille de créneaux, listes globales `schoolsList`/`periodTypesList`) qui n'ont pas de sens dans une popin générique. Plutôt que de la refactoriser (risque élevé, fonction utilisée par tous les écrans de l'appli) pour un seul nouveau composant, `GenericListModal.vue` réimplémente une version volontairement réduite de la même logique schéma-driven (pas de gestion des colonnes `time`, pas de largeur dynamique de colonne) — accepté comme compromis pragmatique, à réévaluer si un troisième besoin similaire apparaît.

**Ce que ça garantit** : toute future relation 1-à-N "possédée" exposée en `_ids` (peu importe le modèle) obtient automatiquement le bouton crayon + popin CRUD dès qu'elle n'est pas `readOnly` — aucun code à écrire, à la différence du m2m vers des enregistrements indépendants qui garde le picker `SearchableMultiSelect` comme aujourd'hui.

**Configurer les colonnes de la popin (`ColumnConfig.listConfig`)** : par défaut, la popin affiche tous les champs de la ressource enfant. Pour restreindre/réordonner/relabelliser (ex: masquer `name` et `course_ids` de la popin `ServiceRepartition`, y compris de son propre sélecteur de colonnes), une solution ad-hoc a été tentée puis rejetée (`popinHiddenColumns: string[]`, une clé dédiée avec sa propre sémantique) — remplacée par le **même mécanisme, empaqueté** : `ColumnConfig` (l'objet déjà utilisé pour configurer chaque colonne d'un `listConfig`) accepte maintenant une clé `listConfig`, dont la valeur est un `ListConfig` **complet**, structurellement identique à celui de n'importe quel panneau `GenericList` :
```json
"repartition_ids": {
  "overrideLabel": "Répartitions",
  "listConfig": {
    "editableInline": true,
    "columns": {
      "occurrence_count": { "visibleByDefault": true, "overrideLabel": "Occurrences" },
      "duration_minutes": { "visibleByDefault": true, "overrideLabel": "Durée" },
      "periodicity": { "visibleByDefault": true, "overrideLabel": "Périodicité" }
    }
  }
}
```
`GenericList.vue` transmet ce `listConfig` tel quel à `GenericListModal`, qui le fusionne uniquement avec l'état `readOnly` (calculé côté parent, toujours prioritaire) avant de le repasser à sa propre instance interne de `GenericList`. Le masquage complet des colonnes non listées (y compris du sélecteur) ne demande **aucun code nouveau** : c'est le comportement déjà existant de `internalColumns` (watcher sur `props.columns`/`props.listConfig`) — quand `listConfig.columns` est fourni, il sert d'allowlist stricte (seules les clés qu'il contient deviennent des colonnes), exactement comme pour n'importe quel panneau `GenericList` classique aujourd'hui. Aucune interface TypeScript ni aucun composant n'a eu besoin d'un traitement spécial pour la popin — `ColumnConfig.listConfig: ListConfig` est une simple référence récursive vers un type qui existait déjà.

**Extraction en widget partagé (`OwnedRelationField.vue`) — IMPLÉMENTÉ, corrige un trou réel** : ce mécanisme n'existait qu'à l'intérieur du template de `GenericList.vue` — un champ `_ids` possédé apparaissant dans un **formulaire** (`GenericForm.vue`/`FormLayoutGrid`) n'était couvert par rien : n'ayant pas de `widget` déclaré explicitement, il tombait dans la branche `type === 'multiselect'` générique (un champ `_ids` possédé porte le même `ui_type` qu'un vrai m2m dans le schéma — seuls `resource`+`parentField` les distinguent) et affichait un picker de sélection global. Vérifié en pratique (pas seulement en théorie) : **9 panneaux `GenericForm` actifs aujourd'hui** exposent au moins un champ touché (`divisions_form`/`partition_ids`, `subjects_form`, `courses_form`/`children_ids`, `mefs_form`, `schools_form` — 5 champs à lui seul, `disciplines_form`, `missions_form`, `election_methods_form`). Pour au moins un cas (`Partition.division_id`), le modèle interdit explicitement de réassigner la FK parent après création (`Partition.update()`) — donc le picker ne se contentait pas d'être trompeur, toute tentative d'ajout/retrait y échouait avec une erreur 400 garantie.

Correctif : le contenu du `<div class="inline-related-list-wrapper">` de `GenericList.vue` (résumé + crayon + `GenericListModal`) est extrait dans `frontend/src/components/widgets/OwnedRelationField.vue`, utilisé par les deux vues :
- Dans `GenericList.vue` : même position dans le dispatch de cellule (juste après le registre de widgets explicite, avant `multiselect`), `listConfig` résolu comme avant (`props.listConfig?.columns?.[key]?.listConfig`) et transmis via `widgetParams.listConfig`.
- Dans `FormLayoutGrid` (`GenericForm.vue`) : nouvelle branche `field.resource && field.parentField`, positionnée entre le registre de widgets et `type === 'multiselect'` — la détection reste structurelle (schéma), pas une déclaration `widget` à ajouter manuellement à chaque champ concerné.
- **Non inscrit dans `WIDGET_REGISTRY`** : contrairement à `many2many_ordered_list` (déclenché par une clé `widget` explicite), ce widget se déclenche automatiquement dès que `resource`+`parentField` sont présents — un signal structurel du schéma, pas un choix de configuration. Les deux mécanismes coexistent à des niveaux de priorité différents (`widget` explicite toujours prioritaire, vérifié en premier).

**Changement d'affichage assumé (tags plutôt que résumé texte)** : l'ancien rendu (`getDisplayValue`, une seule chaîne des libellés joints par `, `) est remplacé par une liste de badges façon tag — un par enregistrement lié — réutilisant l'habillage visuel déjà en place pour `SearchableMultiSelect` (classes `.tag-badge`/`.tag-label`), pour rester cohérent avec l'affichage des autres champs multi-valeurs de l'application plutôt que d'introduire un troisième style de rendu. Contrairement aux tags de `SearchableMultiSelect`, ceux-ci ne portent pas de bouton de suppression individuel — la modification reste exclusivement via la popin (crayon), pour ne pas dupliquer deux façons différentes de retirer un élément.

### K. Dropdowns Tronqués dans une Popin Peu Remplie — Choix Délibéré de ne Pas Corriger la Cause de Fond

**Le symptôme** : dans une popin peu remplie (ex: `GenericListModal` avec 2-3 lignes), un dropdown ouvert depuis une cellule (`SearchableSelect`/`SearchableMultiSelect`) ou le sélecteur de colonnes de `GenericList` peut apparaître tronqué, avec un ascenseur pour voir la fin de la liste.

**Cause identifiée** : ces dropdowns sont en `position: absolute` (jamais en `Teleport`), donc soumis au découpage (`overflow: hidden`/`auto`) de tout ancêtre — ici `BaseModal.modal-body` et `GenericList.table-wrapper`. Quand le conteneur est petit, la partie du dropdown qui dépasse visuellement est coupée. Un ancien correctif (`z-index: 9999 !important` sur la variante inline) ne réglait pas ce problème : le `z-index` ne joue que sur l'ordre d'empilement, jamais sur le découpage `overflow` d'un ancêtre — piège CSS classique.

**Deux solutions envisagées** :
1. **Correctif général** (`Teleport` + positionnement viewport via `getBoundingClientRect()`, sur `SearchableSelect`/`SearchableMultiSelect`/le sélecteur de colonnes de `GenericList`) — implémenté puis **retiré** après relecture : trop de surface touchée (3 composants partagés, utilisés dans tout l'écran) pour un besoin observé à un seul endroit, sans possibilité de vérification réelle en navigateur (règle du projet — voir `constitution.md` Principe II). Le risque de régression sur des composants aussi transverses a été jugé disproportionné par rapport au problème constaté.
2. **Correctif local, ciblé sur la popin** (retenu) — donner à `GenericListModal` une taille suffisante pour que les dropdowns qu'elle contient (peu d'options dans ce cas d'usage : périodicité, durée) ne soient jamais tronqués en pratique.

**Pourquoi ce choix** : le correctif général reste la solution techniquement correcte si ce même symptôme réapparaît ailleurs dans l'app (plusieurs endroits touchés indépendamment serait un signal fort qu'investir dans le correctif générique en vaut la peine) — mais tant que le besoin observé reste isolé à cette popin, la solution locale est nettement moins risquée pour un résultat équivalent dans ce cas précis. Ne pas confondre "solution la plus élégante en théorie" et "solution la mieux dimensionnée pour le besoin réel" : sur ce coup-ci, ces critères n'allaient pas dans le même sens.

**Piège rencontré en implémentant la solution 2** : un premier essai a donné `min-height: 420px` à `.generic-list-modal-content` (le wrapper autour de `GenericList` dans `GenericListModal.vue`). Insuffisant : `GenericList.vue` repose sur `.generic-list-container { height: 100%; }` pour que son `.table-wrapper` (`flex: 1`, la zone scrollable où les dropdowns de cellule s'ancrent) s'étire — et la résolution CSS d'un `height: 100%` exige que le parent direct ait une hauteur *définie*. Un `min-height` seul sur un bloc `display: block` ne fournit pas cette garantie de façon fiable : le `min-height` ajoutait de l'espace vide *autour* de la liste (toujours petite) plutôt que d'agrandir la liste elle-même. Correctif : remplacer `min-height` par une `height` fixe (`height: 420px`) sur `.generic-list-modal-content`, qui *est* une hauteur définie — `height: 100%` de `.generic-list-container` s'y résout alors correctement, et `.table-wrapper` s'étire réellement. Le scroll interne déjà présent sur `.table-wrapper` (`overflow: auto`) continue de gérer le cas où il y a plus de lignes que ne peut en afficher 420px, donc aucune régression pour les listes plus longues.

### L. Vue Pivot Générique (Tableau Croisé Configurable) — IMPLÉMENTÉ

> Conception discutée et validée avec l'utilisateur avant tout code (voir l'historique de la discussion), puis implémentée. Les points 1 à 5 ci-dessous reflètent la conception d'origine (toujours valable) ; le point 6 a été mis à jour avec la forme **réellement construite** de `pivotConfig`, qui diffère sur plusieurs points de l'esquisse initiale (raisons expliquées en fin de section).

**Le besoin** : un nouveau type de vue générique — un tableau où une colonne peut être "explosée" en une colonne par valeur distincte d'un champ (un peu comme un TCD/pivot), avec un champ à la croisée ligne × colonne. Point de départ de la réflexion : le module Odoo `web_grid_view` (grille temps/employé façon feuille d'heures).

**Rejet du modèle Odoo (`read_grid` + méthode d'ajustement)** : la vue grid d'Odoo est un **pivot d'agrégation serveur** — `read_grid` fait un group-by lignes × colonnes avec une mesure agrégée (somme), et l'édition d'une cellule agrégée appelle une méthode Python métier dédiée par modèle (`adjust_name`) qui "réconcilie" la valeur cible en créant/scindant les enregistrements réels. Ce mécanisme suppose du code Python spécifique à chaque modèle voulant une grille — à l'opposé du moteur générique de Klepsydrix (zéro code par modèle, piloté par le schéma OpenAPI + `ui.json`). Décision : **ne jamais éditer une cellule agrégée directement** — l'édition continue de se faire sur les enregistrements réels (`Service`/`ServiceRepartition`), ailleurs dans l'app. Ça élimine le besoin d'un équivalent à `adjust_name`.

**Principe fondateur** : le pivot se construit toujours à partir d'**une seule ressource de base** (dans tous les cas d'usage validés : `services`), jamais en filtrant directement une ressource enfant. Toutes les briques ci-dessous s'appliquent sur les enregistrements de cette ressource, chargés une fois puis regroupés côté client.

**1. Axe lignes** : par défaut, "un enregistrement de la ressource de base = une ligne" (comme `GenericList` aujourd'hui). Nouveauté : une ligne peut aussi être **explosée** sur un champ many-to-many de la ressource de base (ex: `Service.teachers` → une ligne par professeur lié, le service étant crédité en entier à chacun — règle métier confirmée : pas de répartition du volume horaire entre co-enseignants).

**2. Axe colonnes** : toujours explosé sur les valeurs distinctes d'un champ `select` ou many-to-one de la ressource de base (ex: une colonne par MEF, ou par Division). Ces valeurs distinctes sont déjà disponibles génériquement côté frontend sans nouvel endpoint : options statiques du schéma pour un `select`, `fkOptionsCache` déjà chargé pour un many-to-one — aucune agrégation serveur nécessaire pour *lister* les colonnes.

**3. Contenu de cellule — deux modes, configurables par mesure** :
   - **Mode agrégat (lecture seule)** : la cellule affiche une valeur calculée (ex: `SUM` d'un champ numérique, y compris un champ `@exposed` comme `total_weekly_duration_minutes`) sur tous les enregistrements du croisement ligne × colonne. Jamais éditable directement (voir ci-dessus).
   - **Mode liste + popin** : la cellule affiche un résumé (nombre d'éléments, ou libellés concaténés) d'un champ `_ids` ou m2m de la ressource de base sur les enregistrements du croisement (ex: la liste des profs, ou des `ServiceRepartition`), avec un bouton crayon si non-readonly. Le crayon ouvre **`GenericListModal`, réutilisé tel quel**, filtré sur la ressource de base avec **le couple (valeur de ligne, valeur de colonne)** au lieu du `parentField` unique actuel — extension mineure de son prop de filtre (un dict à N clés au lieu d'une seule), et un `listConfig.columns` qui restreint l'affichage à la seule colonne pertinente pour cette mesure (ex: `teacher_ids`, ou `repartition_ids` — dans ce dernier cas, la popin-dans-popin déjà existante sur `repartition_ids` fonctionne sans rien ajouter). Chaque enregistrement du croisement reste sa propre ligne éditable normalement dans cette popin, même s'il y en a plusieurs (pas de notion de "multi-parent" à inventer : c'est juste une `GenericList` filtrée dont le filtre peut retourner 0, 1 ou N lignes, comme n'importe où ailleurs).

**4. Couleur de fond de cellule** : dérivée d'un champ couleur porté par un enregistrement lié (ex: `Alignment.color`, via `Service.alignment_id` — **prérequis à ajouter**, `Alignment` n'a aujourd'hui que `code`/`name`). Si les enregistrements du croisement pointent vers des `Alignment` de couleurs différentes (ne devrait pas arriver, contrainte métier à poser plutôt qu'à gérer dans l'UI), repli visuel : fond hachuré gris/blanc (`repeating-linear-gradient`).

**5. Sélection groupée et actions groupées** : extension du mécanisme `__actions__` existant (section 15.F) plutôt qu'un nouveau système. Aujourd'hui `condition` est une expression JS évaluée sur un `record` unique, rendue uniquement dans `GenericForm.vue`. Pour le pivot :
   - La sélection de cellules du pivot se résout vers un ensemble plat d'IDs de la ressource de base (`Set<id>`) — le même type de donnée que `GenericList.selectedIds` aujourd'hui (row multi-select déjà existant), juste peuplé différemment (une cellule peut représenter plusieurs enregistrements).
   - `condition` doit pouvoir s'évaluer sur un **tableau** de records (`records.every(...)`) en plus du `record` singulier actuel, et être rendue dans un nouvel emplacement : une barre d'actions au-dessus du pivot, visible dès que la sélection est non vide.
   - L'action elle-même (ex: bouton "Aligner") reste une `classmethod` Python bespoke sur `Service` (créer un nouvel `Alignment`, y rattacher tous les `Service` sélectionnés, contrainte de signature de répartition déjà appliquée par `_check_alignment_repartition_match`), invoquée via l'endpoint générique d'appel de méthode de classe déjà existant (`POST /api/generic/{resource}/call/{method_name}`, section 15.C) — aucune nouvelle route backend nécessaire. Décision confirmée : "Aligner" crée **toujours** un nouvel `Alignment` (jamais de fusion avec un `Alignment` existant).

**Cas d'usage validés avec l'utilisateur** (traçabilité, tous vérifiés couverts par les briques ci-dessus) :
1. Lignes = discipline, colonnes = MEF, cellule = somme des heures pour la discipline et le MEF (mode agrégat, lecture seule) — incohérence initiale de l'énoncé (qui mentionnait "la division") tranchée : c'est bien le MEF sur les deux axes.
2. Lignes = professeur (explosion sur `Service.teachers`), colonnes = matière/heures totales (agrégat) + une colonne par division (agrégat), couleur = `Alignment.color`.
3. Lignes = discipline, colonne heures totales (agrégat) + une colonne par division = liste des profs (mode liste + popin sur `teacher_ids`), couleur = `Alignment.color`.
4. Identique au cas 3 mais la cellule porte la liste des `ServiceRepartition` (mode liste + popin sur `repartition_ids`, popin-dans-popin), couleur = `Alignment.color`. Sélection groupée de cellules à répartition identique → bouton "Aligner".

**6. Nom du composant et forme de `ui.json` (tels que construits)** : `frontend/src/components/GenericPivot.vue` (`"component": "GenericPivot"`, chargé en lazy via `defineAsyncComponent` dans `App.vue`, même pattern que `GenericList`/`GenericForm`). Contrairement aux autres panneaux `GenericList`/`GenericForm`, il est **totalement autonome** — il ne dépend d'aucun état global d'`App.vue` (pas d'`activeAdminModel`, pas de `genericItems`), sur le même principe d'indépendance que `GenericListModal.vue` : il reçoit `resourceKey` + `pivotConfig` et charge lui-même tout ce dont il a besoin (schéma OpenAPI via `inject('openApiSpec')`, liste complète de la ressource de base, listes des ressources liées pour résoudre les libellés).

```json
{
  "id": "services_by_discipline_mef",
  "component": "GenericPivot",
  "resourceKey": "services",
  "pivotConfig": {
    "row": { "field": "discipline_id" },
    "columns": [
      { "key": "total_hours", "field": "total_weekly_duration_minutes", "agg": "sum", "overrideLabel": "Total heures (min)" }
    ],
    "matrix": {
      "field": "mef_id",
      "cell": { "type": "aggregate", "field": "total_weekly_duration_minutes", "agg": "sum" }
    }
  }
}
```

- `row` : un objet `{field, explode?, overrideLabel?}`, ou un **tableau** de tels objets pour un groupement composé (cas 2 : `[{"field": "teacher_ids", "explode": true, "overrideLabel": "Professeur"}, {"field": "subject_id", "overrideLabel": "Matière"}]` — une ligne par couple (professeur explosé, matière), pas juste par professeur ; l'énoncé du cas 2 listait "professeur" ET "matière" comme deux colonnes fixes distinctes, ce qui n'a de sens que si elles forment ensemble la clé de groupement). Une colonne d'en-tête est générée automatiquement par dimension, dans l'ordre du tableau — pas besoin d'entrées `type: "label"` dans `columns`.
- `columns` : uniquement les mesures agrégées fixes (non explosées en colonnes), ex. "Total heures". Un seul type existe en pratique (`agg: "sum"` sur un champ numérique, y compris un champ `@exposed`) — les 4 cas validés n'ont jamais eu besoin d'un type `"field"`/`"label"` distinct, donc il n'a pas été construit (pas de code pour un besoin qui ne s'est pas présenté).
- `matrix.field` / `matrix.cell` : identique à la conception d'origine.
- `colorField` : **pas un chemin imbriqué** (`"alignment.color"` envisagé initialement) mais le nom d'un champ **à plat** sur la ressource de base, résolu via un `related_field` côté modèle — ex. `Service.alignment_color = related_field("alignment", "color", ...)`, exactement le même pattern que `division_id`/`mef_id`. Plus simple à résoudre côté frontend (un `recordsById.value[id][colorField]` direct, pas de traversée de chemin), et cohérent avec le reste du moteur générique qui aplatit déjà systématiquement les champs liés de cette façon.
- **Aucune notion de "resource" à déclarer dans `pivotConfig`** : contrairement à l'esquisse initiale (`{"field": "discipline_id", "resource": "disciplines"}`), la ressource liée d'un champ (pour résoudre ses libellés) est lue directement depuis le schéma OpenAPI (`prop.resource`, déjà présent pour tout champ FK réel, `related_field`, ou relation m2m — voir sections 15.G/J) — la dupliquer dans `ui.json` aurait été une redondance pure.

**Écart le plus significatif par rapport à la conception d'origine — la popin d'édition (mode liste)** : l'esquisse prévoyait de filtrer `GenericListModal` sur `{ligne, colonne}` via un dict de filtres à N clés passé à l'endpoint liste générique. En pratique, `division_id`/`mef_id` (les axes de colonne des 4 cas) sont des `related_field` — de simples `property` Python, pas des colonnes SQL — donc **pas filtrables côté serveur** (`getattr(Model, key)` à froid sur la classe ne renvoie pas une expression SQL). Plutôt que de rendre `related_field` filtrable en SQL (changement risqué, `hybrid_property` sur un mécanisme utilisé par de nombreux modèles), la solution retenue est plus simple et évite complètement le problème : `GenericPivot` connaît déjà, pour chaque cellule, l'ensemble exact des IDs `Service` qui la composent (calculé côté client pour l'affichage) — il les transmet donc directement à `GenericListModal` via un nouveau prop `ids: number[]` (alternative à `filterField`/`filterValue`, les deux modes coexistent), lequel s'appuie sur un nouveau filtre générique `?ids=1,2,3` ajouté à l'endpoint liste (`model.id.in_(...)`, une vraie colonne, toujours filtrable). Bénéfice secondaire : ce filtre `ids` est un ajout générique réutilisable par n'importe quel futur besoin de "popin sur un ensemble d'IDs déjà connu", pas seulement le pivot.

**Actions groupées — écart de contrat** : `__actions__` gagne un nouveau `type: "bulk_api"` (les types existants `api`/`wizard` supposent un enregistrement unique), avec `condition` évaluée sur un tableau `records` plutôt qu'un `record`, rendu dans une barre d'outils du pivot (pas dans `GenericForm.vue`, qui reste inchangé). Piège rencontré à l'implémentation : `make_class_call_endpoint` (section 15.C) injecte toujours `db` en `kwargs` quand la signature de la méthode le porte — un appel positionnel (`payload.args`) entre alors en collision avec cette injection dès que `db` précède le vrai paramètre métier dans la signature (`TypeError: got multiple values for argument 'db'`). Toute action `bulk_api` doit donc être appelée via `kwargs`, avec un nom de paramètre **générique et fixe** : `ids` (ex. `Service.align_bulk(cls, db, ids: list[int])`), pas `service_ids` ni un nom spécifique à la ressource — ce contrat est réutilisable tel quel par n'importe quelle future action groupée, sur n'importe quel modèle.

**Action "Aligner" (`Service.align_bulk`)** : crée toujours un nouvel `Alignment` (code/nom auto-générés via `uuid4`, jamais de fusion avec un `Alignment` existant — décision confirmée), après avoir vérifié que tous les `Service` sélectionnés partagent la même signature de répartition (même logique que `_check_alignment_repartition_match`, vérifiée deux fois : en amont pour un message d'erreur clair sans `Alignment` orphelin créé, et de toute façon par le `@constrains()` à chaque `Service.update()`).

**Prérequis confirmé pendant la conception, absent en réalité** : le lien N-N `Service ↔ Teacher` (`service_teachers`) existait déjà avant cette fonctionnalité — ce n'était pas un prérequis à construire, contrairement à ce qui avait été annoncé au départ de la discussion.

**Couleur pastel automatique (`Alignment.create()`)** : si `color` n'est pas fourni à la création (ex. par `Service.align_bulk`, qui ne le renseigne jamais), `Alignment.create()` (surchargé) affecte automatiquement la première couleur de `Alignment._PASTEL_PALETTE` (16 teintes) pas encore utilisée par un autre `Alignment`, avec repli sur un tirage aléatoire dans la palette si elle est épuisée — sans ça, plusieurs `Alignment` distincts seraient visuellement indissociables dans le `colorField` de `GenericPivot`. **Piège rencontré** : `color` portait initialement un défaut SQL (`default="#CCCCCC"`) — or `make_pydantic_model` reprend tel quel le défaut d'une colonne pour construire le schéma Pydantic, donc une requête de création qui omettait `color` recevait quand même `"#CCCCCC"` une fois validée par Pydantic, **avant** même d'atteindre `create()` : "couleur omise" et "couleur = #CCCCCC" devenaient indistinguables côté `vals`. Correctif : retirer le défaut SQL et rendre la colonne nullable (`Optional[str]`) — `clean_payload()` (generic.py) ignore déjà les clés à `None`, donc une couleur omise n'apparaît plus du tout dans `vals`, et `create()` peut la détecter correctement via `vals.get("color")`. La colonne reste nullable au niveau SQL mais n'est, en pratique, jamais NULL en base : `create()` assigne toujours une couleur, fournie ou pastel.

### M. Assistants Multi-Étapes Génériques (`GenericWizard.vue`) — IMPLÉMENTÉ

**Le besoin** : le seul wizard du projet (« Décomposer le cours ») était un composant Vue de ~540 lignes entièrement écrit à la main — sa propre UI multi-écrans, son propre chargement de données, ses 3 appels RPC nommés en dur côté frontend ET backend (`rpc_get_available_modes`, `rpc_preview_composition`, `rpc_save_composition`), et son enregistrement dans une table `componentsMap` codée en dur dans `GenericForm.vue` (import + entrée de dict à ajouter à chaque nouveau wizard). Aucune de ces briques n'était réutilisable pour un futur wizard.

**Rejet de la persistance façon Odoo** : le mécanisme de wizard d'Odoo repose sur un `TransientModel` — une vraie ligne en base, temporaire, créée/modifiée/relue à chaque étape. Décision explicite de ne pas suivre ce modèle ici : (1) le pattern déjà en place (chaque appel RPC reçoit l'état complet en paramètres et renvoie un résultat calculé, sans rien persister) fonctionne déjà et est plus simple (pas de table à créer, pas de purge des brouillons abandonnés à gérer) ; (2) `TransientModel` chez Klepsydrix (section B) n'a de toute façon aucune table et, depuis le refactor vers le polymorphisme documenté dans cette même section B, ses `create()`/`update()`/`delete()` lèvent systématiquement — le réutiliser pour des brouillons de wizard aurait demandé une classe sœur, pas une réutilisation gratuite malgré le nom identique à celui d'Odoo.

**Principe retenu** : l'état du brouillon vit uniquement dans `GenericWizard.vue` (un objet réactif), jamais en base, entre les appels RPC déclarés par étape — même philosophie que le mécanisme déjà en place, mais généralisée.

**1. Déclaration d'un wizard générique** : sur `__actions__` du modèle (section 5.F), `type: "wizard"` sans `component` déclare une clé `steps` — une liste d'étapes, chacune :
```python
{
    "id": "mapping",
    "title": "1. Mapping et mode de répartition",
    "submitLabel": "Générer l'aperçu",
    "rpc": "rpc_preview_composition",
    "rpcParams": {"mode": "composition.mode", "mapping": "composition.mapping"},
    "fields": [
        {"key": "composition", "label": "Répartition", "type": "text", "widget": "course_composition_mapping", "fullWidth": True}
    ]
}
```
- `fields` : mêmes objets `FormField` qu'un formulaire classique (voir section 5.F) — un champ scalaire simple se rend automatiquement via le moteur de champs existant ; un champ complexe passe par `widget`/`widgetParams`, exactement comme `many2many_ordered_list` déjà en place.
- `rpc` (facultatif) : nom de la méthode d'instance appelée à la soumission de cette étape. Une étape sans `rpc` avance simplement au brouillon accumulé, sans aller-retour serveur — couvre le cas des wizards purement collecte de champs.
- `rpcParams` : associe chaque paramètre attendu par la méthode RPC à un **chemin à points** dans le brouillon accumulé (`"composition.mode"` va chercher `draft.composition.mode`) — nécessaire dès qu'un widget porte plusieurs valeurs sous une seule clé de champ (voir `CourseCompositionMapping.vue`, dont la valeur est `{mapping, mode}` sous la clé `"composition"`, car la disponibilité des modes dépend en direct du contenu du mapping et les deux doivent rester dans le même widget pour ça).
- Le JSON renvoyé par l'appel RPC est fusionné tel quel dans le brouillon (`Object.assign`). Si une clé de la réponse correspond à la clé d'un champ d'une étape suivante, ce champ est déjà peuplé sans code de plomberie supplémentaire : `rpc_preview_composition` renvoie `children_vals`, lu directement par l'étape "preview" qui porte un champ de cette même clé — coïncidence de nommage exploitée délibérément, pas un mécanisme de mapping séparé à écrire.
- `isLast` (ou la dernière étape déclarée) : après l'appel RPC réussi, ferme le wizard (`success`, invalide le cache de `resourceKey`) au lieu d'avancer à l'étape suivante.

**2. `GenericWizard.vue`** (`frontend/src/components/widgets/GenericWizard.vue`) : ne réinvente aucun rendu de champ — chaque étape délègue entièrement à `GenericForm.vue`, **réutilisé tel quel**, avec le brouillon accumulé comme `modelValue`. Deux petites extensions, additives et rétrocompatibles, ont été nécessaires sur `GenericForm.vue` :
- Un prop `submitLabel?: string` (défaut `"Enregistrer"`) — chaque étape a son propre libellé de bouton ("Générer l'aperçu", "Enregistrer définitivement"...).
- Aucune connaissance de `resourceKey` n'est transmise au `GenericForm` de l'étape (volontairement `undefined`) : sans ça, `GenericForm` irait chercher les actions métier du modèle **parent** (dont l'action `wizard` elle-même) et les afficherait dans chaque étape — un piège de récursion évité en ne câblant simplement pas cette prop.
- `GenericWizard` injecte dans `widgetParams` de chaque champ d'étape le contexte que seule l'instance du wizard connaît (`recordId`, `resourceKey`, `sourceRecord` = l'enregistrement parent complet) — les étapes sont déclarées génériquement sur le modèle, sans savoir à l'avance sur quel enregistrement concret elles s'exécuteront.

**3. Registre de widgets unifié (`frontend/src/components/widgets/registry.ts`)** : le dispatch de `many2many_ordered_list` dans `FormLayoutGrid` (interne à `GenericForm.vue`) était un `if (elem.widget === '...')` codé en dur — chaque nouveau widget demandait de modifier le code source de `GenericForm.vue`. Remplacé par un lookup dans un registre partagé (`Record<string, Component>`), avec le même contrat de props que `Many2ManyOrderedList.vue` déjà en place (`modelValue`, `field`, `widgetParams?`, `disabled?`, `parentRecord?`, émission `update:modelValue`) — utilisé aussi bien par un champ de formulaire classique que par un champ d'étape de wizard, sans distinction de code entre les deux.

**Régression rencontrée en étendant ce registre à `GenericList.vue`** : `widget` est déclaré au niveau du **modèle** (dict `info`, ex: `Division.mef_links` → `"widget": "many2many_ordered_list"`), donc valable pour *toute* vue affichant ce champ — mais un widget conçu pour l'espace généreux d'un formulaire (une mini-table éditable complète, ex. `Many2ManyOrderedList.vue`) n'est pas adapté à une cellule de tableau compacte. Faire honorer `widget` en liste sans distinction a fait apparaître ce mini-tableau en pleine cellule dans la colonne "Effectifs par MEF" de la liste "Classes" — d'autant plus visible que `mef_link_ids` porte *aussi* `resource`+`parentField` (relation possédée), donc avant ce changement il retombait correctement sur `OwnedRelationField` (tags + crayon), un rendu compact déjà adapté à la liste ; le registre codé en dur avec priorité absolue a court-circuité ce repli. Correctif : chaque entrée du registre porte désormais un `contexts?: ('list' | 'form')[]` (défaut `['form']` uniquement — un widget doit *demander* explicitement le support liste plutôt que s'y retrouver par accident), via `getWidgetForContext(name, context)` plutôt qu'un accès direct au registre. Les 3 widgets actuels (`many2many_ordered_list` et les 2 widgets du wizard de décomposition) restent `['form']` — aucun n'est aujourd'hui conçu pour un rendu compact.

**4. Migration du wizard de décomposition de cours, comme validation du mécanisme** : l'ancien `CourseCompositionWizard.vue` (bespoke, supprimé) est devenu 2 étapes déclarées sur `Course.__actions__` + 2 widgets dédiés :
- `CourseCompositionMapping.vue` (étape 1) : reprend telle quelle la logique de mapping (profs × groupes/parties/classes/salles, exclusion mutuelle des cibles, unicité des profs) et de sélection du mode, y compris l'appel RPC débounced à `rpc_get_available_modes` à chaque changement de mapping — cette dépendance croisée (mode ↔ mapping) reste **interne au widget**, pas générique, parce que ce n'est pas un besoin qui se généralise à n'importe quel wizard. C'est exactement le compromis discuté : la complexité spécifique reste locale à un widget, l'orchestration (étapes, soumission, brouillon) devient commune.
- `CourseCompositionPreview.vue` (étape 2, `isLast`) : le tableau d'aperçu éditable, quasiment inchangé.
- **Simplification assumée, pas une régression accidentelle** : l'ancien bouton "Générer l'aperçu" était désactivé côté client tant que le mapping n'était pas valide (`isMappingValid`). `GenericForm.vue` n'a pas de mécanisme pour qu'un widget bloque dynamiquement le bouton de soumission d'un formulaire générique. `CourseCompositionMapping.vue` affiche toujours un indice visuel si le mapping est invalide, mais le bouton reste cliquable — une soumission invalide échoue proprement côté serveur (erreur affichée), au lieu d'être bloquée en amont côté client. Étendre `GenericForm`/le registre de widgets pour qu'un widget puisse exposer une validité bloquante n'a pas été fait : aucun autre besoin connu ne le demande aujourd'hui.
- ~~Pas de bouton "Précédent"~~ **Ajouté depuis** : `GenericWizard.vue` rend lui-même ce bouton (à côté de l'indicateur d'étapes), pas `GenericForm.vue` — la navigation entre étapes est un concept propre au wizard, `GenericForm` reste un composant à usage général sans rien connaître des étapes. Revenir en arrière est une **navigation purement locale** (décrémente l'index, ré-affiche l'étape précédente avec le brouillon déjà accumulé) — aucun ré-appel RPC, contrairement à "suivant".

**Vérifié** : suite de tests backend 96/96 (un échec du solveur en cours de route s'est avéré être un test flaky préexistant, sans rapport — repassé au vert isolément puis en suite complète), build de production Vite propre, et la séquence complète `rpc_get_available_modes` → `rpc_preview_composition` → `rpc_save_composition` rejouée via `curl` exactement comme `GenericWizard`/les deux widgets l'orchestreraient (mapping réaliste à 3 professeurs, avec vérification du recalcul du statut du cours parent). **Non vérifié** : le rendu visuel réel dans le navigateur (interdit par la constitution du projet, Principe II) — en particulier la mise en page des deux nouveaux widgets et la navigation effective entre les deux étapes.

### N. Troncature Silencieuse au-delà de 1000 Enregistrements — Corrigée (`fetchAllGenericItems`)

**Le problème découvert** : aucune vue de l'application ne fait de pagination serveur réelle. Chaque appelant de `api.fetchGenericList()` (18 sites, dans `App.vue`, `GenericListModal.vue`, `GenericPivot.vue`, `Many2ManyOrderedList.vue`, `PeriodTransitionManager.vue`, les widgets du wizard de décomposition) passait une limite fixe codée en dur — `1000` dans la grande majorité des cas, `2000`/`5000` pour `GenericPivot.vue` — jamais reliée à la pagination affichée dans `GenericList.vue` (`currentPage`/`perPage`), qui découpe en réalité un tableau **déjà entièrement chargé côté client**. Conséquence : toute ressource dépassant sa limite codée en dur voit ses enregistrements au-delà de ce seuil **silencieusement absents** de toutes les vues (listes, popins, pickers, pivot) — aucune erreur, aucun avertissement. Vérifié sur les volumes actuels (aucune ressource ne dépasse 216 lignes aujourd'hui, donc le bug n'était encore jamais déclenché en pratique) — mais un établissement réel (élèves, historique de vœux, créneaux sur une année) dépasserait facilement 1000 lignes sur plusieurs ressources.

**Distinction importante avec la pagination serveur réelle** (évoquée en discutant d'une éventuelle migration vers un composant de type `DataTable`, mode `lazy`) : ce correctif ne change pas l'architecture "tout charger en mémoire, paginer côté client" — il corrige seulement le fait que "tout" ne l'était pas vraiment. Une vraie pagination serveur (ne charger que la page affichée) reste un chantier séparé, plus lourd, hors périmètre ici.

**Correctif** : nouvelle fonction `api.fetchAllGenericItems(resourceName, schoolId?, filters?)`, qui boucle sur `fetchGenericList()` par pages de 500 (en utilisant le champ `total` déjà renvoyé par l'endpoint liste générique pour savoir quand s'arrêter) et concatène les résultats — retourne la même forme `{total, items}` que `fetchGenericList()`, donc les 18 sites d'appel n'ont eu à changer que le nom de la fonction (et l'ordre des arguments restants, `schoolId`/`filters` sans `skip`/`limit`), sans toucher au code appelant en aval. Élimine du même coup l'hétérogénéité des limites codées en dur (1000/2000/5000 selon l'endroit) — un seul mécanisme, un seul comportement, partout.

### O. Couche de Résolution de Semaine A/B au Glisser-Déposer (`BaseGrid.vue`) — codée en dur plutôt que via les slots génériques

**Contexte** : la résolution de l'alternance de semaine (`Course.week_type` A/B/Q, voir `attribution_week_type_auto.md`) peut désormais se faire par glisser-déposer manuel, en plus du solveur — chaque sous-cellule de `BaseGrid.vue` se scinde en deux zones de dépose (Semaine A / Semaine B) pendant le glisser d'un cours non-`W`.

**Pourquoi ce n'est PAS passé par le système de couches à slots existant** (`#cell-background`/`#cell-content`, section 15.A du présent document au sens fonctionnel, formalisé côté specs dans « Structure du Composant Grille ») : ces slots existent parce que leur contenu **diffère selon le consommateur** de `BaseGrid.vue` — `TimetableGrid.vue` y met la heatmap et les `CourseCard`, `PreferenceGrid.vue` y met la peinture de vœux. Le split A/B et l'ombre de survol, à l'inverse, sont un comportement **générique du glisser-déposer de cours**, identique pour tout consommateur qui déplace des cours — l'exposer comme un troisième slot personnalisable aurait obligé chaque futur consommateur à le réimplémenter pour rien. Ce comportement est donc codé en dur dans le template de `BaseGrid.vue` lui-même (une troisième couche, non slotée), piloté par deux nouvelles props (`weekType`, `draggedCourseWeekType`) — `PreferenceGrid.vue`, qui ne renseigne jamais `draggedCourseWeekType`, l'ignore simplement par construction (le `computed` de décision reste toujours faux).

**Mécanisme du split** :
- `TimetableGrid.vue` maintient un état local `draggedCourseWeekType` (recherche du cours par id dans `props.courses` au `dragstart`, remis à `null` au `dragend`) — **pas** lu depuis `DataTransfer.getData()` pendant le survol, illisible à ce stade pour des raisons de sécurité navigateur (seul `drop` y a accès), d'où cet état local dédié plutôt qu'une lecture différée.
- `shouldSplitCells` (computed, `BaseGrid.vue`) : vrai seulement si le filtre de semaine actif est `W` (Toutes) **et** le cours glissé n'est pas `W`.
- Le split est **strictement visuel/structurel** (contour seul, jamais de fond coloré ni de lettrage) pour ne pas masquer la coloration de poids/score de la couche d'arrière-plan sous-jacente (`layer-bg`) — décision explicite du produit, pas une contrainte technique.
- `dragend` (natif HTML5) se déclenche systématiquement en fin de glisser quelle que soit l'issue (drop réussi, annulé, relâché hors zone valide) — la disparition de la couche de split au relâchement est donc une conséquence directe et automatique du `v-if="shouldSplitCells"`, sans code de nettoyage dédié à écrire.

**Ombre portée au survol (préview de destination)** : réutilise le mécanisme *existant* de surbrillance (`dragOverCells`, prop déjà câblée de bout en bout `TimetableGrid.vue` → `GridContainer.vue` → `BaseGrid.vue`), simplement étendu par un suffixe de clé (`-A`/`-B`) pour distinguer la moitié survolée quand le split est actif — pas un système parallèle. Découverte en implémentant cette extension : la classe `.drag-over` existait déjà mais n'avait **jamais fonctionné**, un bug de sélecteur CSS préexistant (`.grid-cell.drag-over` dans `main.css`, alors que la classe est en réalité posée sur `.sub-cell` — jamais sur `.grid-cell`, règle totalement inatteignable) — corrigé au passage et réutilisé comme fondation (styles scoped `.sub-cell.drag-over`/`.split-half.drag-over` dans `BaseGrid.vue`, grisé neutre et transparent plutôt que la teinte violette d'origine, même logique de non-superposition avec la coloration de poids/score).

**Non vérifiable par l'IA** : le rendu visuel réel (positionnement du contour, lisibilité de l'ombre, comportement au relâchement) — test navigateur exclu par la constitution du projet (Principe II). Confirmation visuelle utilisateur nécessaire après toute modification de cette couche.
