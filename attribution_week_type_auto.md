# Attribution automatique du week_type (Quinzaine indéterminée)

Journal de traçabilité des échanges et décisions sur ce sujet — un projet majeur touchant le modèle de données (`Course.week_type`), le moteur de résolution (Timefold) et le workflow de placement manuel.

Chaque section ci-dessous correspond à un échange complet (message utilisateur + réponse), consigné tel quel, dans l'ordre chronologique.

---

## Échange 1 — Cadrage initial et analyse d'impact

### Message utilisateur

> J'aurais besoin de modifier la gestion des "weektype" des cours :
> - je veux pouvoir matérialiser sur le cours qu'il aura lieu en quinzaine (une semaine sur deux), mais laisser l'algorithme de placement (ou bien le workflow manuel de décomposition d'un cours) définir ultérieurement s'il sera en semaine A ou en semaine B. Je pense qu'il faut ajouter une valer Q à l'ENUM (dans prefrence.py);
> - Tout cours placé dans la grille doit OBLIGATOIREMENT avoir un weektype différent de Q :
> 	> Lors d'un placement manuel, l'usager doit forcément avoir précisé la semaine avant de placer le cours.
> 	> Lors du placement automatique, si un cours a un weektype=Q, alors l'agorithme de placement attribue une lettre (soit A soit B). Le plus simple est peut-être  que l'algorithme de placement attribut le weektype=A avant de commencer à placer les cours, et optimiser la semaine a posteriori.
> 		> Si le cours n'est pas verrouillé, l'algorithme de placement automatique/optimisation doit pouvoir changer cette valeur entre A et B pour optimiser l'emploi du temps (mais pas revenir de A ou B vers Q).
>
> ==> Explique moi les conséquences (choses à changer, impacts sur le moteur de calcul etc.). Fais une analyse approfondie pour me présenter les potentiels problèmes et les limites.

### Réponse

Les trois agents de recherche confirment une image cohérente. Voici l'analyse.

#### État actuel (pour cadrer l'analyse)

- **`WeekType`** (`preference.py:10-13`) : `A`, `B`, `W` (= "toutes les semaines", neutre — `weeks_overlap()` dans `constraints.py:194-197` traite `W` comme chevauchant A et B).
- Utilisé sur **deux modèles distincts** : `Course.week_type` (`course.py:127`) et `ResourcePreference.week_type` (`preference.py:31`) — deux colonnes Enum SQL séparées (`course_week_type_enum` vs `week_type_enum`), donc déjà structurellement scindables malgré la classe Python partagée.
- **Pas de modèle "session/occurrence"** : une quinzaine s'incarne aujourd'hui comme **deux `Course` sœurs** (enfants d'un cours composé), chacune avec son propre `week_type=A`/`B` — jamais un seul cours qui s'étend automatiquement sur deux occurrences.
- Le workflow de composition (`composition_mode.py`, modes 2/4/5/6) **génère déjà** ces paires A/B automatiquement, et `CourseCompositionPreview.vue` (étape 2 du wizard) permet déjà à l'utilisateur d'éditer le `week_type` de chaque ligne générée via un `<select>` W/A/B.
- Côté solveur (Timefold), `PlanningCourse` (`solver/constraints.py:151-174`) n'a que **deux** `@PlanningVariable` : `timeslot` et `classroom`. `week_type` est un simple champ `str` copié une fois depuis la DB avant résolution (`solver.py:226-227`), jamais réassigné, jamais réécrit en sortie (le write-back ne touche que `timeslot_id`/`classrooms`, `solver.py:342-368`) — il est lu en lecture seule dans une **vingtaine** de filtres/joiners de contraintes (`weeks_overlap`, `Joiners.equal(lambda c: c.week_type)`).
- Le verrouillage réellement branché au solveur est `Course.is_pinned` → `@PlanningPin` natif Timefold (`constraints.py:162`). `lock_structure` existe mais n'est **branché nulle part** (ni solveur, ni contraintes) — c'est un champ mort. Votre "verrouillé" correspond donc à `is_pinned`.
- Le placement manuel (`Sidebar.vue` → `CourseCard.vue` → `BaseGrid.vue` → `TimetableGrid.onDrop` → `App.vue::onMoveCourse` → `PUT /courses/{id}`) envoie **uniquement** `{timeslot_id, is_pinned, classroom_ids}` — `week_type` n'apparaît **pas du tout** dans ce flux aujourd'hui. Le sélecteur "Semaine" de `GridFilterBar.vue` est un **filtre d'affichage** global (quelle semaine est montrée), pas un champ lié au cours qu'on place.

---

#### 1. Ajouter la valeur Q à l'enum

Mécaniquement trivial (`class WeekType(str, enum.Enum): A="A"; B="B"; W="W"; Q="Q"`), mais Q est **sémantiquement différent** des trois valeurs existantes — ce n'est ni "toutes les semaines" (W), ni une semaine précise (A/B), c'est un état transitoire "sera en quinzaine, laquelle reste à déterminer". Chaque consommateur de l'enum doit être audité :

- **`weeks_overlap(w1, w2)`** : aujourd'hui, si w1 ou w2 vaut quelque chose d'inattendu, la fonction retombe sur `w1 == w2`. Un cours Q qui aurait *malgré tout* un `timeslot_id` (bug ailleurs) ne serait détecté en conflit avec **rien** — silencieusement dangereux. Le point 2 ci-dessous doit donc être une **garantie structurelle**, pas juste un cas bien géré.
- **`ResourcePreference.week_type`** : Q n'a aucun sens ici (préférence hebdomadaire d'une ressource, pas un cours en attente de placement). Comme les deux modèles ont déjà des enums SQL séparés, je recommande de **scinder aussi l'enum Python** (ex: `CourseWeekType` avec Q, `WeekType` sans) plutôt qu'un simple `@constrains` — sinon tout widget générique qui construit un `<select>` à partir des membres de l'enum Python affichera "Q" comme option valide sur les préférences de ressource aussi (le moteur de formulaire de ce projet est piloté par introspection du schéma, donc ce risque est réel, pas théorique).

#### 2. "Jamais Q sur un cours placé"

##### 2a. Placement manuel

Le point dur : **le flux de drag-and-drop actuel n'a aucun moyen de faire préciser la semaine à l'utilisateur**. `PUT /courses/{id}` ne transporte que `timeslot_id`/`is_pinned`/`classroom_ids`. Si on ajoute juste un `@constrains` qui rejette `timeslot_id is not None AND week_type == Q` dans `validate_placement_conflicts`, l'utilisateur qui glisse un cours Q sur la grille se prend une erreur 400 sans aucun moyen, dans cette même interaction, de résoudre l'ambiguïté.

Il faut donc une décision UX, pas juste un contrôle backend :
- **Option simple** : réutiliser le filtre "Semaine" déjà présent dans `GridFilterBar.vue` — s'il est positionné sur "Semaine A" ou "Semaine B" (pas "Toutes"), déposer un cours Q fixe automatiquement son `week_type` à cette valeur au moment du drop. Élégant (rien de neuf visuellement) mais détourne un filtre d'affichage pur en effet de bord qui modifie la donnée — à valider explicitement, ce n'est pas neutre.
- **Option alternative** : bloquer le drag d'un cours Q tant que sa semaine n'est pas choisie ailleurs (ex: forcer un petit sélecteur sur la `CourseCard` elle-même avant qu'elle devienne "draggable" pour de bon).

Je ne trancherai pas ce point à votre place — c'est exactement le genre de choix produit qui mérite d'être validé avant d'écrire du code.

##### 2b. Placement automatique (solveur)

C'est la partie la plus lourde de la demande : vous demandez en substance que **`week_type` devienne une vraie `@PlanningVariable`** pour les cours issus de Q — pas juste un fait copié.

- **Portée de la variable non-uniforme** : tous les cours n'ont pas vocation à voir leur `week_type` bouger — un cours `W` doit rester `W`, un cours déjà `A` (jamais passé par Q) doit rester `A`. Timefold ne permet pas nativement "cette variable est libre pour certaines entités, figée pour d'autres" via un simple range global partagé. Le pattern standard (Timefold/OptaPlanner) est un **value range par entité** (`@ValueRangeProvider` scopé à l'entité, retournant `['A','B']` pour les cours nés Q, et un singleton `[son_week_type_actuel]` pour les autres). Faisable, mais ce n'est pas un simple ajout d'annotation — ça change la forme de `PlanningCourse` et demande une méthode de range par instance.
  - **Inconnue à vérifier tôt** : je n'ai pas vérifié que les bindings Python de Timefold utilisés dans ce projet supportent proprement ce pattern de range par entité (l'API Java le supporte ; je n'ai pas de certitude sur la parité exacte côté `timefold.solver` Python). C'est le premier risque technique à lever — via un petit prototype — avant de s'engager sur le design complet.
- **"Q ne redevient jamais Q"** : se satisfait automatiquement du simple fait que Q ne sera **jamais** dans le range `['A','B']` proposé au solveur — pas besoin de règle spéciale, juste s'assurer que le range provider ne renvoie jamais Q.
- **Initialisation "attribuer A avant de commencer"** : votre intuition est la bonne approche — pré-seeder `week_type='A'` pour tout cours né Q au moment de la traduction DB→fait (`_build_planning_problem`, `solver.py`), avant construction du `PlanningCourse`, puis laisser la recherche explorer `{A,B}` à partir de ce point de départ. C'est plus simple que de gérer une "valeur non assignée" (contrairement à `timeslot` qui utilise `allows_unassigned=True`, ici on n'en a pas besoin : 2 valeurs, jamais de "non placé").
- **Interaction avec `is_pinned`** : bonne nouvelle — `@PlanningPin` gèle **toutes** les variables de planification de l'entité, pas variable par variable. Donc un cours épinglé verrait automatiquement son `week_type` figé en même temps que `timeslot`/`classroom`, sans code supplémentaire : ça correspond exactement à votre "si le cours n'est pas verrouillé, [...] sinon non".
- **Coût de performance** : `week_type` est aujourd'hui lu dans une vingtaine de définitions de contraintes (conflits prof/salle/classe/division, préférences, contraintes d'ordre "quinzaine"). En faire une variable réévaluée à chaque mouvement de recherche augmente mécaniquement l'espace exploré et le recalcul incrémental — pas rédhibitoire, mais à mesurer si beaucoup de cours démarrent en Q simultanément (ex: génération d'une année scolaire entière) plutôt qu'à supposer gratuit.
- **Write-back** : la boucle d'écriture après résolution (`solver.py:342-368`) ne touche que `timeslot_id`/`classrooms` — il faudra y ajouter `db_course.week_type = pc.week_type` (simple, sans risque particulier de l'écrire inconditionnellement même pour les cours non-Q, puisque leur valeur n'aura pas bougé).

#### 3. Effets de bord sur les mécanismes existants

- **`Course._sync_parent_week_type`** (`course.py:328-353`) : recalcule le `week_type` du parent composé depuis l'ensemble des enfants (tout-A→A, tout-B→B, mixte→W). Il faut définir la règle pour Q : un parent avec au moins un enfant encore Q devrait probablement lui-même rester/devenir Q (pas de règle actuelle pour ce cas).
- **`Course.is_consistent_with_service`** (`course.py:172-199`) : pour une `ServiceRepartition` en `BIWEEKLY`, attend aujourd'hui `week_type in (A,B)` — un cours fraîchement généré en Q serait immédiatement signalé "incohérent" par cet indicateur informatif, alors que Q est justement l'état attendu avant résolution. À mettre à jour pour accepter Q (au moins tant que le cours n'est pas placé), sinon régression sur une fonctionnalité existante.
- **Modes de composition 2/4/5/6** : génèrent aujourd'hui des paires A/B *directement*. Question à trancher explicitement : Q devient-il le **nouveau comportement par défaut** de ces modes (cohérent avec l'esprit de la demande : "laisser [...] le workflow de décomposition définir ultérieurement"), ou reste-t-il une **option manuelle supplémentaire** dans le sélecteur de `CourseCompositionPreview.vue` (qui a déjà W/A/B, il suffirait d'ajouter Q) sans toucher au comportement par défaut des modes ? Les deux lectures sont défendables selon votre formulation — je ne pré-tranche pas, mais notez que la première change un comportement existant testé (`test_composition_mode.py`), la seconde est additive et sans risque de régression.
- **Audit des points d'écriture de `timeslot_id`** : la garantie "jamais Q + placé" doit être vraie sur *tous* les chemins qui posent un `timeslot_id` (placement manuel, solveur, import éventuel, autres RPC) — pas seulement les deux évidents. Vaut la peine d'un grep ciblé avant implémentation pour lister tous les sites d'assignation.

#### Risques et limites — résumé

1. **API Timefold Python** : support réel du range-par-entité à vérifier tôt (spike), c'est le risque technique n°1.
2. **Performance solveur** : variable supplémentaire jointe dans ~20 contraintes ; à mesurer, pas à supposer négligeable.
3. **UX de placement manuel** : aucune affordance actuelle pour choisir la semaine au moment du drop — travail de design à trancher *avant* le backend, car ça détermine la forme du payload `PUT /courses/{id}`.
4. **Fuite sémantique de Q** : sans scission de l'enum, Q apparaîtra comme option valide sur `ResourcePreference` (et tout futur champ typé `WeekType`) via le moteur de formulaire générique.
5. **Décision produit non tranchée** : comportement par défaut des modes de composition (Q par défaut vs option manuelle) — impacte les tests existants si le défaut change.
6. **Effets de bord informatifs à corriger** : `is_consistent_with_service` et `_sync_parent_week_type` doivent explicitement apprendre Q, sinon régression silencieuse sur des indicateurs déjà en place.

Je n'ai rien implémenté — cette réponse est uniquement l'analyse demandée. Dites-moi comment vous voulez trancher les points 2a (UX du placement manuel) et le "Q par défaut vs optionnel" des modes de composition, et je peux ensuite écrire un plan d'implémentation détaillé.

---

## Échange 2 — Décisions UX/produit et analyse de performance approfondie

### Message utilisateur

> Pour le point 2a de placement manuel, lorsque le le secteur de semaine est à "Toutes", il faudrait scindé verticalement en 2 les colonnes de chaque jour. Si l'utilisateur dépose sur la zone de gauche, le cours est mis sur weektype=A, s'il dépose sur la colonne de droite, le cours est mis sur la weektype=B. Pour le second pointe je choisis la seconde option : une option manuelle supplémentaire dans le sélecteur de CourseCompositionPreview.vue (qui a déjà W/A/B, il suffirait d'ajouter Q). Par ailleurs, peux-tu analyser plus profondément l'impact prévisionnel sur les performances en donnant un exemple avant/après estimatif en complexité et en temps d'execution.

### Réponse

#### Sur les deux décisions

**2a — colonnes scindées A/B quand le filtre est sur "Toutes"** : bonne idée, plus propre que mes deux options (pas de détournement du filtre d'affichage, pas de blocage frustrant). Ça implique concrètement :
- `BaseGrid.vue` : rendu conditionnel de chaque cellule-jour en deux zones de drop quand `weekType === 'W'` (sinon, cellule pleine comme aujourd'hui — quand on filtre déjà sur "Semaine A", pas d'ambiguïté, toute la cellule vaut A).
- `TimetableGrid.onDrop` : doit maintenant recevoir *quelle moitié* a reçu le drop (coordonnée X relative à la cellule, ou deux zones DOM distinctes avec leur propre listener `@drop`), et le transmettre dans l'event `move`.
- `App.vue::onMoveCourse` → `api.updateCourse` → `PUT /courses/{id}` : le payload `CourseUpdate` doit gagner un `week_type` optionnel (aujourd'hui `{timeslot_id, is_pinned, classroom_ids}` seulement, `endpoints.py:105-108`).
- **Point à trancher avant de coder** : cette mécanique de split ne concerne-t-elle que la résolution des cours Q, ou s'applique-t-elle à *tout* dépose (dropper un cours déjà résolu en B sur la moitié gauche le repasserait-il en A) ? Les deux sont défendables, mais ce n'est pas neutre — un cours déjà A/B/W déposé sur la mauvaise moitié aujourd'hui ne change pas de semaine (le payload actuel ne touche pas `week_type`). Si vous voulez garder ce comportement pour les cours non-Q (seul Q est concerné par la résolution via le split), il faut que le backend/frontend ignore la position du drop sauf si `week_type == Q`.

**2b — Q comme option additive dans `CourseCompositionPreview.vue`** : noté, comportement des modes 2/4/5/6 inchangé, sans risque de régression sur les tests existants.

#### Analyse de performance approfondie

##### Cadrage avec les vrais paramètres du projet

Plutôt que de raisonner dans l'abstrait, vérification de la configuration réelle :

- **Budget de résolution** (`backend/app/core/config.py:11-12`) : `SOLVER_TIME_LIMIT_SECONDS=300`, `SOLVER_UNIMPROVED_TIME_LIMIT_SECONDS=10` — le solveur tourne à **budget de temps fixe** (`TerminationConfig(spent_limit=..., unimproved_spent_limit=...)`, `solver.py:313-316`), pas à budget de nombre de coups. C'est déterminant pour la suite : ajouter un type de mouvement ne "rallonge" pas le calcul, ça change **la répartition de l'exploration** à l'intérieur des 300s.
- **Échelle cible documentée** (`spec.md:13`) : "Structure pilote / Petite taille : jusqu'à 500 élèves, 40 enseignants, 30 salles, 20 classes."
- **Grille** : pas standard = 30 min (`STANDARD_TIMESLOT_DURATION` en seed), donc pour 5 jours × ~10h utiles ≈ **T ≈ 100 créneaux/semaine**.
- **Moteur natif JVM via JPype** (confirmé par `architecture.md` section 9.D, note sur les limites de traçage JPype) : le cœur de la recherche locale tourne en Java/Kotlin, pas en Python pur — important pour évaluer où se situe le vrai risque.

##### Estimation illustrative de N (nombre de `PlanningCourse`)

Pas de chiffre officiel dans les specs, donc estimation raisonnable à partir de l'échelle cible : 20 classes × ~25h de cours/semaine en moyenne ≈ **N ≈ 500** occurrences de cours à placer. Explicitement **illustratif**, pas mesuré.

Avec T≈100, C=30 (salles, valeur max documentée), N≈500 :

| Type de mouvement (aujourd'hui) | Taille du pool | Calcul |
|---|---|---|
| `ChangeMove(timeslot)` | ~50 000 | N×T |
| `ChangeMove(classroom)` | ~15 000 | N×C |
| `SwapMove(timeslot)` (si activé par défaut Timefold) | ~125 000 | N²/2 |
| **Total existant (ordre de grandeur)** | **~65 000 à ~190 000** | |

##### Coût ajouté par `week_type` en variable de planification

Le point clé, souvent contre-intuitif : **le range de `week_type` a une cardinalité de 2** (`{A, B}`), contrairement à `timeslot` (~100 valeurs) ou `classroom` (~30 valeurs). Ça borne structurellement sa contribution au pool de mouvements, quel que soit le nombre de cours Q :

| Scénario (part de cours nés Q parmi N=500) | `ChangeMove(week_type)` | `SwapMove(week_type)` | Part du pool total ajoutée |
|---|---|---|---|
| Réaliste (usage courant, ~5% : quelques cours composés à la fois) | 25×2 = 50 | ~300 | **≈ 0,05 %** |
| Rafale (~15% : import/génération en masse d'une année) | 75×2 = 150 | ~2 800 | **≈ 0,2 à 4 %** |
| Extrême (100% des cours nés Q simultanément) | 500×2 = 1 000 | ~124 750 | **≈ 0,5 à 40 %** (dominé par les swaps) |

Même dans le scénario extrême, `ChangeMove(week_type)` reste minuscule face à `ChangeMove(timeslot)` (1 000 vs 50 000) — c'est le `SwapMove` qui grossit vite si Timefold l'active par défaut pour cette variable (à vérifier/désactiver explicitement si non désiré, un `SwapMove` entre deux `week_type` n'a d'ailleurs guère de sens fonctionnel ici, contrairement au swap de `timeslot`).

**Conséquence sur le "temps d'exécution"** : comme le budget est en temps fixe, la vraie question n'est pas "ça prendra combien de secondes de plus" mais "à budget égal, la qualité finale du score change-t-elle". Sur la base de ces ordres de grandeur, un mouvement `week_type` supplémentaire est **peu coûteux à explorer et potentiellement très rentable** (flipper A→B pour résoudre un conflit prof/salle est une résolution directe d'une contrainte dure — un mouvement à fort effet de levier, comme le sont déjà les swaps de créneaux existants). Le risque d'un ralentissement perceptible de la convergence semble **faible dans les scénarios réalistes**, et seulement plausible dans un scénario de rafale massive et durable.

##### Le vrai risque : pas le pool de mouvements, mais le pont JPype

Là où l'incertitude reste réelle et où une mesure s'impose avant de trancher : si le range de valeurs par entité (`{A,B}` pour les cours Q, singleton pour les autres) est implémenté via une méthode Python appelée par la JVM à chaque évaluation de mouvement candidat (pattern typique d'un `@ValueRangeProvider` scopé à l'entité dans les bindings Timefold), **chaque appel traverse le pont JPype Python↔JVM** — un coût par appel de l'ordre de la microseconde, négligeable isolément, mais potentiellement significatif cumulé sur des millions d'évaluations en 300s. Les autres variables (`timeslot`, `classroom`) n'ont pas ce problème aujourd'hui car leur range est un `ValueRangeProvider` global, calculé une fois (`ProblemFactCollectionProperty`), pas réinterrogé par entité à chaque coup.

Inconnu à ce stade : si Timefold met en cache ce résultat par entité (probable, puisque le range d'une entité donnée ne change pas pendant la résolution) ou le réévalue systématiquement — **exactement la question à lever par le spike déjà recommandé** dans l'échange précédent, pas une hypothèse à trancher sans mesure.

##### Recommandation concrète

Avant d'implémenter le design complet : un spike isolé — ajouter `week_type` comme `@PlanningVariable` à portée d'entité sur un jeu de données synthétique à l'échelle cible (500 cours, 5-15% de cours Q), lancer un solve avec le budget réel (300s/10s), et comparer le score final obtenu **avec et sans** cette variable activée sur le même jeu de données. Ça donnerait de vrais chiffres en 10-15 minutes de travail, plutôt que des estimations.

---

## Échange 3 — Précision sur le comportement des cours de type W

### Message utilisateur

> Concernant le placement manuel : Attention, si un cours est de type W, les colonnes de la grille ne doivent pas se scinder en deux. Un cours de type W ne doit pas basculer en A ou B lors du placement. Si un cours est de type A ou B il est possible de le placer à gauche ou à droite et cela peut modifier le type de A en B.

### Réponse

Compris — ça répond d'ailleurs à la question ouverte laissée dans l'échange précédent (le split ne concerne pas que Q, il s'applique aussi aux cours déjà résolus A/B pour permettre une réassignation manuelle A↔B ; seul W en est exclu, logique puisque W occupe intrinsèquement les deux semaines à la fois).

Deux points à clarifier avant de figer le design :

**1. Split visuel statique vs dynamique selon le cours glissé**

Il y a deux façons d'obtenir "un cours W ne doit jamais basculer en A/B" :
- **(a) Dynamique** : les colonnes ne se scindent visuellement que pendant le glisser d'un cours A/B/Q — dès qu'on commence à faire glisser un cours W, la grille repasse en cellules pleines. Fidèle à la formulation littérale ("les colonnes de la grille ne doivent pas se scinder"), mais demande que `BaseGrid.vue` connaisse le `week_type` du cours en cours de glisser-déposer (via `dataTransfer` ou un état de drag partagé) pour re-render dynamiquement le layout des cellules en plein milieu d'une interaction drag — plus complexe côté frontend.
- **(b) Statique + gestion côté drop** : la grille garde en permanence sa ligne de séparation visuelle quand le filtre est sur "Toutes" (aucun changement de rendu pendant le drag), et c'est simplement le **gestionnaire de drop** qui ignore la position (gauche/droite) et force `week_type=W` quand le cours déposé est de type W. Le résultat fonctionnel est identique (W ne bascule jamais), sans re-rendu dynamique de la grille pendant l'interaction.

Recommandation : (b), plus simple et sans risque de flash visuel pendant le drag — mais si l'absence de la ligne de séparation pour un cours W a une vraie valeur (éviter la confusion visuelle "on dirait que je peux choisir alors que non"), (a) reste faisable. À trancher.

**2. Cohérence avec `is_pinned`**

Le placement automatique respecte déjà la règle "un cours épinglé ne bascule jamais A↔B". Faut-il appliquer la même garde au placement manuel — c'est-à-dire, un cours A/B épinglé (`is_pinned=True`) déposé sur la mauvaise moitié doit-il être rejeté/ignoré plutôt que de changer de semaine ? Cohérent avec l'esprit de "verrouillé = personne (ni algorithme, ni utilisateur) ne change ça", mais reste une décision produit à confirmer.

---

## Échange 4 — Confirmation split (a)+(b), portée de la règle "épinglé = non déplaçable"

### Message utilisateur

> Concernant le split, je veux les deux : je veux l'option (a), mais si un jour j'implémente le multi-section, je veux déjà mettre une sécurité : si je drop un cours W sur A ou B, on ignore la colonne dans la mise à jour vers le back. Ceinture et bretelles. Concernant ton second point, un cours épinglé ne PEUT pas être glissé / déposé.

### Réponse

Deux points notés, avec une clarification nécessaire sur le second.

**1. Split (a) + garde-fou (b) — confirmé, cohérent**

Trois couches de défense, du visuel jusqu'au backend :
- **Visuel (frontend, dynamique)** : `BaseGrid.vue` scinde les colonnes uniquement pendant le glisser d'un cours A/B/Q (nécessite que le composant connaisse le `week_type` du cours en cours de drag, via le payload `dataTransfer` ou un état de drag partagé exposé par `TimetableGrid.vue`).
- **Logique (frontend, drop handler)** : même si par accident un split était affiché ou qu'un event de drop arrivait avec une position gauche/droite pour un cours W, `onDrop`/`onMoveCourse` ignore explicitement cette position et n'envoie jamais de `week_type` dans le payload pour un cours W.
- **Backend (ceinture et bretelles)** : `Course.validate_placement_conflicts` (ou une nouvelle garde dédiée) rejette explicitement toute tentative de faire passer `week_type` de `W` vers `A`/`B` via le placement — peu importe la source de la requête (drag manuel, appel API direct, éventuel futur "multi-section"). C'est la vraie ceinture-et-bretelles : même si le frontend a un bug ou qu'un autre client de l'API existe un jour, le backend refuse structurellement.

**2. "Un cours épinglé ne peut pas être glissé/déposé"**

À vérifier : c'est plus large que le cas A/B initialement posé. Vérification du code — **aujourd'hui, `is_pinned` ne bloque déjà que le solveur** (`@PlanningPin`), pas le glisser manuel : `CourseCard.vue:17` a `draggable="true"` inconditionnel, et rien dans `Course.update()`/`validate_placement_conflicts` ne rejette un changement de `timeslot_id` sur un cours épinglé. Un cours épinglé peut donc être déplacé manuellement aujourd'hui, ce qui n'est probablement pas voulu depuis le début — mais c'est un écart **préexistant**, indépendant de ce chantier week_type.

La formulation ("un cours épinglé ne PEUT pas être glissé/déposé", sans restriction au cas A/B) sonne comme une règle générale, pas limitée à la réassignation de semaine. Question de portée à confirmer : corriger ce comportement **de façon générale** (plus aucun déplacement manuel, semaine ou créneau, pour un cours épinglé — dépasse le périmètre initial de ce chantier mais comble un vrai trou), ou seulement **dans le cadre de cette fonctionnalité A/B** (le cours reste déplaçable en créneau/salle malgré l'épinglage, comme aujourd'hui, mais ne peut plus changer de semaine via le split) ?

Techniquement, la version générale s'implémenterait de la même façon "ceinture et bretelles" : `:draggable="!course.is_pinned"` côté `CourseCard.vue` (empêche même de commencer le glisser) + un rejet backend explicite sur tout `timeslot_id`/`week_type` changeant pour un cours épinglé (couvre les autres clients API).

---

## Échange 5 — Implémentation : verrouillage général du déplacement manuel pour un cours épinglé

### Message utilisateur

> corrige ce comportement de façon générale (plus aucun déplacement manuel, semaine ou créneau, pour un cours épinglé — ce qui dépasse le périmètre initial de ce chantier mais comble un vrai trou)

### Réponse (implémentation)

Correctif implémenté en trois couches ("ceinture et bretelles", cohérent avec l'Échange 4), indépendamment du reste du chantier week_type (celui-ci comble un trou préexistant, sans dépendance sur Q/le split de colonnes) :

- **Backend** (`backend/app/models/course.py`, `Course.update()`) : nouvelle garde en tête de méthode — si le cours est épinglé avant ET reste épinglé après cet appel (`is_pinned=False` dans les mêmes `vals` désactive la garde, permettant "déverrouiller et déplacer" en un seul geste), tout changement effectif de `timeslot_id`, `classroom_ids` ou `week_type` est rejeté avec un `ValueError` explicite ("Impossible de déplacer/changer... un cours épinglé : déverrouillez-le d'abord."). Ne bloque pas le simple renvoi de la valeur courante inchangée (cas de la bascule du pin depuis `CourseCard.vue`, qui réenvoie le `timeslot_id` actuel). Remonte en `409` via `/api/timetable/courses/{id}` et en `400` via le CRUD générique (`/api/generic/courses/{id}`, PATCH) — les deux chemins d'écriture sont couverts.
- **Frontend** (`frontend/src/components/CourseCard.vue`) : `draggable="true"` devenu `:draggable="!course.is_pinned"` — un cours épinglé ne peut plus même démarrer un glisser-déposer. Ajout d'un `cursor: not-allowed` sur `.is-pinned-card` pour l'affordance visuelle (le curseur "grab" existant aurait été trompeur).
- **Test de non-régression** : `backend/tests/test_api.py::test_pinned_course_cannot_be_moved_manually` — couvre le rejet sur créneau/salle/semaine tant qu'épinglé, l'autorisation du renvoi de la valeur inchangée (bascule de pin), et l'autorisation du déverrouillage+déplacement simultané.

Vérifié : suite backend complète 127/127 (126 existants + 1 nouveau), build frontend propre. Base de dev re-seedée après les vérifications manuelles via curl.

---
