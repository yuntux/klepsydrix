# Contrats d'Interface API REST Évolués (V2)

Ce document décrit l'évolution des points d'accès API (FastAPI) pour intégrer le cloisonnement multi-établissement, la gestion des alternances (A/B), les exclusions de groupes et les vœux.

---

## 1. Récupération de l'Emploi du Temps (`GET /api/timetable`)

Le point d'accès est enrichi d'un filtre `school_id` permettant de charger l'environnement de l'école active sélectionnée dans l'IHM.

* **URL** : `GET /api/timetable?school_id={id}`
* **Exemple** : `GET /api/timetable?school_id=1`
* **Réponse (200 OK)** :
  ```json
  {
    "teachers": [
      { "id": 3, "name": "M. Martin", "color": "#4A90E2", "primary_school_id": 1 }
    ],
    "classrooms": [
      { "id": 5, "name": "Salle 101", "capacity": 30, "site_id": 1 }
    ],
    "divisions": [
      { "id": 1, "name": "3ème A", "school_id": 1, "mef_id": 2, "color": "#E3A857" }
    ],
    "timeslots": [
      { "id": 12, "day_of_week": 1, "hour": 8 }
    ],
    "courses": [
      {
        "id": 4,
        "subject_id": 1,
        "teacher_id": 3,
        "division_id": 1,
        "duration_minutes": 55,
        "label": "Mathématiques 3ème A",
        "memo": "Cours de soutien",
        "sessions": [
          {
            "id": 10,
            "timeslot_id": 12,
            "classroom_id": 5,
            "week_type": "W", // W = Toutes les semaines, A = Semaine A, B = Semaine B
            "is_pinned": false,
            "is_co_teaching": true,
            "co_teachers": [4] // IDs des enseignants associés en co-enseignement
          }
        ]
      }
    ]
  }
  ```

---

## 2. Déplacement Manuel et Mise à Jour d'une Séance (`PUT /api/timetable/sessions/{session_id}`)

En V1, l'API validait la collision sur un unique cours. En V2, la validation prend en compte les **semaines alternées A/B**, les **incompatibilités de groupes d'élèves** et le **co-enseignement**.

* **URL** : `PUT /api/timetable/sessions/{session_id}`
* **Corps de requête** :
  ```json
  {
    "timeslot_id": 14,
    "classroom_id": 5,
    "week_type": "A",
    "is_pinned": true,
    "co_teachers": [4]
  }
  ```
* **Réponses de validation métier** :
  * **200 OK** : Modification acceptée et enregistrée en base.
  * **409 Conflict - Teacher Conflict** : Renvoyé si l'enseignant principal ou l'un des co-enseignants est déjà occupé sur ce créneau sur la même semaine (ex: chevauchement d'une séance Semaine A avec une séance Semaine T).
  * **409 Conflict - Group Conflict** : Renvoyé si deux séances visent des groupes exclusifs déclarés incompatibles (`ClassPartLink`) sur le même créneau de la même semaine.

---

## 3. Enregistrement des Vœux et Préférences (`POST /api/timetable/preferences/{resource_type}/{resource_id}`)

Permet de sauvegarder en masse la grille tricolore de vœux d'une ressource (Enseignant ou Salle).

* **URL** : `POST /api/timetable/preferences/{resource_type}/{resource_id}`
* **Exemple** : `POST /api/timetable/preferences/Teacher/3`
* **Corps de requête** :
  ```json
  [
    { "timeslot_id": 12, "preference_level": "Unsuited" },   // Rouge
    { "timeslot_id": 13, "preference_level": "Undesirable" }, // Orange
    { "timeslot_id": 14, "preference_level": "Preferred" }    // Vert
  ]
  ```
* **Réponse (200 OK)** :
  ```json
  {
    "resource_type": "Teacher",
    "resource_id": 3,
    "saved_preferences_count": 3
  }
  ```

---

## 4. Synthèse Budgétaire TRMD (`GET /api/timetable/trmd/{school_id}`)

Fournit les statistiques de consommation d'heures réelles d'enseignement par rapport au budget (Heures Postes, Heures Supplémentaires, ETP).

* **URL** : `GET /api/timetable/trmd/1`
* **Réponse (200 OK)** :
  ```json
  {
    "school_id": 1,
    "budget_summary": [
      {
        "subject": { "id": 1, "short_label": "MATHS" },
        "allocated_etp": 1.22, // Calculé à partir des Heures Postes / 18
        "consumed_etp": 1.14,
        "diff_etp": -0.08,
        "status": "UNDER_BUDGET"
      }
    ]
  }
  ```

---

## 5. Gestion des Conflits de Structure (Simulation et Dépositionnement)

Permet de simuler et d'appliquer de profonds changements de structure (ex: modification de partitions de classe ou suppression de ressources) en évaluant l'impact sur les séances déjà planifiées sur la grille.

### A. Simuler la modification de structure (`POST /api/timetable/structures/simulate-change`)
Analyse l'impact de la modification et renvoie la liste des cours et séances qui devront être libérés et passer en statut `UNPLACED` pour conserver la cohérence de la base.

* **URL** : `POST /api/timetable/structures/simulate-change`
* **Corps de requête** :
  ```json
  {
    "action": "UPDATE_GROUP_PARTITION", // UPDATE_GROUP_PARTITION, DELETE_RESOURCE, etc.
    "resource_type": "Division",
    "resource_id": 1,
    "payload": {
      "new_mef_id": 3
    }
  }
  ```
* **Réponse (200 OK)** :
  ```json
  {
    "can_proceed": true,
    "impacted_sessions_count": 3,
    "impacted_sessions": [
      {
        "session_id": 10,
        "course_label": "Mathématiques - M. Martin - 3ème A",
        "timeslot": "Lundi 8h00",
        "reason": "Modification de la structure de division associée"
      }
    ]
  }
  ```

### B. Confirmer et Appliquer la modification (`POST /api/timetable/structures/apply-change`)
Applique la modification de structure, dépositionne automatiquement toutes les séances impactées en statut `UNPLACED` et enregistre le diagnostic de dépositionnement.

* **URL** : `POST /api/timetable/structures/apply-change`
* **Corps de requête** : (Même corps que la simulation)
* **Réponse (200 OK)** :
  ```json
  {
    "success": true,
    "deplaced_sessions_count": 3,
    "diagnostic_history_id": 15
  }
  ```
