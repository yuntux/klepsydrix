"""
Wizard « Affectation des élèves aux classes » (Pré-rentrée) — sur le modèle du moteur EDT/Index
Éducation (voir la comparaison UnDeuxTemps/EDT/Charlemagne menée en amont) : une liste de critères
pondérés, chacun réglable en mode « Répartir » (dispersion, hétérogénéité recherchée) ou
« Regrouper » (concentration), plus des contraintes nominatives dures (StudentGroupingConstraint,
regrouper/séparer certains élèves). Même patron TransientModel + __actions__ à 3 étapes que
wizard_specialty_group_generation.py.

Portée v1 :
- Périmètre = tous les élèves dont le MEF appartient au RefGrade sélectionné (comme le wizard de
  spécialités), réaffectés parmi les Divisions déjà liées à ces MEF via MefDivision — ce wizard ne
  crée AUCUNE division, il suppose la structure de classes déjà posée (Pré-rentrée > MEF).
- 9 critères fixes (Sexe, Redoublant, Résultats scolaires, Assiduité, Comportement, Établissement
  d'origine, Ville, Ancienne classe, Projet d'accompagnement) — Âge et Options/spécialités sont
  volontairement exclus de cette première itération (les spécialités ont déjà leur propre wizard,
  orthogonal, sur Group/ClassPart plutôt que sur Division).
- Algorithme glouton (même famille que le bin-packing round-robin de la génération des groupes de
  spécialité) : traite d'abord les contraintes GROUP (fusionnées par union-find en « unités »),
  puis chaque unité restante dans l'ordre le plus contraint d'abord, en choisissant à chaque fois
  la division qui maximise un score pondéré (proportion d'élèves de même « case » de critère déjà
  présents, en plus ou en moins selon le mode). Ni solveur combinatoire global, ni verrouillage
  élève par élève post-calcul (chantier ultérieur, comme chez les trois logiciels comparés).
"""
from typing import Optional
from sqlalchemy.orm import Session
from backend.app.models.base import TransientModel, requires_access
from backend.app.models.ref_grade import RefGrade
from backend.app.models.mef import Mef, MefDivision
from backend.app.models.division import Division
from backend.app.models.student import Student
from backend.app.models.student_grouping_constraint import StudentGroupingConstraint, StudentGroupingConstraintType
from backend.app.core.html_text import esc


CRITERION_MODE_OPTIONS = [
    {"value": "ignore", "label": "Ignorer"},
    {"value": "spread_1", "label": "Répartir (poids faible)"},
    {"value": "spread_2", "label": "Répartir (poids moyen)"},
    {"value": "spread_3", "label": "Répartir (poids fort)"},
    {"value": "group_1", "label": "Regrouper (poids faible)"},
    {"value": "group_2", "label": "Regrouper (poids moyen)"},
    {"value": "group_3", "label": "Regrouper (poids fort)"},
]

# (clé du critère, libellé, valeur par défaut)
CRITERIA = [
    ("gender", "Sexe", "spread_2"),
    ("doublement", "Redoublant", "spread_2"),
    ("academic_score", "Résultats scolaires", "spread_2"),
    ("attendance_score", "Assiduité", "spread_2"),
    ("behavior_score", "Comportement", "spread_2"),
    ("last_year_school", "Établissement d'origine", "ignore"),
    ("criterion_city", "Ville", "ignore"),
    ("last_year_level", "Ancienne classe", "ignore"),
    ("accompaniment", "Projet d'accompagnement", "spread_1"),
]
CRITERIA_KEYS = [key for key, _, _ in CRITERIA]


def _decode_mode(raw: Optional[str]):
    """« ignore »/None -> None (critère inactif) ; « spread_2 »/« group_3 » -> (mode, poids)."""
    if not raw or raw == "ignore":
        return None
    mode, _, weight_str = raw.partition("_")
    try:
        weight = int(weight_str)
    except ValueError:
        weight = 1
    return (mode, weight)


def _score_band(value: Optional[int]) -> str:
    if value is None:
        return "non_evalue"
    if value <= 4:
        return "faible"
    if value <= 7:
        return "moyen"
    return "eleve"


def _student_buckets(student: Student) -> dict:
    """« Case » de chaque critère pour cet élève — valeur catégorielle comparable entre élèves,
    y compris pour les critères numériques (bandes faible/moyen/élevé)."""
    return {
        "gender": student.gender.value if student.gender else "NA",
        "doublement": "oui" if student.doublement else "non",
        "academic_score": _score_band(student.academic_score),
        "attendance_score": _score_band(student.attendance_score),
        "behavior_score": _score_band(student.behavior_score),
        "last_year_school": student.last_year_school_id or "NA",
        "criterion_city": student.criterion_city_id or "NA",
        "last_year_level": student.last_year_level or "NA",
        "accompaniment": "oui" if student.accompaniment_projects else "non",
    }


def _load_units_and_separations(db: Session, candidate_ids: set) -> tuple:
    """
    Fusionne les contraintes GROUP par union-find en « unités » d'élèves devant obligatoirement
    partager la même division, et construit l'adjacence des paires devant obligatoirement être
    séparées (contraintes SEPARATE). Une contrainte dont moins de 2 membres appartiennent au
    périmètre sélectionné est ignorée (avec avertissement si elle en perd au moins un).
    """
    parent = {sid: sid for sid in candidate_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    warnings = []
    separate_pairs = set()
    for constraint in db.query(StudentGroupingConstraint).all():
        member_ids = [s.id for s in constraint.students]
        in_pool = [mid for mid in member_ids if mid in candidate_ids]
        if len(in_pool) < 2:
            continue
        if len(in_pool) != len(member_ids):
            warnings.append(
                f"Contrainte « {constraint.name} » : seuls {len(in_pool)}/{len(member_ids)} élève(s) "
                f"appartiennent au niveau sélectionné, les autres sont ignorés."
            )
        if constraint.constraint_type == StudentGroupingConstraintType.GROUP:
            for other in in_pool[1:]:
                union(in_pool[0], other)
        else:
            for i in range(len(in_pool)):
                for j in range(i + 1, len(in_pool)):
                    separate_pairs.add(frozenset((in_pool[i], in_pool[j])))

    groups: dict[int, set] = {}
    for sid in candidate_ids:
        groups.setdefault(find(sid), set()).add(sid)

    separate_adjacency: dict[int, set] = {sid: set() for sid in candidate_ids}
    for pair in separate_pairs:
        a, b = tuple(pair)
        if find(a) == find(b):
            warnings.append(
                "Deux élèves sont à la fois dans une contrainte « à regrouper » et « à séparer » : "
                "la séparation est ignorée pour ce couple."
            )
            continue
        separate_adjacency[a].add(b)
        separate_adjacency[b].add(a)

    return list(groups.values()), separate_adjacency, warnings


def _compute_class_assignment_plan(db: Session, ref_grade_id: int, criteria_raw: dict) -> dict:
    """
    Calcule le plan d'affectation pour un RefGrade, sans rien écrire en base — utilisé à la fois
    par rpc_preview et rpc_generate, pour que l'aperçu et la génération restent rigoureusement
    cohérents (même calcul, jamais deux logiques qui pourraient diverger — voir
    wizard_specialty_group_generation.py, même principe).
    """
    if not ref_grade_id:
        raise ValueError("Veuillez sélectionner un niveau avant de prévisualiser.")
    ref_grade = db.get(RefGrade, ref_grade_id)
    if not ref_grade:
        raise ValueError("Niveau introuvable.")

    mef_divisions = db.query(MefDivision).join(Mef, MefDivision.mef_id == Mef.id).filter(Mef.ref_grade_id == ref_grade_id).all()
    division_ids = sorted({md.division_id for md in mef_divisions})
    if not division_ids:
        raise ValueError(
            "Aucune division n'est rattachée aux MEF de ce niveau. Configurez d'abord les classes "
            "et leurs effectifs prévisionnels (Pré-rentrée > MEF)."
        )
    target_divisions = [db.get(Division, did) for did in division_ids]

    capacity: dict[int, Optional[int]] = {}
    valid_divisions_for_mef: dict[int, set] = {}
    for did in division_ids:
        total = sum(md.forecast_student_count for md in mef_divisions if md.division_id == did)
        capacity[did] = total or None
    for md in mef_divisions:
        valid_divisions_for_mef.setdefault(md.mef_id, set()).add(md.division_id)

    students = db.query(Student).join(Mef, Student.mef_id == Mef.id).filter(Mef.ref_grade_id == ref_grade_id).all()
    if not students:
        raise ValueError("Aucun élève n'appartient à un MEF de ce niveau.")
    candidate_ids = {s.id for s in students}
    students_by_id = {s.id: s for s in students}
    student_buckets = {s.id: _student_buckets(s) for s in students}

    active_criteria = {}
    for key, _, _ in CRITERIA:
        decoded = _decode_mode(criteria_raw.get(f"{key}_mode"))
        if decoded is not None:
            active_criteria[key] = decoded

    raw_units, separate_adjacency, warnings = _load_units_and_separations(db, candidate_ids)

    # Une unité GROUP ne peut être affectée que si TOUS ses membres partagent au moins une
    # division valide pour leur propre MEF — sinon la contrainte est impossible à honorer sans
    # violer l'invariant MEF/Division (Student._check_student_mef_matches_division) : on la
    # rétrograde en unités individuelles plutôt que d'échouer tout le calcul.
    units = []
    for unit in raw_units:
        if len(unit) <= 1:
            units.append(unit)
            continue
        common = None
        for sid in unit:
            mef_valid = valid_divisions_for_mef.get(students_by_id[sid].mef_id, set())
            common = mef_valid if common is None else (common & mef_valid)
        if common:
            units.append(unit)
        else:
            warnings.append(
                f"Contrainte de regroupement impossible à satisfaire pour {len(unit)} élève(s) "
                f"(aucune division commune valide pour leurs MEF) — affectés individuellement."
            )
            units.extend({sid} for sid in unit)

    division_count = {did: 0 for did in division_ids}
    division_bucket_counts: dict[int, dict] = {did: {} for did in division_ids}
    assignments: dict[int, int] = {}

    def score_for(division_id: int, unit: set) -> float:
        total = 0.0
        count = division_count[division_id]
        bucket_counts = division_bucket_counts[division_id]
        for sid in unit:
            buckets = student_buckets[sid]
            for key, (mode, weight) in active_criteria.items():
                bucket_value = buckets[key]
                matching = bucket_counts.get(key, {}).get(bucket_value, 0)
                ratio = (matching / count) if count else 0.0
                total += weight * ratio if mode == "group" else -weight * ratio
        return total

    for unit in sorted(units, key=lambda u: (-len(u), min(u))):
        common_valid = None
        for sid in unit:
            mef_valid = valid_divisions_for_mef.get(students_by_id[sid].mef_id, set())
            common_valid = mef_valid if common_valid is None else (common_valid & mef_valid)
        eligible = [d for d in target_divisions if d.id in (common_valid or set())]
        if not eligible:
            # Ne devrait plus se produire pour une unité multi-élèves (voir rétrogradation
            # ci-dessus) ; filet de sécurité pour un singleton dont le MEF n'est lié à aucune
            # division de ce niveau (configuration Pré-rentrée incomplète).
            warnings.append(f"Élève {students_by_id[next(iter(unit))].display_name} : aucune division valide pour son MEF, ignoré.")
            continue

        forbidden = set()
        for sid in unit:
            for neighbor in separate_adjacency.get(sid, ()):
                if neighbor in assignments:
                    forbidden.add(assignments[neighbor])
        candidates = [d for d in eligible if d.id not in forbidden]
        if not candidates:
            warnings.append(f"Contrainte de séparation impossible à respecter pour {len(unit)} élève(s) — affectés malgré tout.")
            candidates = eligible

        under_capacity = [d for d in candidates if capacity[d.id] is None or division_count[d.id] + len(unit) <= capacity[d.id]]
        pool = under_capacity or candidates
        if not under_capacity:
            warnings.append(f"Effectif prévisionnel dépassé pour l'affectation de {len(unit)} élève(s) (aucune division sous capacité disponible).")

        best = max(pool, key=lambda d: (score_for(d.id, unit), -division_count[d.id], -d.id))
        for sid in unit:
            assignments[sid] = best.id
            division_count[best.id] += 1
            bucket_counts = division_bucket_counts[best.id]
            for key in active_criteria:
                bucket_value = student_buckets[sid][key]
                bucket_counts.setdefault(key, {})
                bucket_counts[key][bucket_value] = bucket_counts[key].get(bucket_value, 0) + 1

    return {
        "ref_grade": ref_grade,
        "target_divisions": target_divisions,
        "capacity": capacity,
        "assignments": assignments,
        "division_count": division_count,
        "students_by_id": students_by_id,
        "warnings": warnings,
    }


def _apply_class_assignment_plan(db: Session, plan: dict) -> dict:
    changed = 0
    for student_id, division_id in plan["assignments"].items():
        student = plan["students_by_id"][student_id]
        if student.division_id != division_id:
            student.update(db, {"division_id": division_id})
            changed += 1
    return {"assigned_count": len(plan["assignments"]), "changed_count": changed, "warnings": plan["warnings"]}


def _render_division_rows(plan: dict) -> list[dict]:
    rows = []
    for i, division in enumerate(sorted(plan["target_divisions"], key=lambda d: d.id)):
        capacity = plan["capacity"].get(division.id)
        rows.append({
            "id": i,
            "division_label": division.name,
            "capacity_label": str(capacity) if capacity is not None else "Illimité",
            "assigned_count": plan["division_count"].get(division.id, 0),
        })
    return rows


def _render_warnings_html(warnings: list) -> str:
    if not warnings:
        return "<p>Aucun avertissement.</p>"
    items = "".join(f"<li>{esc(w)}</li>" for w in warnings)
    return f"<p><strong>{len(warnings)} avertissement(s) :</strong></p><ul>{items}</ul>"


def _criteria_step_fields() -> list[dict]:
    return [{"key": f"{key}_mode", "label": label, "type": "select", "options": CRITERION_MODE_OPTIONS} for key, label, _ in CRITERIA]


def _criteria_rpc_params() -> dict:
    params = {f"{key}_mode": f"{key}_mode" for key, _, _ in CRITERIA}
    params["ref_grade_id"] = "ref_grade_id"
    return params


class WizardStudentClassAssignment(TransientModel):
    """Enregistrement singleton (id=1 fixe, pas de liste), voir ui.json."""
    __tablename__ = "wizard_student_class_assignments"
    _fields = ["id", "ref_grade_id", "info_html", *[f"{key}_mode" for key, _, _ in CRITERIA], "warnings_html", "division_rows", "result_html"]
    _field_info = {
        "ref_grade_id": {"label": "Niveau", "type": "select", "resource": "ref_grades"},
        "info_html": {"type": "html", "label": " ", "readOnly": True},
        "warnings_html": {"type": "html", "label": " ", "readOnly": True},
        "division_rows": {
            "label": "Répartition par classe", "type": "text", "widget": "list_preview", "readOnly": True,
        },
        "result_html": {"type": "html", "label": " ", "readOnly": True},
    }
    _field_info.update({f"{key}_mode": {"label": label, "type": "select", "options": CRITERION_MODE_OPTIONS} for key, label, _ in CRITERIA})
    __actions__ = [{
        "id": "assign_students_to_classes",
        "label": "Affectation des élèves aux classes",
        "type": "wizard",
        "steps": [
            {
                "id": "select",
                "title": "1. Niveau et critères de répartition",
                "fields": [
                    {"key": "info_html", "type": "html", "label": " "},
                    {"key": "ref_grade_id", "label": "Niveau", "type": "select", "resource": "ref_grades"},
                    *_criteria_step_fields(),
                ],
                "submitLabel": "Prévisualiser",
                "rpc": "rpc_preview",
                "rpcParams": _criteria_rpc_params(),
            },
            {
                "id": "review",
                "title": "2. Aperçu",
                "fields": [
                    {"key": "warnings_html", "type": "html", "label": " "},
                    {
                        "key": "division_rows", "label": "Répartition par classe", "type": "text",
                        "widget": "list_preview", "fullWidth": True,
                        "widgetParams": {
                            "columns": [
                                {"key": "division_label", "label": "Classe", "width": 160},
                                {"key": "assigned_count", "label": "Élèves affectés", "width": 120},
                                {"key": "capacity_label", "label": "Effectif prévu", "width": 120},
                            ],
                            "listConfig": {"editableInline": False, "disableAdd": True, "disableDelete": True, "allowMultiSelect": False},
                        },
                    },
                ],
                "submitLabel": "Générer",
                "rpc": "rpc_generate",
                "rpcParams": _criteria_rpc_params(),
            },
            {
                "id": "result",
                "title": "3. Résultat",
                "isLast": True,
                "fields": [{"key": "result_html", "type": "html", "label": " "}],
                "submitLabel": "Fermer",
            },
        ],
    }]

    def __init__(self, id, ref_grade_id=None, info_html=None, warnings_html=None, division_rows=None, result_html=None, **criteria_modes):
        self.id = id
        self.ref_grade_id = ref_grade_id
        self.info_html = info_html
        self.warnings_html = warnings_html
        self.division_rows = division_rows or []
        self.result_html = result_html
        for key, _, default in CRITERIA:
            setattr(self, f"{key}_mode", criteria_modes.get(f"{key}_mode", default))

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        html = (
            "<p>Sélectionnez le niveau à répartir et réglez, pour chaque critère, le mode "
            "« Répartir » (hétérogénéité recherchée entre les classes) ou « Regrouper » "
            "(élèves de même profil concentrés), avec son importance relative. Les contraintes "
            "nominatives « à regrouper »/« à séparer » (menu Pré-rentrée) sont toujours "
            "respectées en priorité.</p>"
        )
        return [cls(id=1, info_html=html)]

    def _criteria_from_kwargs(self, kwargs: dict) -> dict:
        return {f"{key}_mode": kwargs.get(f"{key}_mode") for key, _, _ in CRITERIA}

    @requires_access("write")
    def rpc_preview(self, db: Session, ref_grade_id: int, **kwargs) -> dict:
        """Dry-run : ne modifie rien en base (voir _compute_class_assignment_plan)."""
        plan = _compute_class_assignment_plan(db, ref_grade_id, self._criteria_from_kwargs(kwargs))
        return {
            "warnings_html": _render_warnings_html(plan["warnings"]),
            "division_rows": _render_division_rows(plan),
        }

    @requires_access("write")
    def rpc_generate(self, db: Session, ref_grade_id: int, **kwargs) -> dict:
        plan = _compute_class_assignment_plan(db, ref_grade_id, self._criteria_from_kwargs(kwargs))
        result = _apply_class_assignment_plan(db, plan)
        html = f"<p><strong>{result['changed_count']}</strong> élève(s) réaffecté(s) sur {result['assigned_count']} affecté(s) au total.</p>"
        if result["warnings"]:
            html += _render_warnings_html(result["warnings"])
        return {"result_html": html, "mutated_resources": ["students", "divisions", "mef_divisions"]}
