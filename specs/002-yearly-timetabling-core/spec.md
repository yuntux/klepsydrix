# Feature Specification: Améliorations Fonctionnelles et Socle Technique pour l'Emploi du Temps Annuel

**Feature Branch**: `002-yearly-timetabling-core`

**Created**: 2026-05-17

**Status**: Draft

## Clarifications

### Session 2026-05-17
- Q: Mode d'interaction et filtrage pour la gestion multi-établissement (Cité Scolaire) → A: Option A (Affichage contextuel : un menu déroulant global permet de sélectionner l'établissement actif. La grille et les listes n'affichent par défaut que ses ressources/classes/cours, tout en préservant la visibilité et la protection contre les conflits des professeurs et salles partagés).
- Q: Échelle et volume de données cibles (Stress-test & Performance) → A: Option B (Structure pilote / Petite taille : jusqu'à 500 élèves, 40 enseignants, 30 salles, 20 classes).
- Q: Déclarations de Hors-Scope (Out-of-Scope) → A: Option A (Exclusion de l'affectation nominative/individuelle des élèves dans les groupes, et de la synchronisation collaborative temps réel).
- Q: Résolution des conflits lors de la modification de structures déjà planifiées → A: Option A (Dépositionnement automatique des cours impactés vers le statut UNPLACED avec boîte de dialogue de confirmation et historique de diagnostic).
- Q: Consolidation visuelle des attributs divergents dans la Fiche T (Fiche Cours Cumulée) → A: Option A (Consolidation par Chips stylisées : les attributs communs s'affichent normalement et les attributs divergents sont regroupés sous forme de pastilles/chips avec un indicateur visuel de divergence et un badge de proportion comme `[2/3]`).
- Q: Positionnement de la Fiche T sur l'écran → A: Popin déplaçable (draggable) par glisser-déposer de son en-tête pour ne pas masquer la grille horaire en dessous.

## Out of Scope
Pour cette itération, les fonctionnalités suivantes sont explicitement exclues du périmètre technique et fonctionnel :
1. **Affectation nominative individuelle des élèves** : Le système gère uniquement les structures (Divisions, ClassParts, Groupes) avec leurs effectifs numériques globaux. Aucun suivi nominatif individuel ou gestion d'inscriptions d'élèves par fiche n'est inclus.
2. **Synchronisation collaborative temps réel** : La gestion des conflits d'édition simultanée par plusieurs utilisateurs (type Google Docs) est exclue. Le verrouillage standard de la base SQLite et des sessions utilisateur classiques suffit.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Saisie et gestion du socle via le CRUD Générique (Priority: P1)

En tant qu'administrateur scolaire, je veux pouvoir ajouter, modifier, lister et supprimer l'ensemble des ressources de base de l'établissement (Matières, Professeurs, Groupes, Salles, Classes, Parties de classe, Alternances, Sites, Matériels, Créneaux) via des formulaires et des listes unifiés et génériques, afin de ne pas avoir à réimplémenter du code répétitif pour chaque nouvel écran de saisie.

**Why this priority**: C'est le fondement indispensable de l'application. Sans saisie propre de l'ensemble de ces données de base interconnectées, aucun emploi du temps ne peut être planifié ou calculé.

**Independent Test**: L'utilisateur peut ajouter n'importe quelle ressource (ex: un nouveau Site ou un nouveau Matériel) via le système de formulaires génériques, et la voir instantanément dans la table générique associée, prête à être rattachée à des cours.

**Acceptance Scenarios**:

1. **Given** un formulaire générique de création vide pour n'importe quelle entité de base, **When** l'utilisateur remplit les champs requis et valide, **Then** la ressource est enregistrée en base de données et listée dynamiquement.
2. **Given** un cours existant, **When** le planificateur consulte sa fiche ou sa popin, **Then** il peut y rattacher de manière optionnelle ou obligatoire les différentes ressources correspondantes (Matières, Professeurs, Groupes, Salles, Classes, Parties de classe, Alternances, Sites, Matériels), et l'affecter à au plus 1 créneau (0 ou 1) de la grille.

---

### User Story 2 - Planification avancée annuelle (Alternances A/B, Groupes) (Priority: P1)

En tant que planificateur, je veux pouvoir définir des alternances (Semaine A / Semaine B) pour les cours en quinzaine, et découper mes divisions (classes) en sous-groupes (ex: demi-classes, groupes de spécialités), afin de gérer la complexité réelle d'un établissement scolaire.

**Why this priority**: C'est ce qui distingue un prototype d'un véritable outil d'emploi du temps annuel pour collèges et lycées.

**Independent Test**: L'utilisateur peut diviser la classe de "3ème A" en deux groupes "Groupe 1" et "Groupe 2", et planifier un cours de TP de Physique pour le "Groupe 1" uniquement en Semaine A, et un autre pour le "Groupe 2" en Semaine B.

**Acceptance Scenarios**:

1. **Given** une division existante, **When** l'utilisateur définit un découpage en groupes, **Then** ces sous-groupes deviennent éligibles comme destinataires d'un cours.
2. **Given** un cours de quinzaine, **When** le cours est assigné à la Semaine A, **Then** le solveur s'assure qu'aucun conflit n'est généré sur la semaine B pour les mêmes ressources.

---

### User Story 3 - IHM Métier : La Fiche Cours Cumulée "Fiche T" (Priority: P2)

En tant que planificateur, lorsque je sélectionne plusieurs cours sur ma grille ou dans ma liste, je veux voir apparaître une popin unifiée (sous forme de Fiche T à l'ancienne) qui résume visuellement toutes les données de ces cours, par type d'objet lié (matière, enseignant, salle, division, créneau), afin d'avoir une vision synthétique claire de ma sélection sans pouvoir la modifier directement depuis cet écran. Je veux pouvoir déplacer (glisser-déposer de son en-tête) cette popin de petite taille sur l'écran afin de ne pas masquer la grille horaire située en dessous.

**Why this priority**: Permet un diagnostic et une consultation rapide des détails d'une sélection complexe de cours (enseignants, salles, divisions, créneaux) sans surcharger l'écran principal.

**Independent Test**: Sélectionner 3 cours distincts sur la grille, ouvrir la Fiche T, déplacer la popin à un autre endroit de l'écran par drag-and-drop, et valider que l'ensemble de leurs détails consolidés (matières, enseignants, salles) s'affiche fidèlement.

**Acceptance Scenarios**:

1. **Given** plusieurs cours sélectionnés, **When** l'utilisateur ouvre la Fiche T cumulée, **Then** les attributs communs (ex: même matière) s'affichent normalement et les attributs divergents (ex: salles différentes) sont clairement identifiés et consolidés.
2. **Given** la Fiche T affichée, **When** l'utilisateur clique-glisse l'en-tête de la popin, **Then** la popin suit le mouvement de la souris et se repositionne à l'endroit désigné, sans interférer avec la grille d'emploi du temps sous-jacente.

---

### User Story 4 - Saisie et Gestion Générique des Vœux et Indisponibilités (Priority: P2)

En tant que planificateur ou enseignant, je veux pouvoir colorer une grille horaire réutilisable pour définir les préférences et indisponibilités de *n'importe quelle ressource* (enseignants, classes, groupes, salles, équipements) : rouge pour "Indisponible" (strictement bloquant), orange pour "Souhait d'absence" (pénalisé par le solveur), et vert pour "Souhait de présence" (favorisé/récompensé par le solveur), afin que l'emploi du temps généré respecte toutes les contraintes de l'établissement.

**Why this priority**: C'est une fonctionnalité essentielle pour la flexibilité et la qualité globale de l'emploi du temps. La gestion générique évite de devoir réécrire un modèle de contrainte pour chaque type de ressource.

**Independent Test**: Définir une salle de sport (Gymnase) indisponible le lundi matin (Rouge), un enseignant souhaitant ne pas travailler le mardi après-midi (Orange), et une classe de Terminale souhaitant être libérée le mercredi matin (Orange) mais favorisant le jeudi matin (Vert). Lancer le solveur et valider que toutes ces règles de ressources diverses sont arbitrées et respectées.

**Acceptance Scenarios**:

1. **Given** la grille des vœux générique d'une ressource sélectionnée, **When** l'utilisateur clique-glisse avec le pinceau (rouge, orange, vert), **Then** les créneaux horaires stockent la préférence correspondante pour cette ressource.
2. **Given** une ressource affectée à un cours sur un créneau marqué en rouge pour elle, **When** le solveur tente de placer le cours, **Then** une contrainte dure (Hard Constraint) bloque ce placement.
3. **Given** une ressource affectée à un cours sur un créneau marqué en orange ou vert, **When** le solveur arbitre la solution, **Then** le score souple (Soft Constraint) est respectivement pénalisé ou récompensé en fonction de la préférence.

---

### Edge Cases

- **Chevauchement de vœux et de cours verrouillés** : Si un cours est manuellement épinglé (pinned) sur un créneau qu'un professeur a marqué en rouge (Indisponible), le système doit alerter l'utilisateur de ce conflit direct.
- **Modification de groupes contenant des élèves / ressources planifiées** : Si un groupe, une division ou une ressource (professeur, salle) est supprimée ou modifiée en profondeur alors que des séances y sont déjà placées sur la grille, le système présente une boîte de dialogue de confirmation listant les cours impactés. Après validation de l'utilisateur, les cours affectés sont automatiquement dépositionnés sur la grille (leur statut repasse en `UNPLACED` et leur créneau est libéré) afin de maintenir la cohérence de la base.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: **Moteur CRUD Générique (Socle)** : Le système doit fournir un mécanisme générique côté backend et frontend pour générer les formulaires et les listes pour toutes les entités de base (y compris les nomenclatures) : *Matières, Professeurs, Groupes, Salles, Classes, Parties de classe, Alternances, Sites, Matériels, Créneaux, MEFs, Disciplines, Missions, Méthodes d'élection et Périodes*.
- **FR-002**: **APIs Génériques** : Le backend doit exposer des points d'accès API unifiés, typés et réutilisables pour les opérations CRUD de chaque type de ressource de base.
- **FR-003**: **Composants Frontend Réutilisables** : Le frontend doit utiliser des composants de tableau (`GenericList`) et de formulaire (`GenericForm`) paramétrables pour éviter la duplication de code pour tous les types de ressources.
Concernant le composant `GenericList`, il est fortement recommandé d'intégrer une librairie VueJS existante sur internet (ex: PrimeVue DataTable, AG Grid ou Tabulator) pour offrir nativement les fonctionnalités suivantes :
  1. Pagination (par défaut 30 éléments par page, avec possibilité de modifier ce nombre).
  2. Redimensionnement manuel de la largeur des colonnes.
  3. Réordonnancement des colonnes via glisser-déposer (drag-and-drop) de leurs en-têtes.
  4. Sélecteur de colonnes accessible via un bouton en haut à droite permettant de cocher/décocher les colonnes à afficher.
  5. Tri des données en cliquant sur l'en-tête de n'importe quelle colonne.
  6. Recherche / filtrage spécifique sur chaque colonne.
  *(Note : L'implémentation d'une fonction de regroupement de lignes n'est pas requise).*
- **FR-004**: **Gestion des Alternances (Quinzaine)** : Le modèle de données et le solveur doivent supporter les alternances temporelles (Semaine A / Semaine B / Toutes les semaines).
- **FR-005**: **Gestion des Groupes et Sous-groupes** : Les divisions doivent pouvoir être partitionnées en sous-groupes (ex: demi-classes, groupes de spécialités), avec support des conflits d'intersection d'élèves par le solveur.
- **FR-006**: **Fiche Cours Cumulée (Fiche T)** : Une popin métier unifiée doit permettre de visualiser et de consulter de manière synthétique et consolidée les caractéristiques d'une sélection multiple de cours. Les ressources communes (ex: même matière) s'affichent de façon standard, tandis que les ressources divergentes (ex: enseignants ou salles différents) sont regroupées sous forme de pastilles (chips) stylisées dotées d'un indicateur visuel de divergence (bordure ou couleur contrastée) et d'un badge de proportion (ex: `[2/3]`). **La popin doit être déplaçable (draggable) par glisser-déposer (drag-and-drop) de son en-tête**, afin de permettre au planificateur de dégager la vue sur la grille horaire sous-jacente.
- **FR-007**: **Grille de Vœux Générique** : L'IHM doit proposer une grille interactive réutilisable permettant de saisir graphiquement les indisponibilités (Rouge - contrainte dure), les souhaits d'absence (Orange - contrainte souple négative) et les souhaits de présence (Vert - contrainte souple positive) pour n'importe quelle ressource (Enseignants, Salles, Divisions, Équipements).
- **FR-008**: **Calcul Polymorphique des Vœux** : Le solveur Timefold doit intégrer les vœux et indisponibilités de manière générique dans son modèle de contraintes (Hard pour les créneaux rouges de toute ressource affectée, Soft pénalité pour les créneaux oranges, Soft bonus pour les créneaux verts).
- **FR-009**: **Objet Cours, Durée et Attributs Métiers** : Chaque cours doit porter des attributs propres définis en amont de son placement : une durée (exprimée en nombre de créneaux élémentaires ou minutes), un libellé (généré dynamiquement à partir des ressources rattachées), un mémo (texte libre) et une planification sur la grille horaire via des séances rattachées (0 ou 1 créneau de départ, avec extension contiguë sur la durée du cours).
- **FR-010**: **Données de Démo Réalistes** : La base de données SQLite doit être alimentée par défaut avec un jeu d'essai réaliste et complet couvrant les 9 types de ressources rattachables, plusieurs cours complexes N-à-N créés, et des grilles de vœux pré-remplies (avec créneaux rouges, oranges, verts) pour plusieurs profs/salles, afin de permettre un test direct.
- **FR-011**: **Filtrage Multi-Établissement (Cité Scolaire)** : L'interface utilisateur doit proposer un menu déroulant global permettant de sélectionner l'établissement actif (ex: Collège). La grille et les listes n'affichent par défaut que les ressources (classes, cours) de l'établissement actif, tout en préservant la protection contre les conflits et la visibilité des ressources partagées (professeurs, salles communes).


### Key Entities

- **Course (Cours)** : Le conteneur logique de planification. Il peut être de deux types :
  *   **Cours Simple** : Composé d'une seule **Séance** (Session).
  *   **Cours Complexe** : Regroupe plusieurs **Séances** s'organisant à l'intérieur de ce cours. Ces séances peuvent être placées en parallèle (alignements, ex: barrettes de langues, groupes de spécialités) ou à la suite (pour forcer leur succession temporelle).
- **Séance (Session)** : L'unité réelle de placement sur la grille horaire. Chaque séance possède ses propres ressources rattachées (matières, profs, classes, etc.) et est positionnée sur 0 ou 1 créneau.
- **Ressources de base rattachables à une séance (Relations N-à-N / Many-to-Many)** :
  *   **Subjects (Matières)** : La ou les matières enseignées lors de la séance (ex : Mathématiques, Physique-Chimie).
  *   **Teachers (Professeurs)** : Le ou les enseignants encadrant la séance (supportant le co-enseignement).
  *   **Divisions (Classes)** : La ou les classes d'élèves entières associées (regroupements de classes).
  *   **ClassParts (Parties de classe)** : Une ou plusieurs sous-parties de classes (ex : Demi-classe de 3ème A - Groupe 1).
  *   **Groups (Groupes)** : Un ou plusieurs regroupements d'élèves (ex : Groupe d'Allemand LV2, Spécialité Physique).
  *   **Alternations (Alternances)** : La ou les alternances temporelles définissant le rythme (Semaine A, Semaine B, ou Toutes les semaines).
  *   **Sites** : Le ou les sites physiques ou campus géographiques associés à la séance.
  *   **Materials (Matériels / Équipements)** : Le ou les matériels mobiles ou fixes réservables (ex : Valise d'iPad, Projecteur 3D).
  *   **Classrooms (Salles)** : La ou les salles de classe affectées (ex : Salle 102, Labo SVT).
- **ResourcePreference** : Association polymorphique entre n'importe quel type de ressource listé ci-dessus, un créneau (Timeslot) et un niveau de préférence (Disponible [Blanc], Souhait d'absence [Orange], Indisponible [Rouge], Souhait de présence [Vert]).
- **Period (Période)** : Découpage temporel de l'année scolaire (trimestres, semestres, etc.).
- **ResourceConstraint (Contrainte de Ressource)** : Définition globale pour toute l'année des contraintes réglementaires, pédagogiques ou géographiques rattachées à une ressource unique (matière, enseignant, classe, etc.). Les caractéristiques de ces contraintes s'adaptent dynamiquement selon le type de ressource.

## Spécification Détaillée des Objets et de leurs Attributs

Voici la définition formelle de chaque objet et de sa structure de données :

### 0. School (Établissement)
Représente une entité administrative scolaire autonome (un collège, un lycée général, un lycée professionnel) coexistant au sein de la même base de données (concept de **Cité Scolaire**). Cela permet aux établissements de partager les ressources communes (professeurs partagés, salles communes, même campus) tout en conservant une gestion budgétaire, des imports/exports STSWEB et des structures de classes strictement séparés.
*   `id` : Clé primaire (Entier)
*   `uai` : Code national unique de l'établissement (anciennement RNE) (Chaîne de 8 caractères, ex: "0751234A")
*   `name` : Nom officiel de l'établissement (Chaîne, ex: "Lycée Molière")
*   `type` : Type d'établissement (Enum : `COLLEGE`, `LYCEE`, `LYCEE_PRO`, `AUTRE`)
*   `city` : Ville (Chaîne)
*   `postal_code` : Code postal (Chaîne)
*   `standard_timeslot_duration` : Durée standard d'un créneau élémentaire (Entier, exprimée en minutes, par défaut `30`). Cela permet au solveur de convertir dynamiquement les durées des cours en nombre de créneaux.

### 1. Course (Cours)
Le conteneur logique de cours.
*   `id` : Clé primaire (Entier)
*   `subject_id` : Clé étrangère vers la **Matière** principale enseignée (Entier, relation N-à-1)
*   `teacher_id` : Clé étrangère optionnelle vers le **Professeur** principal (Entier, relation N-à-1)
*   `division_id` : Clé étrangère optionnelle vers la **Classe** principale visée (Entier, relation N-à-1)
*   `group_id` : Clé étrangère optionnelle vers le **Groupe** visé (Entier, relation N-à-1)
*   `label` : Libellé textuel calculé de manière dynamique à partir des séances et ressources rattachées (ex : `"{matières} - {profs} - {classes}"`)
*   `memo` : Texte libre (Chaîne optionnelle) pour les notes du planificateur
*   `duration_minutes` : Durée du cours définie en amont du placement (Entier, exprimée en minutes, ex: `55` pour un cours standard d'une heure)
*   `is_complex` : Indicateur s'il s'agit d'un cours complexe (Booléen, par défaut `False`)
*   `lock_sessions` : Si vrai, verrouille l'ordre ou la répartition des séances à l'intérieur du cours complexe (Booléen, par défaut `False`)
*   `mission_id` : Clé étrangère optionnelle vers une **Mission** (Entier, ex: pour lier un cours à un rôle spécifique comme Professeur Principal)
*   `election_method_id` : Clé étrangère optionnelle vers une **ElectionMethod** (Entier, ex: pour lier à un cours de type DNL)
*   `family_id` : Clé étrangère optionnelle vers une **Family** de type `Course` (Entier, ex: pour regrouper des cours d'une même option ou spécialité)
*   `status` : État du cours calculé de manière dynamique à partir du positionnement de ses séances et des contraintes (Chaîne, calculée) :
    *   `UNPLACED` : Aucune séance planifiée sur la grille.
    *   `PLACED` : Toutes ses séances sont planifiées sans aucun conflit.
    *   `PARTIALLY_PLACED` : Pour un cours complexe, seulement une partie de ses séances sont placées.
    *   `CONFLICT` : Conflit de ressources (double réservation de prof, salle, classe) ou non-respect d'une indisponibilité stricte (`RED`).
    *   `LOCKED` : Cours dont le placement a été explicitement verrouillé par le planificateur.
    *   `SUSPENDED` : Cours temporairement suspendu ou mis de côté.
*   *Relations (1-à-N)* : `sessions` (Liste des **Séances** rattachées à ce cours)

### 1bis. Session (Séance)
L'unité opérationnelle et planifiée d'un cours.
*   `id` : Clé primaire (Entier)
*   `course_id` : Clé étrangère vers le **Course** parent (Entier, relation 1-à-N)
*   `timeslot_id` : Clé étrangère optionnelle vers un **Timeslot** (0 ou 1 créneau). Dans le cas d'une séance planifiée sur la grille, `timeslot_id` désigne le créneau de départ (Start Timeslot), et la séance s'étend de manière contiguë sur une longueur égale à la `duration_minutes` du cours parent.
*   `classroom_id` : Clé étrangère optionnelle vers la **Salle** principale de la séance (Entier, relation N-à-1)
*   `week_type` : Type d'alternance de semaine (Chaîne, 'A', 'B' ou 'T' pour Toutes les semaines, par défaut 'T')
*   `is_pinned` : Indicateur si la séance est verrouillée statiquement sur ce créneau et cette salle, ignorée par le solveur (Booléen, par défaut `False`)
*   `is_co_teaching` : Indicateur si la séance est dispensée en co-enseignement (Booléen, par défaut `False`)
*   *Relations (N-à-N)* : `subjects`, `teachers`, `divisions`, `class_parts`, `groups`, `alternations`, `sites`, `materials`, `classrooms` (les ressources affectées à cette séance)

### 2. Subject (Matière)
*   `id` : Clé primaire (Entier)
*   `code` : Code abrégé interne ou de gestion pour l'affichage (Chaîne, e.g. "MATHS", "SVT", "ACCPE")
*   `code_nomenclature` : Code national réglementaire de la nomenclature issu de la base nationale (Chaîne, e.g. `006600` pour l'accompagnement personnalisé)
*   `short_label` : Libellé court abrégé utilisé pour l'affichage compact dans les grilles horaires (Chaîne, e.g. `ACCOMPAGNEMT. PERSO.`)
*   `long_label` : Libellé long national officiel de la matière (Chaîne, e.g. `ACCOMPAGNEMENT PERSONNALISE`)
*   `edition_label` : Libellé d'édition personnalisé pour l'impression des bulletins et documents (Chaîne, e.g. `Accompagnement personnalisé`)
*   `is_etp` : Indicateur si la matière est comptabilisée dans les Equivalents Temps Plein (ETP) pour les dotations et le TRMD (Booléen, par défaut `False`)
*   `is_specialty` : Indicateur si la matière est une spécialité (ou option) (Booléen, par défaut `False`). Cet attribut permet de filtrer l'interface utilisateur pour n'afficher que les matières de spécialité lors de la constitution des barrettes complexes d'alignement.
*   `color` : Code couleur d'affichage (Chaîne hexadécimale ou HSL pour la grille)
*   `pedagogic_weight` : Facteur de poids pédagogique (Réel, e.g. 1.5 pour matières dites « lourdes » nécessitant d'être réparties de manière équilibrée dans la semaine)
*   `discipline_id` : Clé étrangère vers la **Discipline** d'enseignement pour l'export national STSWEB (Entier, relation N-à-1)
*   `family_id` : Clé étrangère optionnelle vers une **Family** de type `Subject` (Entier, ex: pour regrouper les matières scientifiques)

### 2bis. Discipline
La nomenclature nationale des enseignements (discipline d'enseignement / de poste) indispensable pour l'export STSWEB et l'affectation budgétaire des professeurs.
*   `id` : Clé primaire (Entier)
*   `code` : Code national ou unique (Chaîne, e.g. "L0100" pour Philosophie, "L1400" pour Technologie)
*   `name` : Nom complet de la discipline (Chaîne, e.g. "Philosophie", "Technologie")

### 2ter. TRMDBudget (Budget de Répartition des Moyens par Discipline)
Représente la dotation budgétaire d'heures et de postes (issue de la Dotation Globale Horaire / DGH) allouée par le chef d'établissement à une discipline donnée. Cette entité constitue le socle du **TRMD** (Tableau de Répartition des Moyens par Discipline). 

Le système compare en temps réel :
1. **Les Besoins Prévisionnels (Requis)** : Volume total d'heures nécessaires pour assurer tous les enseignements. Il est calculé en faisant la somme pour chaque classe (`Division`) du volume horaire hebdomadaire défini par le `MEFService` de la matière de cette discipline (ex: `weekly_hours * nombre_de_classes`).
2. **Les Moyens Réels (Disponibles / Apports)** : Somme des heures de service hebdomadaires que les enseignants titulaires (`Teacher`) affectés à cette discipline doivent contractuellement assurer dans l'établissement (`max_weekly_hours`).
3. **La Balance Budgétaire (Écart)** : Différence dynamique calculée $\text{Moyens Réels} - \text{Besoins Prévisionnels}$. Une balance négative indique un sous-effectif nécessitant le recrutement de contractuels ou l'attribution d'heures supplémentaires, tandis qu'une balance positive indique un sur-effectif d'heures dans la discipline.

*   `id` : Clé primaire (Entier)
*   `discipline_id` : Clé étrangère vers la **Discipline** concernée (Entier, relation unique 1-à-1)
*   `allocated_hp` : Volume d'Heures Postes (HP) budgétées pour la discipline (Réel, ex: `180.0` heures régulières)
*   `allocated_hsa` : Volume d'Heures Supplémentaires Annuelles (HSA) budgétées pour la discipline (Réel, ex: `18.0` heures supplémentaires)
*   `allocated_posts` : Nombre de postes d'enseignants titulaires (Equivalent Temps Plein / ETP) alloués à la discipline (Réel, ex: `10.0`)

### 2quater. Family (Famille / Catégorie)
Regroupement transversal et hiérarchique de ressources permettant de mutualiser des contraintes ou de filtrer l'affichage (ex: familles de matières "Sciences", familles de cours "Spécialités Terminale", familles de professeurs "Sciences Humaines").
*   `id` : Clé primaire (Entier)
*   `code` : Code unique de la famille (Chaîne, e.g. "SCIENCES")
*   `name` : Libellé de la famille (Chaîne, e.g. "Sciences Expérimentales")
*   `resource_type` : Type de ressource concernée par ce regroupement (Enum : `Subject`, `Course`, `Teacher`, `Classroom`)

### 3. Teacher (Professeur)
Un professeur est défini globalement au niveau de la cité scolaire (permettant le partage de service entre collège et lycée), mais possède un établissement principal de rattachement administratif.
*   `id` : Clé primaire (Entier)
*   `code` : Trigronyme ou identifiant unique (Chaîne, e.g. "DUPONT.J")
*   `last_name` : Nom de famille (Chaîne)
*   `first_name` : Prénom (Chaîne)
*   `color` : Code couleur d'affichage (Chaîne)
*   `max_weekly_hours` : Nombre maximum d'heures d'enseignement autorisées par semaine (Réel)
*   `primary_school_id` : Clé étrangère optionnelle vers sa **School** de rattachement administratif principal (Entier, relation N-à-1)

### 4. MEF (Module Élémentaire de Formation / Niveau de formation)
Représente une formation ou un niveau d'enseignement réglementaire national défini par le ministère (ex: "Troisième Générale", "Seconde Générale et Technologique", "Première Spécialité"). C'est le socle technique indispensable pour l'import de la structure depuis STSWEB et pour calculer les dotations horaires globales.

Le MEF est un concept structurant pour :
1. **L'intégration nationale** : Il porte le code national obligatoire à 11 chiffres requis pour l'exportation réglementaire de rentrée vers STSWEB/SIECLE.
2. **Le calcul automatique des besoins** : En modifiant les services d'un MEF, le planificateur met à jour instantanément les besoins de l'ensemble des classes associées, évitant de ressaisir les matières et volumes horaires classe par classe.
3. **La gestion des structures composites** : Il permet de distinguer les élèves de formations différentes réunis au sein d'une même classe physique (ex: double-niveau ou classe de 3ème réunissant des élèves de MEF Général et MEF SEGPA).

*   `id` : Clé primaire (Entier)
*   `school_id` : Clé étrangère vers la **School** concernée (Entier, relation N-à-1)
*   `code` : Code national unique standardisé sur 11 caractères (Chaîne, e.g. "20310010110" pour une 3ème Générale)
*   `name` : Libellé complet de la formation (Chaîne, e.g. "Troisième Générale")
*   `forecast_student_count` : Nombre prévisionnel d'élèves affectés à cette formation dans l'établissement (Entier)
*   `max_students_per_class` : Limite conseillée ou réglementaire d'élèves par division (Entier, ex: `30` pour le collège, `35` pour le lycée)
*   *Relations (1-à-N)* : `mef_services` (Liste des dotations d'heures réglementaires par matière pour ce niveau)

### 4bis. MEFService (Service standard de formation)
Modèle de service d'enseignement lié à un MEF. Il sert de « gabarit » ou de patron pour générer automatiquement les cours requis d'une classe (Division) de ce niveau, évitant la saisie manuelle répétitive pour chaque classe. Lors de l'association d'une classe (`Division`) à un `MEF`, celle-ci hérite automatiquement de l'ensemble des `MEFServices` sous forme de cours prévisionnels.
*   `id` : Clé primaire (Entier)
*   `mef_id` : Clé étrangère vers le **MEF** parent (Entier, relation 1-à-N)
*   `subject_id` : Clé étrangère vers la **Subject** (Matière) enseignée (Entier, relation N-à-1)
*   `weekly_hours` : Volume horaire hebdomadaire réglementaire dû aux élèves (Réel, ex: `3.5` pour 3h30 de Mathématiques en 3ème)
*   `is_divided` : Si vrai, indique que tout ou partie de cet enseignement se déroule en effectif réduit (cours en groupe) (Booléen, par défaut `False`)

### 4ter. Division (Classe)
*   `id` : Clé primaire (Entier)
*   `school_id` : Clé étrangère vers la **School** à laquelle la classe appartient (Entier, relation N-à-1)
*   `code` : Code unique de la classe (Chaîne, e.g. "3EME_A")
*   `name` : Libellé de la classe (Chaîne, e.g. "Troisième A")
*   `student_count` : Nombre total d'élèves de la classe (Entier)
*   `color` : Code couleur d'affichage (Chaîne)
*   `mef_id` : Clé étrangère optionnelle vers le **MEF** principal de la classe (Entier, relation N-à-1). Si la classe est composite (multi-MEF ou double-niveau), elle est liée à son MEF de référence majoritaire.

### 5. ClassPart (Partie de classe)
Une composante élémentaire issue d'une partition de classe (ex : Demi-classe 1, Esp1, Latin).
*   `id` : Clé primaire (Entier)
*   `code` : Code unique (Chaîne, e.g. "3A_G1")
*   `name` : Libellé (Chaîne, e.g. "Groupe 1 (Demi-classe)")
*   `partition_id` : Clé étrangère vers la **Partition** parente (Entier, relation 1-à-N)
*   `student_count` : Nombre d'élèves de cette partie (Entier)

### 5bis. Partition (Partition de classe)
Découpage logique disjoint des élèves d'une Division (ex : la partition "Langues" contient les parties Esp1, Esp2, All ; la partition "Demi-classe" contient G1, G2).
*   `id` : Clé primaire (Entier)
*   `code` : Code unique de la partition (Chaîne, e.g. "LV2", "AP", "OPTIONS")
*   `name` : Libellé de la partition (Chaîne, e.g. "Langue Vivante 2", "Accompagnement Personnalisé")
*   `division_id` : Clé étrangère vers la classe parente **Division** (Entier, relation 1-à-N)

### 6. Group (Groupe)
Regroupement d'élèves (éventuellement à effectif variable) constitué par l'assemblage d'une ou plusieurs **ClassParts** (parties de classe) issues d'une ou plusieurs Divisions (ex : le groupe "Allemand LV2" associe la partie "All" de la 3ème A et la partie "All" de la 3ème B).
*   `id` : Clé primaire (Entier)
*   `code` : Code unique du groupe (Chaîne, e.g. "GERMAN_LV2")
*   `name` : Libellé (Chaîne, e.g. "Allemand LV2")
*   `student_count` : Nombre total d'élèves participant au groupe (Entier)
*   `is_variable_size` : Indicateur si le groupe est à effectif variable en cours d'année (Booléen, par défaut `False`)
*   *Relations (N-à-N)* : `class_parts` (Les parties de classe composant ce groupe)

### 6bis. ClassPartLink (Lien entre parties de classe)
Lien d'incompatibilité logique. L'existence d'un lien entre deux parties de classe indique qu'elles ont (ou peuvent avoir) des élèves en commun. Par conséquent, le solveur de conflits s'assure que deux séances affectées à ces deux parties respectives ne peuvent pas être planifiées en même temps.
*   `id` : Clé primaire (Entier)
*   `class_part_a_id` : Clé étrangère vers la première **ClassPart** (Entier)
*   `class_part_b_id` : Clé étrangère vers la seconde **ClassPart** (Entier)
*   `is_system_generated` : Vrai si le lien a été généré automatiquement par précaution par le système lors de la création de partitions croisées (Booléen, par défaut `True`)


### 7. Alternation (Alternance)
*   `id` : Clé primaire (Entier)
*   `code` : Code unique (Chaîne, e.g. "WEEK_A", "WEEK_B")
*   `name` : Libellé complet (Chaîne, e.g. "Semaine A", "Semaine B", "Hebdomadaire")
*   `color` : Code couleur d'affichage (Chaîne)

### 8. Site
*   `id` : Clé primaire (Entier)
*   `code` : Code unique (Chaîne, e.g. "CAMPUS_A")
*   `name` : Nom du site géographique (Chaîne, e.g. "Campus Nord")

### 8b. SiteTravelTime (Temps de trajet inter-sites)
Matrice relationnelle des temps de trajet définissant la durée nécessaire pour se déplacer d'un site à un autre. Le solveur utilise ces durées pour bloquer tout enchaînement direct de cours sans ce délai de battement.
*   `id` : Clé primaire (Entier)
*   `from_site_id` : Clé étrangère vers le **Site** de départ (Entier)
*   `to_site_id` : Clé étrangère vers le **Site** d'arrivée (Entier)
*   `duration_minutes` : Durée de déplacement en minutes (Entier, ex: `30` pour `0h30`)

### 9. Material (Matériel / Équipement)
*   `id` : Clé primaire (Entier)
*   `code` : Code abrégé unique (Chaîne, e.g. "KIT_IPAD")
*   `name` : Nom de l'équipement (Chaîne, e.g. "Chariot de Tablettes Tactiles")
*   `quantity` : Nombre total d'unités disponibles en stock (Entier)

### 10. Classroom (Salle)
Représente soit une salle simple (ordinaire), soit un **Groupe de salles** interchangeables (ex: "Laboratoires sciences") permettant une réservation générique lors de la saisie des cours (avec affectation finale automatique).
*   `id` : Clé primaire (Entier)
*   `code` : Code unique de la salle ou du groupe (Chaîne, e.g. "S102", "GR_LABOS")
*   `name` : Libellé de la salle ou du groupe (Chaîne, e.g. "Salle 102 - Physique", "Laboratoires sciences")
*   `capacity` : Capacité maximale d'accueil d'élèves (Entier, optionnel pour les groupes)
*   `site_id` : Clé étrangère vers le **Site** géographique (Entier, relation 1-à-N)
*   `quantity` : Nombre de salles physiques représentées (Entier, par défaut `1`).
    *   Si `quantity == 1` : C'est une **salle simple**.
    *   Si `quantity > 1` : L'entité est un **Groupe de salles**.
*   *Relations (N-à-N ordonnée)* : `contained_classrooms` (Pour les groupes de salles (`quantity > 1`), liste ordonnée des salles simples de même capacité et situées obligatoirement sur le **même site** composant ce groupe. L'ordre d'affectation au sein du groupe est défini de manière séquentielle pour prioriser l'utilisation de certaines salles simples par rapport à d'autres).

### 11. ResourcePreference (Vœux / Préférence)
Association polymorphique entre n'importe quel type de ressource, un créneau (Timeslot), un niveau de préférence (Disponible, Vœu, Indisponible), rattachée obligatoirement à **1 à N périodes** (Semaine A/B, Trimestre, Période spécifique).
*   `id` : Clé primaire (Entier)
*   `resource_type` : Type de ressource concernée (Chaîne : `Teacher`, `Classroom`, `Division`, `Group`, `Material`, `ClassPart`, `Site`, `Subject`)
*   `resource_id` : Identifiant de la ressource concernée (Entier)
*   `timeslot_id` : Clé étrangère vers le créneau **Timeslot** (Entier)
*   `level` : Niveau de vœu (Enum : `RED` (Indisponibilité impérative / Rouge), `ORANGE` (Indisponibilité optionnelle / Orange), `GREEN` (Souhait de présence / Vert), `WHITE` (Disponible / Blanc))
*   *Relations (N-à-N, min 1)* : `periods` (Liaison obligatoire vers **1 à N périodes** d'application de ce vœu ou indisponibilité)

### 12. Mission
Mission d'enseignement ou d'accompagnement rattachée à un cours (ex : Professeur Principal).
*   `id` : Clé primaire (Entier)
*   `code` : Code unique (Chaîne, e.g. "PP", "COORD_MAT", "TUTO")
*   `name` : Libellé de la mission (Chaîne, e.g. "Professeur Principal", "Coordonnateur de Matière")
*   `hours_allowance` : Décharge horaire ou volume d'heures forfaitaire attribué (Réel)

### 13. ElectionMethod (Modalité d'élection)
Modalité pédagogique et administrative indispensable pour la reconnaissance des services de DNL et l'export STSWEB / LSL / Parcoursup.
*   `id` : Clé primaire (Entier)
*   `code` : Code unique de la modalité (Chaîne, e.g. "CG", "DNL", "AP")
*   `name` : Libellé complet (Chaîne, e.g. "Cours Général", "Discipline Non Linguistique", "Accompagnement Personnalisé")
*   `export_code` : Code technique d'exportation vers STSWEB (Chaîne)

### 14. Period (Période)
Découpage temporel de l'année d'enseignement (ex: Semestres, Trimestres, Périodes de stage).
*   `id` : Clé primaire (Entier)
*   `code` : Code abrégé unique (Chaîne, e.g. "T1", "T2", "T3", "S1", "S2")
*   `name` : Libellé de la période (Chaîne, e.g. "Trimestre 1", "Semestre 1")
*   `start_date` : Date de début de la période (Date)
*   `end_date` : Date de fin de la période (Date)

### 15. ResourceConstraint (Contrainte de Ressource)
L'objet générique portant les contraintes spécifiques à une ressource, définies de manière globale pour toute l'année d'enseignement (sans liaison temporelle avec les périodes).
*   `id` : Clé primaire (Entier)
*   `resource_type` : Type de ressource concernée (Chaîne : `Subject`, `Teacher`, `Division`, `Classroom`, `Site`)
*   `resource_id` : Identifiant de la ressource concernée (Entier)


#### Attributs spécifiques dynamiques selon le type de ressource :

##### A. Contraintes sur les Matières (`resource_type == 'Subject'`)
Sert à définir l'espacement, la succession, la charge horaire maximale et l'ordre hebdomadaire des matières dans l'emploi du temps des élèves. Chaque ligne de contrainte s'applique à un couple de matières (Matière A et Matière B, ou Matière A vers elle-même si `target_subject_b_id` est nul) pour une classe donnée :

*   `target_subject_b_id` : Clé étrangère optionnelle vers un second **Subject** (Entier). Si nul, la contrainte s'applique de la matière A vers elle-même (ex: deux cours de Français).
*   **Incompatibilités** (Espacement temporel requis entre les cours de A et B) :
    *   `incompatible_same_half_day` : Si vrai, interdit d'avoir des cours de A et B sur la même demi-journée (Booléen, par défaut `False`)
    *   `incompatible_same_day` : Si vrai, interdit d'avoir des cours de A et B le même jour (Booléen, par défaut `True` pour une matière vers elle-même)
    *   `incompatible_two_consecutive_days` : Si vrai, interdit d'avoir des cours de A et B sur deux jours consécutifs (Booléen, par défaut `False`)
    *   `min_free_half_days_between` : Nombre minimum de demi-journées libres d'espacement forcé entre un cours de A et de B (Entier, optionnel, ex: `2`)
*   **Succession Interdite** (Interdiction d'enchaînement immédiat sans pause ou sans autre cours intermédiaire) :
    *   `prevent_consecutive_a_then_b` : Si vrai, interdit qu'un cours de B succède immédiatement à un cours de A (Booléen, par défaut `False`)
    *   `prevent_consecutive_b_then_a` : Si vrai, interdit qu'un cours de A succède immédiatement à un cours de B (Booléen, par défaut `False`)
*   **Max Horaire** (Limitation de la charge d'heures de la matière A pour la classe) :
    *   `max_hours_per_day` : Limite horaire maximale autorisée de cette matière par jour pour la classe (Réel, optionnel, ex: `2h00`)
    *   `max_hours_per_half_day` : Limite horaire maximale autorisée par demi-journée (Réel, optionnel)
*   **Ordre Hebdomadaire** (Contraintes de préséance chronologique sur la semaine) :
    *   `weekly_order_a_before_b` : Si vrai, impose que le cours de la matière A ait lieu chronologiquement avant celui de la matière B dans la semaine (Booléen, par défaut `False`)
    *   `weekly_order_b_before_a` : Si vrai, impose que le cours de la matière B ait lieu chronologiquement avant celui de la matière A dans la semaine (Booléen, par défaut `False`)
*   **Cours en Groupe vs Classe Entière** (Gestion des séances dédoublées par rapport aux cours complets) :
    *   `group_course_order` : Force un ordre spécifique pour les séances en groupe par rapport aux séances en classe entière de cette matière (Enum : `NONE` (Aucun), `GROUP_BEFORE` (Groupe avant dans la semaine), `GROUP_AFTER` (Groupe après dans la semaine), `GROUP_BEFORE_OR_AFTER` (Groupe avant ou après dans la semaine, interdit d'avoir les deux le même jour), `GROUP_BEFORE_OR_AFTER_FORTNIGHT` (Groupe avant ou après sur deux semaines))

##### B. Contraintes sur les Enseignants (`resource_type == 'Teacher'`)
Garantit les conditions de service et l'aménagement du temps de travail des professeurs. Ces contraintes régissent la planification de leur temps de travail :

*   **Max Horaire** (Limitation de la charge de cours effective) :
    *   `max_hours_per_day` : Nombre maximum d'heures de cours par journée (Réel, optionnel)
    *   `max_hours_per_am` : Nombre maximum d'heures de cours par matinée (Réel, optionnel)
    *   `max_hours_per_pm` : Nombre maximum d'heures de cours par après-midi (Réel, optionnel)

*   **Maximum Présentiel / Amplitude** (Limitation de la durée globale de présence dans la journée, de la première à la dernière heure de cours) :
    *   `max_presence_days_per_week` : Nombre de jours concernés par semaine (Entier, ex: `2` jours)
    *   `max_presence_hours_per_day` : Amplitude horaire de présence maximale pour ces jours (Réel, ex: faire des journées d'au plus `6h00`)

*   **Horaires Aménagés** (Aménagements pour arrivées tardives ou départs précoces certains jours) :
    *   `late_start_days_per_week` : Nombre de jours par semaine concernés par l'arrivée tardive (Entier)
    *   `late_start_time` : Heure minimale de début de journée pour ces jours (Timeslot / Heure, ex: pas avant `09h00`)
    *   `early_end_days_per_week` : Nombre de jours par semaine concernés par le départ anticipé (Entier)
    *   `early_end_time` : Heure maximale de fin de journée pour ces jours (Timeslot / Heure, ex: pas après `17h00`)

*   **Plages Libres Garanties** (Garanties de repos et de jours libres) :
    *   `min_free_days_per_week` : Nombre minimal de journées libres garanties par semaine (Entier)
    *   `min_free_half_days_per_week` : Nombre de demi-journées libres garanties par semaine (Entier, ex: `2`)

*   **Maximum de Demi-journées de Travail** (Répartition des demi-journées de service) :
    *   `max_worked_am_per_week` : Nombre maximum de matinées travaillées par semaine (Entier)
    *   `max_worked_pm_per_week` : Nombre maximum d'après-midis travaillés par semaine (Entier)
    *   `only_one_half_day_per_day` : Si vrai, interdit de travailler plus d'une demi-journée par jour (Booléen, par défaut `False`)

*   **Préférences d'Optimisation** (Seuils tolérés lors du calcul automatique) :
    *   `max_gap_hours_per_week` : Nombre d'heures de trous tolérées par semaine (Heures de Trou Tolérées / H.T.T.) (Entier, par défaut `2`)

##### C. Contraintes sur les Classes (`resource_type == 'Division'`)
Délimite les conditions de travail des élèves d'une division (classe entière). Ces contraintes régissent le rythme scolaire hebdomadaire des élèves :

*   **Max Horaire** (Limitation de la charge d'enseignement quotidienne pour les élèves) :
    *   `max_hours_per_day` : Nombre maximum d'heures de cours par journée (Réel, optionnel)
    *   `max_hours_per_am` : Nombre maximum d'heures de cours par matinée (Réel, optionnel)
    *   `max_hours_per_pm` : Nombre maximum d'heures de cours par après-midi (Réel, optionnel)

*   **Horaires Aménagés** (Limitation pour préserver le rythme biologique et de travail des élèves) :
    *   `late_start_days_per_week` : Nombre de jours par semaine concernés par l'arrivée tardive (Entier)
    *   `late_start_time` : Heure minimale de début de journée pour ces jours (Timeslot / Heure, ex: pas avant `09h00`)
    *   `early_end_days_per_week` : Nombre de jours par semaine concernés par le départ anticipé (Entier)
    *   `early_end_time` : Heure maximale de fin de journée pour ces jours (Timeslot / Heure, ex: pas après `16h30`)

*   **Maximum de Demi-journées de Travail** (Répartition des demi-journées travaillées par la classe) :
    *   `max_worked_am_per_week` : Nombre maximum de matinées travaillées par semaine (Entier)
    *   `max_worked_pm_per_week` : Nombre maximum d'après-midis travaillés par semaine (Entier)
    *   `only_one_half_day_per_day` : Si vrai, interdit d'avoir des cours sur plus d'une demi-journée le même jour (Booléen, par défaut `False`)

*   **Préférences d'Optimisation** (Trous / Permanence des élèves) :
    *   `max_gap_hours_per_week` : Nombre d'heures de trous tolérées par semaine pour la classe (Entier, par défaut `2`)

##### D. Contraintes de Trajet et Site (`resource_type == 'Site'`)
Gère les contraintes logistiques liées aux déplacements des professeurs ou élèves sur les différents campus :
*   `max_travel_trips_per_day` : Nombre maximum de déplacements / trajets inter-sites autorisés par jour pour une même ressource (enseignant ou division/élèves) (Entier, optionnel). Si le nombre de déplacements réels dépasse ce seuil lors de la planification d'un jour donné, une alerte est levée ou le placement automatique échoue.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Le temps nécessaire à un développeur pour ajouter un nouvel écran de saisie basique (ex: matières) est réduit de 70% grâce au socle CRUD générique.
- **SC-002**: L'utilisateur peut visualiser et analyser d'un coup d'œil les caractéristiques consolidées de 5 cours sélectionnés en moins de 1 seconde via la Fiche T.
- **SC-003**: Le solveur respecte à 100% les indisponibilités strictes (créneaux rouges) saisies sur la grille pour l'ensemble des ressources (enseignants, salles, classes, équipements).
- **SC-004**: Les souhaits d'absence (oranges, évités) et de présence (verts, favorisés) sont respectés à plus de 90% sur l'ensemble des ressources lors de la résolution automatique.

## Assumptions
 
- L'interface s'intègre harmonieusement avec le design existant en utilisant TailwindCSS et Vue 3.
- Les données de vœux et d'alternance sont persistées dans la base SQLite existante via des migrations adaptées.
- Le solveur de base reste performant (recherche d'une solution stable et valide en < 10s) sous le volume cible de la structure pilote (jusqu'à 500 élèves, 40 enseignants, 30 salles, 20 classes / divisions).
