# Guide de Démarrage Rapide (Quickstart V2) : Emploi du Temps Annuel

Ce guide explique comment mettre en place l'environnement, appliquer la migration de la base de données SQLite de la V1 vers la V2, et valider l'ensemble via la suite de tests automatisée.

---

## 1. Préparation de l'Environnement Local

Nous réutilisons l'environnement virtuel et la configuration existants.

### 1.1. Activation du Backend (FastAPI)
```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
```

### 1.2. Configuration de l'IHM Frontend (Vue 3)
```bash
cd ../frontend
npm install
```

---

## 2. Exécution de la Migration SQLite

Pour faire évoluer la base de données existante `timetable.db` vers le schéma V2 contenant les tables `schools`, `subjects`, `mefs` et la scission de `Course` en `Course` + `Session` :

```bash
cd ../backend
python -m app.core.database --apply-migrations
```

### 2.1. Alimentation avec le Jeu d'Essai V2
Pour vider la base locale et y injecter le jeu d'essai complet de validation multi-établissement (comprenant deux établissements actifs de la Cité Scolaire, 40 enseignants avec grilles de vœux pré-remplies, divisions, MEF, budgets TRMD et cours de spécialité) :
```bash
python -m app.core.database --init-db --seed-v2
```

---

## 3. Lancement des Serveurs de Développement

### 3.1. Démarrer le API Backend
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```
L'API OpenAPI interactive se trouve sur `http://localhost:8000/docs`.

### 3.2. Démarrer le Serveur IHM Frontend
```bash
cd frontend
npm run dev
```
L'IHM est accessible sur `http://localhost:5173`. Le proxy configuré redirige automatiquement les appels `/api/*` vers le port backend `8000`.

---

## 4. Validation par les Tests (TDD)

Toutes les nouvelles contraintes (quinzaine A/B, exclusions de groupes) et la logique multi-établissement sont validées via Pytest.

### 4.1. Exécuter l'ensemble de la suite de tests
```bash
cd backend
pytest -v
```

### 4.2. Lancer les tests spécifiques du solveur V2
```bash
pytest tests/test_solver.py -v
```
Ces tests valident que le solveur Timefold :
1. Résout correctement l'emploi du temps sans générer de conflit sur les professeurs ou salles partagées.
2. Respecte les semaines alternées A/B et positionne les cours en quinzaine de manière optimale.
3. Alerte l'utilisateur en cas de chevauchement sur les grilles de vœux rouges.
