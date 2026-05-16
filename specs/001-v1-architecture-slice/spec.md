# Spécification Fonctionnelle : Tranche Verticale de la V1 (Klepsydrix)

**Branche de la fonctionnalité** : `001-v1-architecture-slice`

**Date de création** : 2026-05-16

**Statut** : Version de Travail (Draft)

**Description générale** :  
Ce lot définit le périmètre d'une V1 "Tranche Verticale" pour Klepsydrix. L'objectif est de poser une première version fonctionnelle complète d'un flux d'emploi du temps, de sa persistance à son optimisation automatique via un moteur de contraintes, jusqu'à sa visualisation dans une interface utilisateur interactive de qualité professionnelle.

---

## Clarifications

### Session 2026-05-16
- **Q** : Si le jeu de contraintes est trop serré ou impossible à résoudre, comment le moteur de calcul doit-il se comporter à l'expiration de son temps limite de calcul ?  
  **A** : **Option B (Strictement valide ou échec)** : Le solveur s'arrête à la limite de temps et renvoie une erreur claire "Résolution impossible" si au moins une contrainte dure (FR-007) est violée, sans modifier la grille.
- **Q** : Pour notre V1 "Tranche Verticale", quel est l'ordre de grandeur maximal du jeu de données que le système doit charger, afficher et résoudre ?  
  **A** : **Option A (Petit prototype)** : Jusqu'à 10 enseignants, 5 classes (divisions), 5 salles de classe, et 30 cours individuels à planifier.
- **Q** : Comment la gestion des utilisateurs et l'authentification (connexion/login) doivent-elles être traitées pour cette V1 "Tranche Verticale" ?  
  **A** : **Option A (Session unique anonyme - Sans authentification)** : L'application s'ouvre directement sur l'interface de planification sans aucun formulaire de connexion. Tout le monde a tous les droits d'accès locaux.

---

## Scénarios Utilisateurs & Validation

### Scénario Utilisateur 1 - Visualisation et Résolution Automatique de la Grille (Priorité : P1)

En tant que Responsable d'Établissement (Planificateur), je veux visualiser un emploi du temps hebdomadaire d'exemple sur une interface utilisateur et lancer un calcul d'optimisation automatique pour placer des cours non affectés en respectant des contraintes strictes.

**Valeur métier** : Valider que le moteur de calcul communique correctement avec l'application et met à jour l'interface utilisateur sans bloquer la navigation ni figer la grille.

**Test Indépendant** : 
1. Charger l'interface utilisateur (qui affiche une grille vide ou partiellement remplie).
2. Cliquer sur le bouton déclenchant la résolution automatique.
3. L'interface affiche un indicateur de chargement fluide, puis met à jour instantanément les positions des cours sur la grille avec un score de conformité.
4. Aucun cours n'est en conflit (pas de professeur ou de salle en doublon sur un même créneau).

**Scénarios d'Acceptation** :
1. **Étant donné** une base de données contenant 5 cours non placés, 3 enseignants et 2 salles,  
   **Quand** je lance la résolution automatique,  
   **Alors** le système calcule et place 100% des cours sur la grille sans aucun conflit d'enseignant ou de salle.
2. **Étant donné** un calcul d'optimisation en cours sur le serveur,  
   **Quand** le solveur calcule,  
   **Alors** l'interface utilisateur reste réactive et fluide, et affiche un indicateur visuel de recherche.

---

### Scénario Utilisateur 2 - Modification Manuelle simple de la Grille (Priorité : P2)

En tant que Planificateur, je veux déplacer un cours manuellement sur un créneau horaire vide directement depuis l'interface utilisateur et sauvegarder cette modification dans le système de persistance.

**Valeur métier** : Valider la cohérence des données après manipulation manuelle et s'assurer que le système applique les règles métiers de base.

**Test Indépendant** :
1. Sélectionner un cours placé sur la grille.
2. Le déplacer sur un créneau libre.
3. Le système valide la modification et la persiste.

**Scénarios d'Acceptation** :
1. **Étant donné** un cours placé sur un créneau A,  
   **Quand** je le déplace sur un créneau B (libre),  
   **Alors** l'interface utilisateur met à jour le placement et la modification est enregistrée de manière permanente.
2. **Étant donné** un déplacement manuel qui créerait un conflit (ex: enseignant indisponible ou déjà occupé sur ce créneau),  
   **Quand** le déplacement est tenté,  
   **Alors** l'interface affiche une notification d'erreur compréhensible et le cours retourne à sa place initiale.

---

## Exigences Fonctionnelles

### Exigences Générales et d'Architecture
- **FR-001** : Le système doit exposer une architecture découplée comprenant : une interface utilisateur interactive, une interface de programmation (API), un service d'application, et une base de données de persistance.
- **FR-002** : Le moteur de résolution automatique doit s'exécuter entièrement en mémoire vive pour optimiser les performances et garantir des temps de calcul minimaux pour le jeu de données de la V1.

### Base de Données et API
- **FR-003** : La base de données doit enregistrer les entités de base nécessaires à la gestion scolaire : Enseignants, Salles de classe, Divisions (classes d'élèves), Matières, Créneaux temporels et Cours.
- **FR-004** : L'API doit permettre de récupérer l'intégralité de la grille horaire et le statut des cours.
- **FR-005** : L'API doit permettre de déclencher à la demande la résolution automatique de l'emploi du temps par le moteur d'optimisation.
- **FR-006** : L'API doit permettre de mettre à jour le créneau temporel ou la salle assignée à un cours spécifique.

### Moteur de Résolution (Solveur)
- **FR-007** : Le solveur doit respecter impérativement deux règles strictes d'exclusion (Contraintes Dures) :
  - Un enseignant ne peut pas dispenser deux cours sur le même créneau.
  - Une salle ne peut pas accueillir deux cours sur le même créneau.
- **FR-008** : Le solveur doit appliquer une règle d'optimisation préférentielle (Contrainte Souple Enseignants) :
  - Minimiser le nombre de créneaux temporels vacants (les "trous" horaires) situés entre le premier et le dernier cours planifiés d'un même enseignant au cours d'une même journée.
- **FR-012** : Le solveur doit appliquer une règle d'optimisation préférentielle (Contrainte Souple Élèves) :
  - Minimiser le nombre de créneaux temporels vacants (les "trous" horaires) situés entre le premier et le dernier cours planifiés d'une même division (classe d'élèves) au cours d'une même journée.
- **FR-011** : Si le solveur ne parvient pas à trouver une solution respectant 100% des contraintes dures (FR-007) dans le temps imparti, la base de données ne doit pas être modifiée et l'API doit renvoyer une erreur claire "Résolution impossible" à l'interface utilisateur.



### Interface Utilisateur
- **FR-009** : La grille horaire interactive doit afficher un planning hebdomadaire structuré (du lundi au samedi) découpé en séquences horaires uniformes d'une heure.
- **FR-010** : Le design visuel doit présenter une esthétique sombre et soignée, avec un mode d'affichage moderne, une typographie lisible, et des animations fluides de transition d'état lors des actions de planification.

---

## Critères de Succès

- **SC-001** : L'affichage de la grille horaire reste fluide et réactif lors de la manipulation des cours.
- **SC-002** : Le temps total requis pour une phase d'optimisation automatique par le solveur est inférieur à 5 secondes sur le jeu de données V1.
- **SC-003** : 100% des cours placés automatiquement respectent scrupuleusement les contraintes d'exclusion mutuelle (zéro conflit enseignant/salle).
- **SC-004** : Un planificateur peut réaliser un cycle complet (visualiser ➡️ lancer la résolution automatique ➡️ déplacer un cours manuellement ➡️ enregistrer la modification) en moins de 15 secondes.

---

## Entités Clés

- **Teacher (Enseignant)** : Individu dispensant des cours, caractérisé par ses indisponibilités.
- **Classroom (Salle de classe)** : Espace physique caractérisé par sa capacité d'accueil.
- **Division (Classe d'élèves)** : Groupe homogène d'élèves (ex: 6ème A).
- **Course (Cours / Leçon)** : Association structurée entre un enseignant, une division d'élèves, une matière et une salle (optionnelle). C'est l'entité à planifier qui recevra un créneau temporel.
- **Timeslot (Créneau temporel)** : Séquence horaire fixe dans la semaine scolaire.

---

## Hypothèses

- **H-001** : Pour ce premier lot V1, le jeu de données d'exemple sera pré-alimenté directement dans la base de données, sans nécessiter d'interface d'importation dédiée (les fichiers d'imports types SIECLE/STSWEB feront l'objet de lots ultérieurs).
- **H-002** : Le calendrier scolaire est fixe pour toute la période (pas de gestion complexe de quinzaines ou d'alternances dans cette V1).
- **H-003** : Le jeu de données maximal cible pour la validation de cette V1 est borné à 10 enseignants, 5 divisions (classes d'élèves), 5 salles de classe et 30 cours individuels.

---

## Exclusion de Périmètre

Sont explicitement exclus du périmètre de cette V1 (Tranche Verticale) :
- La gestion des comptes utilisateurs, l'authentification (login, sessions) et la sécurité d'accès multi-utilisateurs (session unique anonyme et ouverte par défaut).
- L'importation de fichiers scolaires réels (fichiers XML SIECLE/STSWEB).
- La gestion de calendriers complexes (semaines alternées A/B, vacances scolaires variables).


