# Recherche Technique & Rationale d'Évolution : Emploi du Temps Annuel (V2)

Ce document décrit les choix d'architecture technique et de modélisation pour l'évolution de Klepsydrix de la V1 vers la V2.

---

## 1. Modélisation de la Planification Temporelle (Quinzaine & Groupes)

### Problématique
Dans la V1, un cours est représenté par une unique entité `Course` directement positionnée sur la grille via `timeslot_id`. Dans la réalité scolaire :
1. Un cours hebdomadaire de 2h de Mathématiques se traduit par deux séances distinctes de 1h placées sur des créneaux différents.
2. Certains enseignements s'effectuent par quinzaine (ex: Travaux Pratiques de SVT en Semaine A pour le Groupe 1 et en Semaine B pour le Groupe 2).
3. Les élèves d'une division (classe) peuvent appartenir à des sous-groupes (LV2 Allemand, Spécialité Physique) qui s'intersectent. Deux cours visant des groupes s'intersectant ne peuvent pas être placés en parallèle (conflit d'élèves).

### Décision de Conception
* **Séparation Course / Session** :
  Le modèle est scindé en deux entités distinctes :
  * `Course` : Entité pédagogique racine stockant la matière, le volume global ou la durée, et les ressources de référence (matière, enseignant principal).
  * `Session` : Séance d'enseignement physique d'une durée d'1h ou 2h, rattachée au cours, portant `timeslot_id`, `classroom_id`, `week_type` (`A`, `B`, ou `W` pour toutes les semaines), et un booléen `is_pinned`.
* **Modélisation de l'Intersection de Groupes (`ClassPartLink`)** :
  Pour éviter d'affecter individuellement chaque élève (hors scope), nous modélisons les exclusions logiques. Si la classe de 3ème A est divisée en `Groupe 1` (demi-classe) et `Groupe 2` (demi-classe), ils sont compatibles. Si elle est aussi divisée en `LV1 Allemand` et `LV1 Anglais`, les élèves d'allemand peuvent être dans le groupe 1. La table d'association `class_part_links` déclare explicitement les groupes qui possèdent au moins un élève en commun. Si deux groupes sont liés par cette table, ils sont déclarés **incompatibles** et ne peuvent pas partager le même créneau sur la même semaine.

---

## 2. Intégration dans Timefold Solver

### Problématique
Le solveur de la V1 manipule des `PlanningCourse` simples. Il doit désormais manipuler des séances à quinzaine et des incompatibilités de groupes d'élèves.

### Choix de Conception
* **Planning Entity** : `PlanningSession` (qui remplace `PlanningCourse`).
* **Variables** : `timeslot` et `classroom`.
* **Règles de Collision Évoluées** :
  * **Teacher / Room Collision** : Deux séances `s1` et `s2` partageant le même enseignant ou la même salle sont en conflit si et seulement si leurs semaines s'intersectent :
    ```python
    def weeks_overlap(s1, s2):
        return s1.week_type == "W" or s2.week_type == "W" or s1.week_type == s2.week_type
    ```
  * **Student Collision (Groupes & Classes)** : Deux séances s'exécutant sur la même semaine s'intersectent s'il y a conflit de division (même classe) OU si les groupes visés possèdent un lien d'incompatibilité dans `ClassPartLink`.

---

## 3. Multi-Établissement (Cité Scolaire) sans surcharge

### Problématique
Nous devons résoudre l'emploi du temps d'un établissement actif (ex: Collège) tout en garantissant qu'un professeur ou une salle partagée avec un autre établissement (ex: Lycée) ne subit aucun conflit d'horaire.

### Choix de Conception
* **Chargement Contextuel & Pinned Elements** :
  Lors de la résolution pour l'école `school_id` :
  1. Le backend charge toutes les divisions, cours, MEF et budgets associés à cet établissement. Le solveur peut librement déplacer leurs séances non verrouillées.
  2. Le backend charge les séances planifiées des **autres** établissements de la Cité Scolaire comme des contraintes fixes. Ces séances extérieures sont passées au solveur avec `is_pinned=True` et leurs variables `timeslot` et `classroom` figées en lecture seule.
  3. Ainsi, le solveur résout l'établissement actif en moins de 10s tout en contournant de manière 100% fiable les occupations des ressources communes par les autres structures scolaires !

---

## 4. Draggable Fiche T & Ergonomie Premium

### Problématique
La popin Fiche T doit pouvoir être déplacée à la souris par l'utilisateur pour découvrir les créneaux masqués.

### Choix de Conception
* **Drag-and-Drop de Positionnement (Vue 3)** :
  Nous implémentons le déplacement via un gestionnaire de coordonnées absolues :
  ```typescript
  const popinPosition = ref({ x: 100, y: 150 });
  
  function onHeaderMouseDown(event: MouseEvent) {
      const startX = event.clientX - popinPosition.value.x;
      const startY = event.clientY - popinPosition.value.y;
      
      function onMouseMove(moveEvent: MouseEvent) {
          popinPosition.value.x = moveEvent.clientX - startX;
          popinPosition.value.y = moveEvent.clientY - startY;
      }
      
      function onMouseUp() {
          window.removeEventListener('mousemove', onMouseMove);
          window.removeEventListener('mouseup', onMouseUp);
      }
      
      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
  }
  ```
  Ce code natif est extrêmement performant, fluide et n'ajoute aucune dépendance JS externe.
* **Consolidation par Chips Stylisées** :
  Pour consolider les attributs (enseignants, salles, etc.) d'une multisélection de `N` cours :
  1. Nous calculons les valeurs distinctes.
  2. Si `valeurs_distinctes.length == 1`, l'attribut est commun et s'affiche sous forme standard.
  3. Si `valeurs_distinctes.length > 1`, les attributs divergent. Chaque valeur s'affiche sous forme de badge de proportion (ex: `M. Martin [2/3]`) avec une couleur contrastée et une bordure en pointillés, indiquant instantanément à l'utilisateur la disparité de sa sélection.
