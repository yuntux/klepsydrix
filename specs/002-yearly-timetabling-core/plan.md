# Plan d'Implémentation : Évolution vers l'Emploi du Temps Annuel Complet (V2)

**Branch**: `002-yearly-timetabling-core` | **Date**: 2026-05-17 | **Spec**: [specs/002-yearly-timetabling-core/spec.md](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md)

---

## Summary

Ce plan d'implémentation détaille la **seconde itération (V2)** de Klepsydrix. Contrairement à la V1 qui posait une tranche verticale simple (10 enseignants, 5 classes, 30 cours mono-créneaux), la V2 introduit la modélisation métier complète d'une **Cité Scolaire** (coexistence de structures collège/lycée avec cloisonnement et ressources partagées), la **gestion fine des alternances (Semaines A/B)**, la **subdivision en groupes d'élèves compatibles ou exclusifs**, la **grille tricolore de vœux des enseignants/salles**, le suivi budgétaire national (**TRMD, ETP et MEF**) et une **IHM Fiche T déplaçable** par drag-and-drop consolidant les attributs en lot.

**Approche Évolutive Cible** : Nous capitalisons entièrement sur le code robuste de la V1 (FastAPI, SQLAlchemy, SQLite, Timefold, Vue 3 SPA). Nous faisons évoluer la base de données de manière incrémentale par migrations SQL, modifions les modèles et les contraintes du solveur existant, et enrichissons l'IHM avec de nouveaux composants dynamiques (Fiche T déplaçable, grilles de vœux, gestionnaire d'établissement).

---

## Technical Context

* **Language/Version** : Python 3.11/3.12 (Strict - en raison du pont JPype JVM requis par Timefold Solver) | TypeScript 5.3+ (Frontend Vue 3).
* **Primary Dependencies** :
  * *Backend* : `fastapi`, `uvicorn`, `sqlalchemy>=2.0`, `pydantic>=2.0`, `pydantic-settings`, `timefold>=0.1.0`, `pytest`.
  * *Frontend* : `vue>=3.4`, `vite`, `typescript`.
* **Storage** : SQLite (`timetable.db`). L'activation des clés étrangères (`PRAGMA foreign_keys = ON;`) est garantie à chaque connexion via un écouteur SQLAlchemy pour maintenir une intégrité parfaite.
* **Testing** : TDD via `pytest`. Les tests de validation couvrent le nouveau solveur à alternance quinzaine, les incompatibilités de groupes, les budgets ETP et les nouvelles routes API.
* **Performance Goals** :
  * Temps de résolution du solveur < 10 secondes pour une structure pilote (500 élèves, 40 enseignants, 30 salles, 20 classes).
  * Consolidation visuelle de la Fiche T < 50ms pour 50 cours.
  * Pas de gel de l'IHM lors des calculs (Supervision asynchrone).

---

## Constitution Check

*GATE: Alignement total avec la constitution v1.1.0.*

* **I. Clean Architecture** : Séparation front/back conservée. Communication REST JSON strictement typée via des schémas Pydantic évolués.
* **II. Rigorous Testing (TDD)** : Aucun test par navigateur. Couverture par tests unitaires `pytest` sur la logique d'incompatibilité de groupes, le calcul du TRMD et les contraintes d'alternance semaine A/B.
* **III. Premium Vue 3 UX** : Utilisation de transitions CSS Vanilla fluides. drag-and-drop natif (HTML5 Drag & Drop) enrichi pour la grille et implémenté sur l'en-tête de la Fiche T pour la déplacer sans geler l'interface.
* **IV. High-Performance Solving** : Timefold Solver résout le modèle en mémoire vive. SQLite persiste le graphe relationnel.
* **V. French Documentation & Pedagogical Rigor** : Spécifications et plans rédigés en français détaillé et pédagogique. Noms de variables et tables SQL en anglais.

---

## Architecture Évolutive : Modifications vs Nouveautés

Pour éviter de repartir de zéro et garantir une transition harmonieuse, voici la répartition exacte des modifications et créations de fichiers.

### 1. Évolution du Modèle de Données (SQLite & ORM)

Pour la définition exhaustive et fonctionnelle de tous les attributs de ces objets, la source unique de vérité est la section [## Spécification Détaillée des Objets](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#spcification-dtaille-des-objets-et-de-leurs-attributs) de `spec.md`.

#### Fichiers existants à MODIFIER :
* **`backend/app/models/teacher.py`** : Évolue pour inclure la couleur d'affichage et l'école principale de rattachement (voir [spec.md#2-teachers](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#2-teachers)).
* **`backend/app/models/course.py`** : Divisé en deux tables pour dissocier le cours (pédagogique) de sa planification physique (voir [spec.md#1-course](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#1-course) et [spec.md#séance-session](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#114-séance-session)).
* **`backend/app/models/timeslot.py`** : Conserve ses attributs hebdomadaires (Lundi-Samedi, 8h-17h).
* **`backend/app/models/classroom.py`** : Évolue pour inclure le site géographique (voir [spec.md#10-classroom](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#10-classroom)).

#### Nouveaux Fichiers de Modèles à CRÉER :
* **`backend/app/models/school.py`** : Établissement administratif (école) pour Cité Scolaire (voir [spec.md#0-school](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#0-school)).
* **`backend/app/models/subject.py`** : Nomenclature nationale de disciplines (voir [spec.md#3-subjects](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#3-subjects)).
* **`backend/app/models/mef.py`** : Gabarits nationaux de formation STSWEB et heures réglementaires (voir [spec.md#4-mef](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#4-mef)).
* **`backend/app/models/trmd_budget.py`** : Budgets alloués par matière (voir [spec.md#trmd](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#26-trmd)).
* **`backend/app/models/group.py`** : Parties de classe et exclusions (voir [spec.md#5-classpart](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#5-classpart)).
* **`backend/app/models/preference.py`** : Table unifiée des vœux et indisponibilités liée aux périodes (voir [spec.md#11-resourcepreference](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#11-resourcepreference)).
* **`backend/app/models/period.py`** : Découpages temporels calendaires (voir [spec.md#14-period](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#14-period)).
* **`backend/app/models/alternation.py`** : Alternances cycliques (Semaines A/B) (voir [spec.md#7-alternation](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#7-alternation)).
* **`backend/app/models/site.py`** : Campus géographiques et temps de trajet inter-sites (voir [spec.md#8-site](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#8-site)).
* **`backend/app/models/mission.py`** : Missions d'enseignement ou d'accompagnement (voir [spec.md#12-mission](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#12-mission)).
* **`backend/app/models/election_method.py`** : Modalités d'élection réglementaires (voir [spec.md#13-electionmethod](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#13-electionmethod)).
* **`backend/app/models/material.py`** : Équipements et ressources réservables (voir [spec.md#9-material](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#9-material)).
* **`backend/app/models/session.py`** : Séances physiques et réservations de co-ressources (voir [spec.md#1bis-session](file:///home/ubuntu/klepsydrix/specs/002-yearly-timetabling-core/spec.md#1bis-session)).


---

### 2. Évolution du Solveur de Contraintes (Timefold)

#### Fichiers existants à MODIFIER :
* **`backend/app/solver/constraints.py`** :
  * Adapter `PlanningCourse` pour représenter une `PlanningSession` (car un cours peut donner lieu à plusieurs séances physiques Semaine A / Semaine B).
  * Ajouter la variable `week_type` dans l'analyse de collision.
  * Mettre à jour les contraintes d'exclusion mutuelle :
    * **Resource Collision (Teacher / Room / Division)** : Une collision n'est pénalisée (Hard) que si les deux séances s'exécutent sur la même semaine administrative (ex: deux séances A, ou une séance A et une séance T. Deux séances sur A et B ne collisionnent pas).
    * **Incompatibilité de Groupes** : Deux séances visant des `ClassPart` incompatibles (liées par `ClassPartLink`) ne peuvent pas se chevaucher sur la même semaine.
    * **Strict Unavailability (Créneaux Rouges)** : Pénalité dure (Hard) si une séance est affectée sur un créneau marqué comme `Unsuited` pour l'enseignant, la classe ou la salle.
  * Mettre à jour les contraintes souples (Soft) :
    * **Preferences (Orange / Vert)** : Pénalités pour les créneaux oranges, récompenses pour les créneaux verts.
    * **Trajet Inter-sites** : Pénaliser les enseignants ou classes contraints de changer de `Site` sur deux créneaux consécutifs.
* **`backend/app/solver/solver.py`** :
  * Adapter `_build_planning_problem` pour charger uniquement les données de l'école active (`school_id`), tout en chargeant les séances déjà placées des autres écoles comme des obstacles statiques et fixes (les séances des autres écoles sont chargées avec `is_pinned=True` pour éviter tout conflit sur les professeurs ou les salles communes !). C'est une solution élégante et extrêmement performante pour le multi-établissement.

---

### 3. Évolution des APIs (FastAPI)

#### Fichiers existants à MODIFIER :
* **`backend/app/api/endpoints.py`** :
  * Faire évoluer `GET /api/timetable` pour accepter le paramètre de filtre `school_id`.
  * Rendre l'API CRUD robuste pour les nouvelles tables. Pour cela, au lieu de coder 10 routeurs distincts, nous ajoutons un routeur générique réutilisable dans `backend/app/api/generic.py` qui s'appuie sur SQLAlchemy pour générer à la volée les listes et formulaires simples des entités de base, tout en préservant le routeur spécifique pour les cours, la résolution et le TRMD.
  * Adapter `PUT /api/timetable/courses/{course_id}` (qui devient `/api/timetable/sessions/{session_id}`) pour vérifier les chevauchements en prenant en compte les groupes exclusifs (`ClassPartLink`), les alternances de semaines (`week_type`) et le co-enseignement.
  * **Simulation de modification de structure** : Ajouter un endpoint `POST /api/timetable/structures/simulate-change` qui liste tous les cours et séances actuellement placés qui vont être impactés (et donc dépositionnés en statut `UNPLACED`) lors de la modification ou suppression d'un groupe, d'une division ou d'une ressource. Lors de la confirmation par `POST /api/timetable/structures/apply-change`, le système libère les créneaux et enregistre un diagnostic de dépositionnement pour l'utilisateur.

---

### 4. Évolution du Frontend (Vue 3 + CSS)

#### Fichiers existants à MODIFIER :
* **`frontend/src/components/TimetableGrid.vue`** :
  * Modifier le rendu pour afficher l'alternance de semaine (séance coupée en deux horizontalement ou verticalement si c'est Semaine A / Semaine B, ou pleine largeur si c'est Toutes les semaines).
  * Gérer le Drag and Drop natif HTML5 sur les sous-créneaux de semaine.
* **`frontend/src/components/HeaderControls.vue`** :
  * Ajouter le menu déroulant global de sélection de l'établissement actif (chargeant dynamiquement l'emploi du temps correspondant).
* **`frontend/src/App.vue`** :
  * Gérer la multisélection de cours (en maintenant la touche `Ctrl` ou `Shift` ou par clic successif).
  * Afficher la popin Fiche T en cas de multisélection.
  * **Boîte de dialogue de confirmation de structure** : Intercepter les modifications d'entités structurantes dans les formulaires d'administration pour afficher une popin listant les cours qui repasseront en `UNPLACED`, avec confirmation et affichage de l'historique de diagnostic.

#### Nouveaux Fichiers Frontend à CRÉER :
* **`frontend/src/components/FicheT.vue`** : La popin de consultation cumulée. Elle est rendue en position absolue CSS.
  * **Comportement Déplaçable** : Géré via des écouteurs `mousedown` sur son en-tête pour calculer le delta souris et repositionner la popin sur l'écran en temps réel.
  * **Visualisation par Puces (Chips)** : Analyse des attributs des cours sélectionnés. Les attributs divergents affichent des chips contrastées dotées de badges de proportions (ex: `M. Martin [2/3]`, `Mme. Petit [1/3]`).
* **`frontend/src/components/VoeuxGrid.vue`** (implémenté sous `PreferenceGrid.vue`) : Grille horaire interactive tricolore permettant à un enseignant ou pour une salle de définir graphiquement ses préférences par clic/glisser (Rouge = indisponible, Orange = évitable, Vert = préféré, Gris = neutre).
  * **Évolution Multi-sélection** :
    * Chargement en parallèle (`Promise.all`) des vœux de tous les enseignants sélectionnés si le tableau d'IDs comporte plusieurs éléments.
    * Algorithme de consolidation de la couleur par créneau :
      * Couleur unie si tous les enseignants sélectionnés partagent la même préférence.
      * Motif hachuré léger (via CSS `repeating-linear-gradient`) si les préférences sont partielles (hachuré vert/orange/rouge mélangé avec du neutre) ou divergentes (hachuré bleu).
    * Peinture en lot : application du changement de vœu sur l'ensemble des enseignants sélectionnés en parallèle avec rollback en cas d'échec.
    * Bouton d'aide ❓ et popin modale affichant la légende complète illustrée.
* **`frontend/src/components/NotebooksTree.vue`** : Composant de navigation dynamique par onglets (notebooks) imbriqués, alimenté par le JSON de configuration. Il gère l'application des styles spécifiques (en-tête à fond coloré ou liseré supérieur).
* **`frontend/src/components/SplitPanel.vue`** : Conteneur de mise en page capable de scinder son espace en 1 à N panneaux verticaux séparés par des barres de redimensionnement interactif (splitter) gérées par glisser-déposer de la souris.
* **`frontend/src/config/notebooks.json`** : Fichier de configuration déclarative décrivant l'arbre complet des onglets, leur style et leurs panneaux de contenu.
* **`frontend/src/components/GenericList.vue`** : Tableau générique dynamique qui interroge l'API de métadonnées backend pour construire ses colonnes, ses tris et afficher les instances.
* **`frontend/src/components/GenericForm.vue`** : Formulaire dynamique intelligent qui s'auto-génère en lisant le JSON-Schema fourni par le backend pour l'entité (champs textes, selects relationnels, booléens).
* **`frontend/src/pages/Admin.vue`** : Page d'administration unifiée permettant de basculer entre la gestion des 10 entités de base à l'aide des composants génériques `GenericList` et `GenericForm`.



---

## Project Structure

Voici le plan des fichiers à modifier ou ajouter, parfaitement intégré à l'architecture existante de la V1 :

```text
backend/
├── app/
│   ├── models/
│   │   ├── base.py
│   │   ├── teacher.py       # MODIFIÉ (color, primary_school_id)
│   │   ├── classroom.py     # MODIFIÉ (site_id)
│   │   ├── division.py      # MODIFIÉ (mef_id)
│   │   ├── course.py        # MODIFIÉ (séparé en Course et Session)
│   │   ├── timeslot.py
│   │   ├── school.py        # NOUVEAU (Entité pivot multi-école/établissement)
│   │   ├── subject.py       # NOUVEAU (Nomenclature nationale)
│   │   ├── mef.py           # NOUVEAU (Gabarits d'heures nationaux)
│   │   ├── trmd_budget.py   # NOUVEAU (Budgets ETP/HSA par discipline)
│   │   ├── group.py         # NOUVEAU (Parties de classe et incompatibilités)
│   │   ├── preference.py    # NOUVEAU (Table de vœux tricolore)
│   │   ├── period.py        # NOUVEAU (Découpages temporels calendaires)
│   │   ├── alternation.py   # NOUVEAU (Alternances cycliques Semaines A/B)
│   │   ├── site.py          # NOUVEAU (Campus géographiques et temps de trajet)
│   │   ├── mission.py       # NOUVEAU (Missions d'enseignement et décharges)
│   │   ├── election_method.py # NOUVEAU (Modalités d'élection réglementaires)
│   │   ├── material.py      # NOUVEAU (Équipements et ressources réservables)
│   │   └── session.py       # NOUVEAU (Séances physiques et co-ressources)
│   ├── api/
│   │   ├── endpoints.py     # MODIFIÉ (Filtre établissement, alternances, conflits)
│   │   └── generic.py       # NOUVEAU (Moteur CRUD générique dynamique pour les entités simples)
│   └── solver/
│       ├── constraints.py   # MODIFIÉ (Intégration d'incompatibilité groupes, A/B, vœux)
│       └── solver.py        # MODIFIÉ (Résolution asynchrone par établissement + pins statiques)
└── tests/
    ├── test_crud.py         # NOUVEAU (Validation du CRUD générique)
    ├── test_solver.py       # MODIFIÉ (Validation des contraintes A/B et groupes)
    └── test_api.py          # MODIFIÉ (Validation du cloisonnement établissement)

frontend/
├── src/
│   ├── config/
│   │   └── notebooks.json     # NOUVEAU (Structure déclarative des onglets)
│   ├── components/
│   │   ├── TimetableGrid.vue  # MODIFIÉ (Rendu A/B, Drag-and-drop semaine)
│   │   ├── Sidebar.vue        # MODIFIÉ (Affichage des cours non placés par établissement)
│   │   ├── HeaderControls.vue # MODIFIÉ (Dropdown établissement actif)
│   │   ├── FicheT.vue         # NOUVEAU (Popin déplaçable de consultation cumulée par Chips)
│   │   ├── VoeuxGrid.vue      # NOUVEAU (Grille interactive tricolore des vœux)
│   │   ├── GenericList.vue    # NOUVEAU (Composant de tableau dynamique introspectif)
│   │   ├── GenericForm.vue    # NOUVEAU (Composant de formulaire dynamique auto-généré)
│   │   ├── NotebooksTree.vue  # NOUVEAU (Composant générique d'onglets imbriqués)
│   │   └── SplitPanel.vue     # NOUVEAU (Conteneur multi-panneaux redimensionnables)
│   ├── pages/
│   │   └── Admin.vue          # NOUVEAU (Panneau d'administration CRUD unifié)
│   └── App.vue                # MODIFIÉ (Orchestration principale par NotebooksTree)
```


---

## Complexity Tracking

Le principe fondamental de cette itération est de conserver une **complexité minimale** tout en offrant des fonctionnalités premium :
1. **Cloisonnement multi-établissement** : Pas de bases de données multiples ou de schémas complexes. Une seule base SQLite, les entités d'autres établissements étant chargées comme des obstacles immobiles (`is_pinned=True`) pour le solveur. Simple, performant et 100% robuste.
2. **Formulaires et listes génériques** : Plutôt que de dupliquer 10 formulaires Vue et 10 contrôleurs backend pour les entités secondaires, l'introspection de schémas Pydantic / JSON-Schema automatise le rendu de l'IHM, réduisant le boilerplate à zéro.
3. **Draggable Popin sans dépendances** : Le drag-and-drop de la Fiche T est écrit en JS/TS natif via de simples coordonnées absolues et écouteurs d'événements souris, garantissant un contrôle total sur le style et l'absence de régression.
