# Contrat d'Interface API : Klepsydrix V1

Ce document formalise les points de terminaison (endpoints) de l'API REST exposée par le backend FastAPI, avec le format exact des requêtes/réponses JSON.

---

## 1. Modèles de Données Communs (Schémas JSON)

### A. Représentation d'une Ressource
```json
{
  "id": 1,
  "name": "M. Martin"
}
```

### B. Représentation d'un Cours (Course)
```json
{
  "id": 1,
  "subject": "Mathematics",
  "teacher_id": 2,
  "division_id": 1,
  "classroom_id": null,
  "timeslot_id": null
}
```
*Note : `classroom_id` et `timeslot_id` peuvent être des entiers ou porter la valeur `null` (si non planifié).*

---

## 2. Endpoints de l'API

### GET `/api/timetable`
Récupère l'état complet du projet de planification.

- **Réponse HTTP 200 OK** :
```json
{
  "teachers": [
    { "id": 1, "name": "M. Martin" },
    { "id": 2, "name": "Mme. Bernard" }
  ],
  "classrooms": [
    { "id": 1, "name": "Salle 101", "capacity": 30 },
    { "id": 2, "name": "Salle 102", "capacity": 35 }
  ],
  "divisions": [
    { "id": 1, "name": "6ème A" },
    { "id": 2, "name": "5ème B" }
  ],
  "timeslots": [
    { "id": 1, "day_of_week": 1, "hour": 8 },
    { "id": 2, "day_of_week": 1, "hour": 9 }
  ],
  "courses": [
    {
      "id": 1,
      "subject": "Mathematics",
      "teacher_id": 1,
      "division_id": 1,
      "classroom_id": null,
      "timeslot_id": null
    },
    {
      "id": 2,
      "subject": "French",
      "teacher_id": 2,
      "division_id": 2,
      "classroom_id": 1,
      "timeslot_id": 2
    }
  ]
}
```

---

### POST `/api/timetable/solve`
Déclenche la résolution et l'optimisation automatique par le moteur Timefold en mémoire vive.

- **Corps de la requête** : *Aucun corps requis (le solveur prend les données courantes en base de données).*
- **Réponse HTTP 200 OK** (Si résolution réussie avec zéro conflit dur) :
  Retourne la liste des cours mis à jour avec leurs créneaux et salles attribués.
```json
{
  "status": "success",
  "message": "Résolution automatique complétée avec succès.",
  "courses": [
    { "id": 1, "subject": "Mathematics", "teacher_id": 1, "division_id": 1, "classroom_id": 2, "timeslot_id": 1 },
    { "id": 2, "subject": "French", "teacher_id": 2, "division_id": 2, "classroom_id": 1, "timeslot_id": 2 }
  ]
}
```

- **Réponse HTTP 422 Unprocessable Entity** (Si le jeu de contraintes est impossible à résoudre sans violer de contrainte dure) :
```json
{
  "status": "error",
  "code": "UNSOLVABLE_TIMETABLE",
  "message": "Résolution impossible : impossible de positionner tous les cours sans chevauchement d'enseignant ou de salle."
}
```

---

### PUT `/api/courses/{course_id}`
Met à jour manuellement la planification d'un cours spécifique (action de glisser-déposer de l'utilisateur).

- **Corps de la requête** :
```json
{
  "timeslot_id": 3,
  "classroom_id": 2
}
```
*Note : Pour remettre le cours dans la barre latérale des cours non placés, l'utilisateur soumet `null` pour ces deux champs.*

- **Réponse HTTP 200 OK** (Si le déplacement est valide) :
```json
{
  "id": 1,
  "subject": "Mathematics",
  "teacher_id": 1,
  "division_id": 1,
  "classroom_id": 2,
  "timeslot_id": 3
}
```

- **Réponse HTTP 409 Conflict** (Si le déplacement viole une contrainte dure d'exclusion mutuelle, ex: le professeur a déjà un cours sur ce créneau) :
```json
{
  "status": "error",
  "code": "RESOURCE_OVERLAP",
  "message": "Conflit détecté : l'enseignant M. Martin dispense déjà un cours sur le créneau demandé."
}
```

---

### POST `/api/timetable/reset`
Réinitialise tous les cours à leur état d'origine non placé (`timeslot_id = null`, `classroom_id = null`) pour relancer des démonstrations de résolution.

- **Réponse HTTP 200 OK** :
```json
{
  "status": "success",
  "message": "La grille horaire a été entièrement réinitialisée à son état initial."
}
```
