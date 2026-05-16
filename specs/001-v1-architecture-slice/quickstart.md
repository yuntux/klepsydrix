# Guide de Démarrage Rapide (Quickstart) : Klepsydrix V1

Ce guide détaille les étapes pour installer, isoler les dépendances et exécuter localement le frontend et le backend de Klepsydrix en mode développement.

---

## 1. Prérequis Système
Avant de commencer, assurez-vous d'avoir installés sur votre machine hôte :
- **Python 3.11 ou 3.12** : ⚠️ *Critique : N'utilisez surtout pas Python 3.13 ou supérieur. La librairie Timefold s'appuie sur le pont Python-Java `JPype1`, qui plante au démarrage de la JVM sur les versions récentes de Python (erreur `SIGSEGV`).*
- **Java JRE/JDK 17+** : Requis par Timefold pour exécuter le moteur sous le capot.
- **Node.js v18** ou supérieur (avec son gestionnaire de paquets `npm`).

---

## 2. Configuration & Lancement du Backend

Le backend est isolé dans un environnement virtuel local pour ne pas polluer l'OS hôte.

### Étape A : Création et activation de l'environnement virtuel
Ouvrez un terminal dans le sous-projet backend :
```bash
cd /home/ubuntu/klepsydrix/backend
python3 -m venv .venv
source .venv/bin/activate
```

### Étape B : Installation des dépendances
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Étape C : Configuration du fichier local `.env`
Créez un fichier `.env` à la racine de `backend/` à partir de l'exemple fourni :
```bash
cp .env.example .env
```
Le fichier `.env` contiendra les variables minimales pour SQLite :
```ini
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite:///./klepsydrix.db
```

### Étape D : Lancement du serveur FastAPI de développement
Démarrez le serveur avec rechargement automatique (Hot Reload) :
```bash
uvicorn app.main:app --reload --port 8000
```
Le serveur sera disponible sur [http://localhost:8000](http://localhost:8000). Vous pouvez explorer l'API interactive (Swagger UI) sur [http://localhost:8000/docs](http://localhost:8000/docs).

---

## 3. Configuration & Lancement du Frontend

Le frontend Vue 3 est isolé nativement via le répertoire local `node_modules`.

### Étape A : Installation des dépendances localement
Ouvrez un nouveau terminal dans le sous-projet frontend :
```bash
cd /home/ubuntu/klepsydrix/frontend
npm install
```

### Étape B : Lancement du serveur de développement Vite
Démarrez le serveur de développement local :
```bash
npm run dev
```
L'interface de planification sera disponible sur [http://localhost:5173](http://localhost:5173). 

*Note : La configuration Vite `vite.config.ts` inclut un proxy automatique qui redirige toutes les requêtes `/api/*` vers le serveur backend FastAPI local sur le port 8000.*

---

## 4. Lancement des Tests (TDD)

Pour valider l'intégrité de la logique et du solveur (sans tests par navigateur) :
```bash
cd /home/ubuntu/klepsydrix/backend
source .venv/bin/activate
pytest -v
```
