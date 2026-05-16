# Recherche & Choix Technologiques : Klepsydrix V1

Ce document détaille les décisions d'architecture, les rationalités associées et les alternatives évaluées pour la tranche verticale V1.

---

## 1. Choix du Cadre de Persistance et Base de Données

### Décision :
Utiliser **SQLAlchemy ORM 2.0** associé à **Pydantic v2** sur une base de données **SQLite** locale en développement, avec compatibilité **PostgreSQL** en cible.

### Rationalité :
- **Transition SQLite ➡️ PostgreSQL transparente** : SQLAlchemy fait abstraction du moteur de base de données. Modifier l'environnement (`DATABASE_URL`) suffit à faire migrer l'application du fichier SQLite local vers un serveur PostgreSQL d'entreprise.
- **Typage fort et Validation native** : Pydantic permet de déclarer des schémas d'API stricts (`schemas.py`) et assure la validation automatique des types à l'entrée et à la sortie des routes API.
- **Sécurité et intégrité** : L'utilisation de sessions isolées SQLAlchemy (`SessionLocal`) avec fermeture automatique à chaque requête (`Depends(get_db)`) garantit la cohérence des transactions et empêche les fuites de connexions.

### Alternatives considérées :
- *SQL Direct (sqlite3 / psycopg2)* : Rejeté. Rendre l'application compatible avec deux dialectes SQL différents sans ORM demanderait une duplication importante de code de requêtage.
- *Tortoise ORM* : Rejeté. Bien qu'asynchrone, il est moins mature et dispose d'un écosystème de migration de base de données (comme Alembic pour SQLAlchemy) moins robuste.

---

## 2. Choix de la Stack Frontend

### Décision :
Utiliser **Vue 3 (Composition API)**, **TypeScript** et **Vite** comme outil d'assemblage et serveur de développement.

### Rationalité :
- **Réactivité fine** : Vue 3 repose sur un système de réactivité extrêmement performant (via des Proxies JavaScript), idéal pour rafraîchir en temps réel la grille horaire hebdomadaire lors des opérations de Drag & Drop sans ré-évaluer tout le DOM.
- **Simplicité de lecture (Single File Components)** : Les fichiers `.vue` regroupent logiquement HTML, TypeScript et CSS Vanilla, facilitant la lisibilité et le ton pédagogique imposé par la Constitution.
- **Vitesse d'exécution** : Vite offre un serveur de développement instantané (grâce au rechargement de modules à chaud ESM natif) et des builds finaux optimisés.

### Alternatives considérées :
- *React* : Évalué en détail. Bien que très populaire, React exige une gestion d'état souvent plus verbeuse (useState/useContext) et n'intègre pas nativement de système de transitions CSS aussi simple et performant que l'élément `<Transition>` de Vue 3.
- *Vue 2* : Rejeté car en fin de vie et moins performant sur la réactivité que Vue 3.

---

## 3. Choix du Moteur d'Optimisation

### Décision :
Utiliser **Timefold Solver (Python)** s'exécutant intégralement en mémoire vive (RAM) à chaque cycle de calcul.

### Rationalité :
- **Modélisation orientée objet naturelle** : Timefold s'intègre directement avec nos modèles de données Python (les classes `@planning_entity` et `@planning_solution`). Le moteur résout le problème en manipulant directement notre graphe d'objets en mémoire vive.
- **Séparation des contraintes** : Permet de coder les contraintes de manière déclarative (ex: "un enseignant ne peut pas être à deux endroits en même temps" dans `constraints.py`) en utilisant l'API d'évaluation de score très optimisée de Timefold.
- **Résolution sous 5 secondes** : Pour le jeu de données restreint de la V1 (30 cours), Timefold trouve une solution optimale sans aucun conflit dur de manière quasi instantanée (< 1 seconde).

### Alternatives considérées :
- *Google OR-Tools* : Très puissant pour la programmation linéaire, mais la modélisation des contraintes d'emplois du temps scolaires (très qualitatives et dépendantes de critères humains) y est beaucoup plus ardue et moins lisible qu'avec Timefold.
- *Algorithme Greedy/Backtracking fait maison* : Rejeté. Trop complexe à faire évoluer lorsque de nouvelles contraintes (salles spécialisées, co-enseignement) seront ajoutées dans les versions ultérieures.

---

## 4. Choix de Confinement et d'Isolation

### Décision :
Utiliser un environnement virtuel Python local (`.venv`) et l'isolation native de Node.js via le dossier `node_modules` local, sans outil de containerisation système (pas de Docker).

### Rationalité :
- **Légèreté absolue** : Aucune dépendance de virtualisation système (pas de conteneur, pas d'hyperviseur). L'application tourne directement au niveau du processeur de la machine hôte.
- **Propreté de l'OS** : L'environnement Python reste confiné dans le dossier `backend/.venv` et les dépendances du frontend dans `frontend/node_modules`. La suppression de ces dossiers suffit à restaurer la machine hôte à son état d'origine.
- **Performance** : Les temps d'accès au système de fichiers et au réseau (`localhost`) restent maximaux, ce qui est crucial pour les calculs du solveur.

### Alternatives considérées :
- *Docker & Docker Compose* : Rejeté. Il a été formellement décidé d'exclure Docker de la tranche verticale V1 pour simplifier la configuration de développement et privilégier un démarrage local rapide et accessible sans connaissances en containerisation.
