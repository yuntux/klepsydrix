# Klepsydrix - Backend API

Ce dossier contient l'API REST de Klepsydrix, un moteur d'optimisation d'emplois du temps scolaire basé sur FastAPI et Timefold Solver (version hybride).

## Fonctionnalités

- **Persistance SQLite** : Stockage des cours, enseignants, classes et salles avec SQLAlchemy.
- **Solveur Hybride** : Résolution automatique ultra-rapide des emplois du temps (Timefold Solver combiné à une heuristique gloutonne déterministe).
- **Gestion des Conflits** : Validation immédiate des conflits d'enseignants, de salles et de classes lors de l'édition manuelle (erreur 409).
- **Données d'essai V1** : Script d'initialisation complet pour la simulation.

## Démarrage rapide

1. Activer l'environnement virtuel :
   ```bash
   source backend/.venv/bin/activate
   ```
2. Lancer le serveur de développement :
   ```bash
   PYTHONPATH=. uvicorn backend.app.main:app --reload --port 8000
   ```

## API Endpoints

- `GET /api/timetable` : Récupérer l'état actuel du planning complet (cours placés et non placés).
- `POST /api/timetable/solve` : Lancer la résolution automatique hybride.
- `POST /api/timetable/reset` : Réinitialiser tous les cours de la grille.
- `PUT /api/timetable/courses/{course_id}` : Déplacer un cours (avec détection de conflits).
