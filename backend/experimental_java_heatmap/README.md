# Optimisation de la Heatmap (Expérimentation Java / Timefold Python)

## 1. Contexte et Objectif
L'interface de placement interactif nécessite de calculer une **Heatmap** (carte de chaleur) indiquant quels créneaux horaires sont compatibles ou conflictuels avec un cours spécifique. L'algorithme simule le placement du cours sur chaque créneau disponible (ex: 120 créneaux) et évalue l'impact sur le score global.

**Problème initial :**
Dans la librairie Timefold Python, la méthode native `SolutionManager.update(problem)` s'assure de maintenir la parfaite synchronisation entre les objets Python et le moteur Java interne via JPype. Bien que très robuste, cette synchronisation a un coût massif. Une simple boucle de 120 itérations en Python prenait **~16,5 secondes**, ce qui est inutilisable pour de l'interactivité en temps réel.

**L'Objectif :**
Contourner le pont Python/Java pour la boucle d'évaluation incrémentale en codant un contrôleur natif en Java (`HeatmapEvaluator.java`) qui manipule directement les objets internes de Timefold, réduisant l'overhead au strict minimum.

---

## 2. Architecture de la Solution

La solution s'appuie sur une interception de la requête au sein de `solver.py` pour rediriger le calcul vers `heatmap_proxy.py`, qui pilote le code Java compilé. 

### A. Le Pattern "Dual-ScoreDirector" (100% Isofonctionnel)
Demander au moteur d'expliquer l'origine exacte d'un conflit (avec `ConstraintMatchPolicy.ENABLED`) consomme énormément de CPU et de mémoire. Pour accélérer le processus, le code Java instancie **deux ScoreDirectors** :
1. **Un "Fast" ScoreDirector** : Parcourt les 120 créneaux sans activer l'analyse des raisons de conflit. C'est lui qui détecte les dégradations de score à une vitesse de l'ordre de quelques millisecondes.
2. **Un "Detailed" ScoreDirector** : N'est appelé en "lazy loading" **que si** le Fast ScoreDirector détecte un score négatif. Il isole alors les raisons métier du conflit (ex: `Teacher conflict`). 

*Note : Cette architecture est strictement isofonctionnelle avec la logique d'origine en Python. En Python, `solution_manager.update()` utilise en sous-marin un moteur rapide, tandis que `solution_manager.explain()` instancie un moteur lourd. Le code Java ne fait que cloner cette optimisation "lazy", prouvant que la comparaison des performances (1,5s vs 16,5s) se fait à algorithme parfaitement équivalent.* 

### B. Manipulation des Proxys JPype
Le domaine métier (ex: `PlanningCourse`) est défini en Python. Timefold génère dynamiquement des coquilles Java ("Proxys") pour représenter ces entités.
Le script `heatmap_proxy.py` récupère les proxys Java des créneaux (via `java_problem.getTimeslots()`) et les transmet au module Java. 
En Java, le changement de créneau est forcé par la réflexion :
```java
setTimeslotMethod.invoke(targetCourse, timeslotProxy);
```
Il est ensuite impératif d'informer manuellement le moteur des changements pour que le flux de contraintes (Bavet) se déclenche de manière incrémentale :
```java
fastScoreDirector.beforeVariableChanged(targetCourse, "timeslot");
// ... application du changement ...
fastScoreDirector.afterVariableChanged(targetCourse, "timeslot");
```

### C. Contournement des classes masquées (Le Parsing du Score)
Une difficulté majeure rencontrée fut l'extraction du score. La méthode `fastScoreDirector.calculateScore()` retourne une classe interne (`InnerScore`) qui n'expose pas publiquement ses méthodes `hardScore()` et `softScore()` à la réflexion Java, provoquant des `NoSuchMethodException`.
**La solution :** Le module Java parse directement la chaîne générée par la méthode `toString()` du score (qui est garantie par le format Timefold, ex: `"-36init/-2hard/0soft"`). Cela évite de dépendre d'interfaces internes instables ou de librairies supplémentaires.

---

## 3. Résultats et Performances

- **Temps initial (Boucle Python `SolutionManager.update`)** : ~16.5 secondes.
- **Temps actuel (Java Hook)** : **~1.5 seconde**.

**Gains :**
L'accélération est de l'ordre de **x10**. La vaste majorité du temps de calcul restant (~1.2s) est désormais consommée une seule fois en amont par la fonction `convert_to_java_python_like_object` pour instancier les proxys. La boucle de 120 créneaux en Java pur ne prend quant à elle qu'environ **200 à 300 millisecondes**.

---

## 4. Instructions de Compilation et de Déploiement

Si des modifications sont apportées à `HeatmapEvaluator.java`, le JAR doit être recompilé et injecté dans l'environnement virtuel Python utilisé par FastAPI.

Depuis le répertoire racine du projet, exécuter :

```bash
cd backend/experimental_java_heatmap
# 1. Nettoyer et compiler le projet Maven
./apache-maven-3.9.6/bin/mvn clean package

# 2. Remplacer l'ancien JAR par le nouveau dans les dossiers JPype
cp target/heatmap-1.0-SNAPSHOT.jar ../.venv/lib/python3.12/site-packages/timefold/solver/jars/

# 3. Redémarrer le serveur FastAPI pour que le Classloader JPype prenne en compte la modification.
```

## 5. Perspectives d'Avenir et Limites de l'Hybride

Bien que l'expérimentation soit un succès massif pour la réactivité de l'application, ce code "hybride" reste une solution de contournement (hack). 

### Le goulot d'étranglement résiduel des Lambdas Python
Malgré l'exécution de la boucle en Java pur, le moteur de contraintes (Bavet) doit continuellement évaluer les règles métier définies dans `constraints.py`. Puisque ces contraintes utilisent des lambdas Python (ex: `lambda c: c.timeslot.day_of_week`), le ScoreDirector Java est obligé d'invoquer l'interpréteur Python en sous-marin pour chaque évaluation. Bien que l'incrémentalité réduise drastiquement le volume de ces appels par rapport à un `SolutionManager.update()` complet, cet aller-retour inter-langages conserve un léger surcoût.

### Pourquoi ne pas écrire les contraintes directement en Java ?
C'est une question tout à fait logique pour chercher la performance absolue. Mais la réponse courte est : **cela implique de réécrire quasiment tout le moteur en Java.**

En Java (langage fortement typé), le compilateur a besoin de connaître la structure exacte des classes (Course, Teacher, Timeslot) pour valider un `ConstraintProvider`. Or, nos classes de domaine (`PlanningCourse`, etc.) sont définies dynamiquement en Python (`domain.py`) et n'existent côté Java que sous forme de Proxys opaques générés par JPype.

**Ce que cela signifierait concrètement :**
Si l'on voulait basculer les contraintes en Java pour supprimer le dernier goulot d'étranglement, il faudrait adopter une **Architecture Core-Java / Wrapper-Python** :
1. **Domaine en Java :** Recréer les classes `Course.java`, `Teacher.java`, `Timeslot.java` en pur Java avec les annotations `@PlanningEntity`.
2. **Contraintes en Java :** Traduire intégralement `constraints.py` en `TimetableConstraintProvider.java`.
3. **Pont Python :** Côté FastAPI, utiliser JPype pour injecter les données SQLAlchemy directement dans les objets Java, et lancer le solveur Java.

### Conclusion
**Est-ce une bonne idée ?**
- **OUI**, si la performance algorithmique devient critique (milliers de cours, interface ultra temps-réel). C'est le standard "Enterprise" pour marier une API Python avec un moteur Java.
- **NON**, si l'on souhaite conserver une base de code 100% Python permettant à n'importe quel développeur de modifier les règles métier sans jamais compiler de Java. 

La librairie `timefold-solver-python` a été créée précisément pour éviter d'avoir à faire du Java. Cette expérimentation (le Dual-ScoreDirector en Java pilotant des proxys Python) représente donc aujourd'hui **le meilleur compromis absolu** entre performance algorithmique et rapidité de développement Python.

## 6. FAQ : Pourquoi ne pas réécrire `_solve_timetable_job` en Java ?

On pourrait logiquement se demander : *si la Heatmap a gagné un facteur x10 en migrant la boucle en Java, obtiendrait-on les mêmes gains monumentaux en déplaçant la fonction de résolution globale (`_solve_timetable_job` / `solver.solve()`) en Java natif ?*

La réponse est **NON** (le gain direct serait de 0%). 

Voici pourquoi la situation est fondamentalement différente de celle de la Heatmap :

**Le défaut de la Heatmap d'origine :**
L'ancienne Heatmap Python exécutait une boucle (`for ts in timeslots`) et appelait `SolutionManager.update(problem)` 120 fois. Cette fonction spécifique force le pont JPype à rescanner et resynchroniser l'intégralité du planning (tous les cours, toutes les salles) depuis Python vers Java à **chaque tour de boucle**. C'est ce travail de traduction massif et répété qui prenait 16 secondes. Notre `HeatmapEvaluator` Java a fait sauter cette étape en effectuant de la mutation locale incrémentale.

**Le fonctionnement de `solver.solve()` :**
Lorsque l'on appelle `solver.solve(problem)` depuis Python, la librairie confie immédiatement le contrôle total au moteur Java interne de Timefold. Toute la boucle de résolution (les milliers d'itérations, la recherche locale, les mouvements) **tourne déjà de manière 100% atomique et incrémentale à l'intérieur de la JVM**, en utilisant la même mécanique optimisée que notre Heatmap expérimentale.

**Le véritable goulot d'étranglement de la résolution globale :**
Bien que la boucle de résolution tourne nativement en Java, les objets manipulés restent des "Proxys" liés aux objets Python, et les contraintes (`constraints.py`) restent des lambdas exécutées par l'interpréteur Python. À chaque évaluation d'un mouvement local, le moteur Java effectue des appels JNI pour évaluer ces lambdas. 

Déplacer simplement l'appel `solver.solve()` du côté Java ne changerait rien à cette architecture hybride. La seule et unique façon d'obtenir un saut de performance majeur (x10 à x100) sur la durée totale de la résolution globale serait d'appliquer la solution radicale détaillée au **Chapitre 5** : migrer intégralement le modèle de domaine (`models/`) et les contraintes (`constraints.py`) en Java pur, faisant ainsi disparaître définitivement le pont JPype lors de l'exécution algorithmique.
