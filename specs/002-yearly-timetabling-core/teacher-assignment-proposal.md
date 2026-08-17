# Proposition : Affectation automatique des besoins aux professeurs

**Statut** : brouillon de conception, non validé pour implémentation. Ce document consolide un
échange de conception complet ; il est écrit pour devenir la base des sections correspondantes de
`spec.md` (et d'une nouvelle section d'`architecture.md`), **mais n'y a pas encore été fusionné** —
volontairement, pour ne pas entrer en conflit avec `plan.md`/`spec.md`, activement utilisés par un
autre chantier en cours sur cette branche (`GenericList.vue`, refonte `groupBy`, non commité au
moment de l'écriture de ce document). Fusion à faire une fois cet autre chantier atterri, et après
validation explicite du contenu ci-dessous.

**Portée** : Lot 3 (Pré-rentrée), sous-chantier « couche Service » (voir mémoire
`project_service_layer`). S'appuie entièrement sur `MefService`/`Service`/`ServiceRepartition`/
`TrmdLine` déjà en place — n'introduit aucune nouvelle couche de gabarit.

---

## 0. Argumentaire — algorithme classique plutôt que Timefold

*(section destinée à devenir une sous-partie de `spec.md`, dans les règles métier du solveur)*

### Nature du problème

Contrairement au placement horaire (`COURSE_PLACEMENT`/`CLASSROOM_ASSIGNMENT`), l'affectation
prof→service n'est pas un problème de planification temporelle mais un **problème de transport /
affectation généralisée sous capacité** : des besoins pondérés (`Service` × volume horaire, typés
par discipline) à faire correspondre à des professeurs à capacité bornée, avec un coût par
correspondance et des exclusions dures.

Même sans aucune règle de cohérence, ce n'est déjà pas un matching biparti pur (contrairement au
cas des salles par créneau) : la capacité d'un professeur se consomme à travers plusieurs besoins
simultanément (plusieurs matières, plusieurs classes). Le baseline « sans couplage » est donc déjà
un problème de transport — classique, exactement soluble par un flot à coût minimal.

### Pourquoi rester en algorithme classique malgré les couplages réels

Deux familles de couplage existent et cassent la décomposition en affectations indépendantes :

- **Exclusions combinatoires** : incompatibilités entre professeurs (portée : jamais dans la même
  équipe pédagogique, voir §4.4). Non représentables proprement dans un flot pur quand deux
  besoins non encore décidés partagent la même division — traité par une passe de réparation
  après le flot (§5.3), pas par le flot lui-même.
- **Objectif agrégé non additif** : minimiser globalement le volume d'HSA généré par
  l'établissement (§2). Contrairement à un glouton par ordre de priorité (qui ne garantit rien
  globalement — voir l'exemple espagnol en §2), un flot à coût minimal à deux paliers de capacité
  garantit cette minimisation *par construction*.

Aucun de ces couplages ne nécessite de recherche itérative (Timefold) : le premier est traité par
un filtrage/une réparation gloutonne classique après résolution, le second est nativement résolu
par un algorithme de flot exact. Aucun des trois logiciels concurrents étudiés (UnDeuxTEMPS, EDT,
Charlemagne — voir échange préalable) n'utilise de recherche itérative sur ce sous-problème
précis : UDT documente un glouton déterministe (« ordre de service décroissant »), EDT une
simulation rejouable à la demande, Charlemagne reste 100% manuel.

### Différence structurelle avec le cas des salles (continuité)

Pour les salles, `timeslot`/`week_type` sont déjà figés par `COURSE_PLACEMENT` avant
`CLASSROOM_ASSIGNMENT` — c'est un sous-problème captif à l'intérieur d'un solve Timefold déjà en
cours. L'affectation prof→service a lieu **en amont de toute la chronologie de résolution**
(phase pré-rentrée, avant que `Course`/`timeslot` existent) : il n'existe aujourd'hui aucun solve
Timefold à ce stade. Introduire Timefold ici serait donc un **second solveur autonome** à
maintenir (nouvelle entité de planification, nouvelle config de score, nouvelle orchestration),
pas une ligne de contrainte en plus dans le pipeline existant.

### Hors périmètre, assumé

Ce module ne vérifie pas la faisabilité agrégée multi-professeurs d'une même classe (ex. trois
matières confiées chacune à un professeur disponible un seul jour, pour une classe fermée ce
jour-là) — cette vérification reste le rôle de `COURSE_PLACEMENT`, en aval, qui dispose déjà de
toutes les contraintes réelles (salles, autres classes, autres profs). Un signal de compatibilité
horaire pairwise (§5.2) sert d'avertissement, pas de garantie de faisabilité.

---

## 1. Cinématique cible (calquée sur EDT, simplifiée)

Klepsydrix a déjà, via la cascade `MefService → Service → ServiceRepartition`, l'équivalent du
module Prérentrée d'EDT (MEF → classes prévisionnelles → services hérités) — pas besoin de le
réimplémenter, seulement l'étape « Affecter les professeurs aux services » :

1. Vérifier que chaque `Service` a une discipline qualifiée disponible côté `TeacherDiscipline`
   (déjà le cas, rien à faire).
2. Renseigner les critères optionnels côté professeur : niveaux souhaités + priorité + nombre max
   de classes par niveau (`TeacherGradePreference`, §4.2), incompatibilités (§4.4), plafond HSA
   (`max_hsa_duration_minutes`, §4.1).
3. Lancer une **simulation** (dry-run, non persistée, rejouable à volonté).
4. Contrôler le résultat proposé : avertissements (capacité dépassée, faible recouvrement horaire,
   besoin non couvert, incompatibilité non résolue faute d'alternative — voir §5.3) + métrique de
   qualité (HSA générée par professeur, §5.4, comparée à ce qu'un `Service` non verrouillé aurait
   pu éviter).
5. Valider → écrit réellement dans `Service.teachers`.
6. Tout `Service` avec `teachers_locked = True` n'est jamais touché par l'algorithme, qu'il soit
   vide ou déjà pourvu (verrouillage explicite, voir §4.3 — pas de convention implicite).

---

## 2. Minimiser globalement les HSA de l'établissement

**Exigence produit explicite** : si un besoin peut être couvert sans demander d'HSA à personne, il
doit l'être — l'établissement doit retomber le plus près possible du volume d'HSA structurellement
inévitable.

**Pourquoi un glouton simple ne suffit pas** : un glouton qui traite les besoins un par un dans
l'ordre de priorité peut laisser un premier besoin accaparer le seul professeur disponible en
palier normal, et forcer un besoin *suivant* de la même discipline à tomber en HSA — alors qu'une
affectation différente des mêmes besoins aux mêmes professeurs aurait évité toute HSA (exemple :
besoin d'espagnol en classe A confié à un professeur qui aurait pu couvrir la classe B à la place,
laissant un deuxième professeur, seul capable de couvrir A, partir inutilement en HSA).

**Solution retenue** : formuler comme un flot à coût minimal à deux paliers de capacité par
professeur (détail §5.1) — capacité « normale » à coût quasi nul, capacité HSA à coût
volontairement écrasant (largement supérieur à toute combinaison de coûts de priorité/
compatibilité horaire). Un flot à coût minimal sature nécessairement tous les arcs de capacité
normale disponibles avant de faire passer la moindre unité par un arc HSA — la minimisation
globale est alors garantie par construction, pas par une heuristique d'ordre.

---

## 3. Suppression de `Teacher.max_weekly_hours`

Vieille scorie historique, à retirer. Usage vérifié avant suppression — **aucune référence dans le
solveur** (`constraints.py`/`solver.py`), champ purement déclaratif. Périmètre de suppression :

- `backend/app/models/teacher.py` — retirer la colonne (ligne 24 au moment de l'écriture).
- `backend/app/api/ui.json` — retirer le champ du formulaire (`teachers_form`, ligne 422).
- `backend/app/core/init_demo.py` — retirer de l'`INSERT` (ligne 169).
- `backend/tests/test_generic.py` — retirer du payload de test (ligne 183).

Conséquence : le palier « capacité normale » de l'affectation n'est **pas** un plafond scalaire
séparé — c'est directement la somme des apports déclarés par discipline (`TeacherDiscipline.
duration_minutes`), déjà existante.

---

## 4. Modèle de données

### 4.0 Réutilisé sans changement

`Service.teachers` (cible de l'affectation), `TeacherDiscipline` (qualification + apport),
`TeacherAra`/`TeacherAre`/`TeacherOtherSchool` (= ARA/ARE/CSD), `ResourcePreference` (grille
Teacher/Division), `RefGrade`, `ServiceRepartition`.

**Considéré et explicitement exclu** : `ResourceConstraint` (plafonds de rythme — max heures/jour,
demi-journées travaillées, etc., déclinés symétriquement sur `Teacher` et `Division`). Contrairement
à `ResourcePreference` (état statique directement comparable entre deux grilles), `ResourceConstraint`
ne prend son sens que rapporté à un arrangement réel de plusieurs cours dans la semaine — exactement
le type de vérification agrégée renvoyé à `COURSE_PLACEMENT` (voir §0, hors périmètre assumé).

### 4.1 `backend/app/models/teacher.py` à modifier

- Suppression de `max_weekly_hours` (§3).
- Nouveau champ `max_hsa_duration_minutes` (Integer, `nullable=False`, `default=120` soit 2h00 par
  défaut, `info={"type": "duration"}` — même convention que `duration_minutes`/`ara_duration_minutes`
  et consorts) — plafond HSA, palier 2, **global** au professeur (pas décliné par discipline —
  c'est une enveloppe administrative unique).
- Nouvelle relation possédée `grade_preference_lines` (même patron que `discipline_lines`).
- Nouvelle relation `incompatible_teacher_ids` (§4.4).
- Trois nouvelles propriétés calculées à la demande (§6).
- `Teacher.create()` surchargé : cascade de génération vers `TeacherGradePreference` (§4.3).

### 4.2 Nouveau `backend/app/models/teacher_grade_preference.py`

`TeacherGradePreference(teacher_id, ref_grade_id, priority: int 1-5, max_class_count: Optional[int])`
— équivalent EDT (niveaux souhaités + priorité + nombre max de classes par niveau). Contrainte
d'unicité `(teacher_id, ref_grade_id)`.

### 4.3 Cascade de création automatique Teacher ↔ RefGrade

Même patron que `MefService`/`MefDivision` → `Service` (architecture.md §15.G) :

- `Teacher.create()` génère une ligne `TeacherGradePreference(priority=2, max_class_count=None)`
  pour chaque `RefGrade` existant.
- `RefGrade.create()` génère une ligne symétrique pour chaque `Teacher` existant.
- Générateur factorisé dans une seule méthode partagée sur `TeacherGradePreference`, appelée des
  deux côtés — évite la duplication de construction du dict `vals`.

### 4.4 Incompatibilités entre professeurs

Nouvelle table d'association symétrique `teacher_incompatibilities(teacher_id_a, teacher_id_b)`,
contrainte `teacher_id_a < teacher_id_b` pour éviter les doublons miroirs. Exposée via le widget
`relation_browser` déjà documenté (architecture.md §15.J.1 — relation indépendante many2many,
jamais many2one, en popin) : **aucun nouveau composant Vue**.

**Portée** : jamais dans la même équipe pédagogique = jamais professeurs affectés à des `Service`
de la **même Division**, tous services confondus (pas restreint au même `Service`). Résolution de
la Division : directe via `Service.division_id` (`related_field` existant) pour un `Service` lié à
une `MefDivision` ; pour un `Service` lié à un `Group`, remontée `Group → ClassPart → Division` —
traversée exacte à vérifier dans `class_part.py`/`division.py` au moment du code.

### 4.5 `backend/app/models/service.py` à modifier

Nouveau champ `teachers_locked: Mapped[bool]` (Boolean, défaut False) — verrouillage explicite
(pas de convention implicite « déjà pourvu = verrouillé ») : quand `True`, l'algorithme n'écrit
jamais dans `Service.teachers` pour cette ligne, qu'elle soit vide ou déjà pourvue (couvre aussi le
verrouillage partiel : un `Service` avec un professeur déjà posé et verrouillé, où l'algorithme
n'ajoute pas de co-enseignant).

### 4.6 `backend/app/models/course.py` à modifier

Nouveau champ `weighting_coefficient` (Float, défaut 1.0) — copié depuis `service.
weighting_coefficient` au moment de la génération (`wizard_course_generation.py`,
`_courses_from_service`/`_courses_from_alignment`), reste à 1.0 pour un cours créé manuellement
sans `Service` d'origine (`Course` n'a et ne doit pas avoir de lien de retour vivant vers `Service`
— cohérent avec le reste de la génération, qui copie plutôt que référence).

---

## 5. Algorithme classique (`backend/app/solver/teacher_assignment.py`)

Python pur, **aucun lien avec Timefold** (`constraints.py`/`solver.py` non touchés). Nouvelle
dépendance validée : `networkx` (ajoutée à `backend/requirements.txt`), pour le flot à coût
minimal — seule dépendance nouvelle de tout ce chantier.

### 5.1 Structure du graphe

- Un nœud « palier 1 » par couple (professeur, discipline) : capacité = `assignable_capacity(T, D)`
  (§5.2), coût quasi nul.
- Un nœud « pool HSA » par professeur, capacité = `max_hsa_duration_minutes`, coût volontairement écrasant
  (dominant toute combinaison de coûts de priorité/compatibilité) — **partagé entre toutes les
  disciplines du professeur** : le débordement de chaque palier 1 discipline converge vers ce
  même pool avant le puits final.
- Un nœud intermédiaire par (professeur, niveau) borne le **nombre de divisions distinctes**
  (`TeacherGradePreference.max_class_count`, pas un volume horaire) — capacité entrante = ce
  plafond, subdivisée en un arc par division du niveau (capacité 1 chacun, présence/absence).
- Arêtes besoin → professeur uniquement entre disciplines qualifiées (`TeacherDiscipline`).

### 5.2 Capacité palier 1 — `assignable_capacity(T, D)`

```
assignable_capacity(T, D) = teacher.discipline_duration_minutes   # apport déclaré pour D
                             - teacher.ara_duration_minutes        # décompté
                             + teacher.are_duration_minutes        # jamais décrémentée, toujours ajoutée
                             - teacher.other_school_duration_minutes  # CSD, déduit
```

Calculée sous `db.filter_discipline_id = D` (contexte ambiant déjà utilisé par
`trmd_synthesis.py`) — ARA/ARE/CSD ne portent aucun `discipline_id` propre, donc attribués en bloc
à la **discipline majeure** du professeur (`_sum_lines_by_discipline_majeure`, mécanisme déjà
existant, aucune nouvelle propriété nécessaire sur `Teacher`).

Cohérence avec le TRMD, terme à terme (`trmd_synthesis.py:165-166`) :

| | TRMD (`def_teached`/`def_given`) | `assignable_capacity` (ce module) |
|---|---|---|
| Apport déclaré | `discipline_duration_minutes` | identique |
| ARA | soustrait | identique |
| CSD | soustrait | identique |
| ARE | *pas dans « teached »*, ajouté côté besoin | **ajouté ici** — seule divergence assumée |

La divergence sur ARE est volontaire : le TRMD raisonne en masse par discipline (ARE = un besoin
de plus à couvrir), ce module raisonne du point de vue d'un professeur précis affecté à un
`Service` réel. Cette capacité est un **plafond heuristique** qui guide le flot — elle n'a pas
besoin d'être l'image miroir exacte de `hsa_duration_minutes` (§6), qui est une vérité
rétrospective calculée sur les `Course` réels une fois l'affectation faite.

### 5.3 Incompatibilités — réparation après le flot

Non représentées dans le graphe de flot (couplage entre décisions simultanées sur une même
division, non flot-représentable). Passe de réparation après résolution : détecter les divisions
où deux professeurs incompatibles (§4.4) se retrouvent coaffectés.

**Réparation par re-résolution contrainte, pas par essai heuristique** : pour un conflit détecté
(T1 et T2 incompatibles, coaffectés sur la division D), interdire temporairement l'arête
(T1 → son besoin) dans le graphe de flot et **relancer la résolution complète** du flot à coût
minimal sous cette contrainte. Un flot à coût minimal est un algorithme exact : s'il existe *une*
réaffectation possible — même en cascade sur plusieurs professeurs (T1 part vers un autre besoin,
ce qui libère un professeur qui prend la place de T1, etc.) — le solveur la trouve nativement,
sans avoir à écrire de recherche combinatoire séparée. Si cette résolution échoue (aucun flot
faisable sous la contrainte) ou si la nouvelle solution laisse subsister un conflit sur D, on
retente symétriquement en interdisant l'arête (T2 → son besoin).

**Seulement si les deux tentatives échouent** — ce qui constitue une certitude réelle, garantie par
l'optimalité du flot et non une estimation — le conflit est **surfacé comme avertissement
explicite** dans l'étape de review du wizard (§8) — distinct de « besoin non couvert » (§1) : ici
les deux besoins sont couverts, juste par deux professeurs qui ne devraient pas se croiser. Non
bloquant pour `apply` : c'est à l'humain de trancher (décocher l'une des deux propositions, ou
relancer la simulation après avoir ajusté un critère).

Conflits multiples (plus de deux professeurs mutuellement incompatibles sur la même division) :
traités un par un, chaque réparation réussie devenant la nouvelle base avant d'évaluer le suivant.
Coût contenu : le sous-problème reste petit (mêmes ordres de grandeur que le reste de ce module),
et le solveur n'est relancé que pour les conflits effectivement détectés — un ou deux re-solve par
conflit, pas une explosion combinatoire.

### 5.4 Métrique de contrôle post-résolution

Après `apply` (§7), recalcul de `Teacher.hsa_duration_minutes` (§6) par professeur affecté —
affiché dans l'étape de review du wizard comme métrique de qualité de l'affectation proposée, pas
comme entrée du flot.

---

## 6. Champs calculés sur `Teacher` et `Course` (à la demande, non stockés)

Décision actée après discussion : calcul à la demande pour les quatre champs, pas de stockage.
Raison : ces valeurs dépendent de données vivant sur d'autres tables (`Course` via `course_teachers`,
`TeacherAra`/`TeacherAre`/`TeacherOtherSchool`/`TeacherDiscipline`) — rien aujourd'hui ne
déclencherait leur recalcul si elles étaient stockées (éditer un `Course` ou une ligne ARA ne
déclenche aucune `@constrains()` sur `Teacher`). Stocker aurait exigé de surcharger `create()`/
`update()`/`delete()` sur cinq modèles différents pour forcer un recalcul en cascade, avec un
vrai risque de perf sur la génération de masse de `Course` (centaines de lignes en une passe). Le
calcul à la demande évite toute cette complexité et reste toujours frais.

```python
# course.py
@exposed(info={"label": "Durée pondérée", "type": "duration", "readOnly": True})
@property
def weighted_duration_minutes(self) -> int:
    return round(self.duration_minutes * self.weighting_coefficient)

# teacher.py — section « Champs calculés pour le TRMD »
@exposed(info={"label": "Heures enseignées (brutes)", "type": "duration", "readOnly": True})
@property
def taught_raw_duration_minutes(self) -> int:
    return sum(c.duration_minutes for c in self.courses if not c.children)

@exposed(info={"label": "Heures enseignées (pondérées)", "type": "duration", "readOnly": True})
@property
def taught_weighted_duration_minutes(self) -> int:
    return sum(c.weighted_duration_minutes for c in self.courses if not c.children)

@exposed(info={"label": "HSA (surservice, si > 0) / Sous-service (si < 0)", "type": "duration", "readOnly": True})
@property
def hsa_duration_minutes(self) -> int:
    return (
        self.taught_weighted_duration_minutes
        + self.are_duration_minutes + self.ara_duration_minutes + self.other_school_duration_minutes
        - self.discipline_duration_minutes
    )
```

Notes :
- `if not c.children` : exclut les cours composés parents (qui ne portent pas de durée réelle,
  seuls leurs enfants comptent) — inclut les cours placés et non placés.
- `hsa_duration_minutes` a une **portée globale**, pas par discipline (`discipline_duration_minutes`
  et les trois autres termes lus **sans** positionner `db.filter_discipline_id` — elles retombent
  déjà sur la somme totale non filtrée dans ce cas, mécanisme déjà existant).
- ARE toujours ajoutée, jamais décrémentée — cohérent avec §5.2, mais les deux formules ne sont
  **pas** des images miroir exactes l'une de l'autre (vérifié algébriquement) : `assignable_capacity`
  est un plafond heuristique qui guide l'algorithme, `hsa_duration_minutes` est la vérité
  rétrospective une fois les `Course` réels posés. Ce n'est pas une incohérence à corriger.

---

## 7. API — wizard unique (simulate + apply)

Sur le patron exact de `WizardCourseGeneration` (`wizard_course_generation.py`, `TransientModel` +
`__actions__`) :

```python
# backend/app/models/wizard_teacher_assignment.py
class WizardTeacherAssignment(TransientModel):
    __tablename__ = "wizard_teacher_assignments"
    __actions__ = [{
        "id": "assign_teachers",
        "label": "Affecter les professeurs",
        "type": "wizard",
        "steps": [
            {
                "id": "scope",
                "title": "Périmètre",
                "fields": [...],  # établissement / niveau / filière
                "submitLabel": "Lancer la simulation",
                "rpc": "rpc_simulate",
            },
            {
                "id": "review",
                "title": "Résultat de la simulation",
                "isLast": True,
                "fields": [
                    {"key": "proposals", "type": "list_preview", "label": "Propositions"}
                ],
                "submitLabel": "Valider",
                "rpc": "rpc_apply",
                "rpcParams": {"proposals": "proposals"},
            },
        ],
    }]
```

`rpc_simulate` retourne `{"proposals": [...]}` (fusionné dans le brouillon du wizard, mécanisme
déjà générique de `GenericWizard.vue`, rien à y changer). `rpc_apply` reçoit `draft.proposals`
(éventuellement amputé des lignes décochées par l'utilisateur en étape de review), écrit dans
`Service.teachers` (sauf `Service` verrouillés), retourne
`{"mutated_resources": ["services"], "hsa_by_teacher": {...}}` (métrique §5.4).

---

## 8. Frontend

- **`GenericWizard.vue`** : réutilisé tel quel, aucun changement — le mécanisme d'accumulation du
  brouillon entre étapes via fusion du résultat RPC couvre déjà ce besoin.
- **`GenericList` en mode transitoire** : nouveau type de champ (`list_preview`) affichant
  `draft.proposals` — un tableau déjà en mémoire, jamais persisté, jamais récupéré depuis
  `/api/generic/{resource}`. Changement minimal proposé : `GenericList` accepte une prop optionnelle
  (`staticItems` ou équivalent) qui, si présente, court-circuite le fetch et rend directement le
  tableau donné, en réutilisant tout le rendu de colonnes/sélection existant (cases à cocher par
  ligne pour exclure une proposition avant validation).
  **Point de coordination bloquant** : `GenericList.vue` est en cours de refactor dans une autre
  session au moment de l'écriture de ce document (chantier `groupBy`, non commité) — ce changement
  ne peut être écrit qu'une fois cet autre chantier atterri, la structure exacte du composant
  post-refactor n'étant pas encore stabilisée.
- **Formulaire `Teacher`** (`ui.json`, `teachers_form`) : nouvel onglet notebook « Préférences
  d'affectation » (même patron que les onglets existants « Volumes horaires annexes ») contenant
  `max_hsa_duration_minutes` (champ scalaire), `grade_preference_lines` (relation possédée), et
  `incompatible_teacher_ids` (widget `relation_browser`).

---

## 9. Documentation, seed, tests

- **`spec.md`** : nouvelle user story « Affectation automatique des besoins aux professeurs » +
  nouvelles entités (`TeacherGradePreference`, `teacher_incompatibilities`, `Service.
  teachers_locked`, `Teacher.max_hsa_duration_minutes`, `Course.weighting_coefficient`, les quatre propriétés
  calculées) + nouvelle règle métier reprenant l'argumentaire de la §0.
- **`architecture.md`** : nouvelle section documentant le choix algorithme classique vs Timefold
  pour ce cas (précédent réutilisable pour d'autres automatisations pré-rentrée), et le pattern
  flot à coût minimal à paliers de capacité.
- **`data-model.md`** : nouvelles entités.
- **`init_db.py`/`init_demo.py`** : retrait des références à `max_weekly_hours`, seed de
  `max_hsa_duration_minutes`, `Course.weighting_coefficient`, et des lignes `TeacherGradePreference`, puis
  rejeu (`stop` → `init_db` → `start`).
- **`backend/tests/test_teacher_assignment.py`** (nouveau) : capacité palier 1/2 respectée,
  minimisation globale des HSA (cas de test reproduisant explicitement l'exemple espagnol du §2,
  pour vérifier que le flot évite bien l'HSA évitable là où un glouton naïf y tomberait),
  incompatibilités respectées (portée Division), `Service` verrouillés jamais touchés, discipline
  non qualifiée exclue, + test API `simulate`/`apply`.
- Vérification `curl` end-to-end une fois codé, avant de déclarer le travail terminé.

---

## 10. Récapitulatif des fichiers

**Nouveaux** :
- `backend/app/models/teacher_grade_preference.py`
- `backend/app/solver/teacher_assignment.py`
- `backend/app/models/wizard_teacher_assignment.py`
- `backend/tests/test_teacher_assignment.py`

**À modifier** :
- `backend/app/models/teacher.py` (suppression `max_weekly_hours`, ajout `max_hsa_duration_minutes` +
  `incompatible_teacher_ids` + `grade_preference_lines` + 3 propriétés calculées + cascade `create()`)
- `backend/app/models/ref_grade.py` (cascade `create()` symétrique)
- `backend/app/models/service.py` (ajout `teachers_locked`)
- `backend/app/models/course.py` (ajout `weighting_coefficient` + propriété `weighted_duration_minutes`)
- `backend/app/models/wizard_course_generation.py` (renseigne `weighting_coefficient` à la génération)
- `backend/app/api/ui.json` (retrait `max_weekly_hours`, nouvel onglet Teacher, wizard d'affectation)
- `backend/app/core/init_db.py` / `init_demo.py` (seed)
- `backend/tests/test_generic.py` (retrait `max_weekly_hours` du payload)
- `backend/requirements.txt` (ajout `networkx`)
- `frontend/src/components/GenericList.vue` (mode transitoire — **en attente de l'atterrissage du
  chantier `groupBy` en cours ailleurs**)
- `specs/002-yearly-timetabling-core/spec.md`, `architecture.md`, `data-model.md` (fusion finale de
  ce document, une fois validé)

---

## 11. Décisions actées durant la conception (traçabilité)

Pour référence rapide, dans l'ordre où elles ont été tranchées :

1. Algorithme classique (flot à coût minimal), pas Timefold — argumentaire §0.
2. Verrouillage explicite (`teachers_locked`), pas de convention implicite.
3. Portée incompatibilité : équipe pédagogique = même Division, pas seulement même `Service`.
4. `max_hsa_duration_minutes` : plafond HSA explicite, distinct de l'apport déclaré.
5. ARA décompté, ARE jamais décrémentée (compté) — confirmé à deux reprises pour le module
   d'affectation, y compris explicitement pour `hsa_duration_minutes`.
6. Cohérence avec le TRMD sur ARA/CSD — écart assumé et documenté sur ARE uniquement (§5.2, §6).
7. `TeacherGradePreference` enrichi d'un `max_class_count` en plus de la priorité.
8. Cascade de création automatique Teacher ↔ RefGrade → `TeacherGradePreference` (priorité par
   défaut 2, sans plafond de classes par défaut).
9. `simulate`/`apply` = deux étapes d'un seul wizard générique, pas deux écrans séparés.
10. Préférences de niveau + incompatibilités : nouvel onglet du formulaire Teacher, pas de popin.
11. `GenericList` adapté en mode transitoire pour la review du wizard, pas de tableau bespoke.
12. Minimisation globale des HSA : exigence produit explicite, a fait basculer l'algorithme d'un
    glouton simple vers un flot à coût minimal — `networkx` validé comme dépendance.
13. `max_weekly_hours` supprimé (scorie historique).
14. `Course.weighting_coefficient` + `weighted_duration_minutes` ajoutés pour porter le calcul HSA.
15. Trois champs `Teacher` (`taught_raw`/`taught_weighted`/`hsa_duration_minutes`) : calculés à la
    demande, jamais stockés — décision finale après discussion du coût du stockage cross-modèle.
