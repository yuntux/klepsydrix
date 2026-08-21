"""
Wizard « Générer les groupes de spécialité » (réforme du lycée) — trois étapes (sélection /
aperçu / résultat), même patron que wizard_teacher_assignment.py (TransientModel + __actions__).

Portée v1 (mode « minimisant les liens », voir architecture.md §21.A) : aucun
Alignment n'est précalculé — chaque Service de spécialité est posé directement sur un Group
(cross-division), et la non-collision entre spécialités choisies par un même élève repose
entièrement sur le mécanisme générique déjà en place (ClassPartLink auto-généré entre partitions
d'une même division, group_link_conflict côté solveur). Le mode « alignements » (barrette
précalculée) est un chantier ultérieur distinct.

Limite connue de cette première itération : un ré-exécution du wizard après un changement
d'effectif peut faire migrer un élève d'un groupe à un autre — le retrait de l'ancien ClassPart
est fait explicitement (voir _apply_specialty_plan, passe de nettoyage avant la passe
d'affectation) mais aucune détection de dérive fine (états Fait/Partiel/Reconstruire) n'est
construite ici.
"""
import math
from sqlalchemy.orm import Session
from backend.app.models.base import TransientModel, requires_access
from backend.app.models.ref_grade import RefGrade
from backend.app.models.student import Student, StudentSpecialtyChoice
from backend.app.models.specialty_group_config import SpecialtyGroupConfig
from backend.app.models.subject import Subject
from backend.app.models.mef import Mef, MefService
from backend.app.models.group import (
    Partition, find_or_create_group,
    _find_or_create_specialty_partition, _ensure_specialty_class_parts,
)
from backend.app.models.service import Service


def _compute_specialty_plan(db: Session, ref_grade_id: int) -> dict:
    """
    Calcule le plan de génération pour un RefGrade, sans rien écrire en base — utilisé à la fois
    par rpc_preview (affichage) et rpc_generate (exécution), pour que l'aperçu et la génération
    restent rigoureusement cohérents (même calcul, jamais deux logiques qui pourraient diverger).
    """
    ref_grade = db.get(RefGrade, ref_grade_id)
    if not ref_grade or not ref_grade.specialty_choice_limit:
        raise ValueError(
            "Ce niveau n'est pas configuré pour les enseignements de spécialité "
            "(le champ 'Plafond de vœux de spécialité' du niveau n'est pas défini)."
        )

    students = db.query(Student).join(Mef, Student.mef_id == Mef.id).filter(Mef.ref_grade_id == ref_grade_id).all()

    parcours_by_student: dict[int, tuple] = {}
    subject_students: dict[int, list[Student]] = {}
    for student in students:
        choices = sorted(student.specialty_choices, key=lambda c: c.rank)
        subject_ids = tuple(c.subject_id for c in choices)
        if not subject_ids:
            continue
        parcours_by_student[student.id] = subject_ids
        for subject_id in subject_ids:
            subject_students.setdefault(subject_id, []).append(student)

    parcours_counts: dict[tuple, int] = {}
    for subject_ids in parcours_by_student.values():
        parcours_counts[subject_ids] = parcours_counts.get(subject_ids, 0) + 1

    subject_bins: dict[int, list[list[Student]]] = {}
    warnings: list[str] = []
    for subject_id, subj_students in subject_students.items():
        subject = db.get(Subject, subject_id)
        subject_label = subject.name if subject else str(subject_id)

        config = db.query(SpecialtyGroupConfig).filter(
            SpecialtyGroupConfig.subject_id == subject_id,
            SpecialtyGroupConfig.ref_grade_id == ref_grade_id,
        ).first()
        if not config:
            warnings.append(f"Aucun seuil configuré pour « {subject_label} » à ce niveau — matière ignorée.")
            continue

        groups_needed = math.ceil(len(subj_students) / config.max_students_per_group)
        if config.max_groups_count and groups_needed > config.max_groups_count:
            warnings.append(
                f"« {subject_label} » : {len(subj_students)} élève(s) nécessitent {groups_needed} "
                f"groupe(s), plafonnés à {config.max_groups_count} — le seuil groupe sera dépassé."
            )
            groups_needed = config.max_groups_count

        # Glouton simple (round-robin) — mode « minimisant les liens » : aucune tentative de
        # corréler les groupes d'un élève entre ses différentes spécialités, la non-collision est
        # déléguée au ClassPartLink générique + au solveur (voir docstring de module).
        bins = [[] for _ in range(groups_needed)]
        for i, student in enumerate(subj_students):
            bins[i % groups_needed].append(student)
        subject_bins[subject_id] = bins

    return {
        "ref_grade": ref_grade,
        "parcours_counts": parcours_counts,
        "subject_bins": subject_bins,
        "warnings": warnings,
    }


def _find_or_create_mef_service(db: Session, mef_id: int, subject: Subject, ref_grade: RefGrade) -> MefService:
    """
    Recherché par (mef_id, subject_id) — réutilisé tel quel s'il existe (jamais écrasé, un
    ajustement manuel du volume doit survivre à une réexécution du wizard), créé seulement s'il
    est absent. Volume par défaut dérivé du référentiel officiel : 6h en Première (plafond de vœux
    = 3), 4h en Terminale (plafond = 2) — faute d'un champ dédié, cette corrélation officielle sert
    de repli ; le volume reste éditable ensuite comme n'importe quel MefService.
    """
    existing = db.query(MefService).filter(MefService.mef_id == mef_id, MefService.subject_id == subject.id).first()
    if existing:
        return existing
    default_minutes = 360 if ref_grade.specialty_choice_limit == 3 else 240
    return MefService.create(db, {
        "mef_id": mef_id, "subject_id": subject.id, "discipline_id": subject.discipline_id,
        "weekly_duration_full_class_minutes": default_minutes,
    })


def _apply_specialty_plan(db: Session, plan: dict) -> dict:
    ref_grade = plan["ref_grade"]
    created_groups = 0
    created_services = 0
    mef_mismatch_warnings: list[str] = []

    for subject_id, bins in plan["subject_bins"].items():
        subject = db.get(Subject, subject_id)

        # Passe de nettoyage : retire d'abord tous les élèves concernés par CETTE matière de
        # toutes les ClassPart déjà existantes de leur partition de spécialité respective — évite
        # qu'un élève ayant changé de bin depuis un précédent lancement se retrouve transitoirement
        # dans deux ClassPart de la même Partition (interdit par Student._check_student_class_parts).
        all_students = [s for bucket in bins for s in bucket]
        divisions_touched = {s.division_id for s in all_students}
        for division_id in divisions_touched:
            partition = db.query(Partition).filter(
                Partition.division_id == division_id, Partition.code == f"SPEC_{subject.code}"
            ).first()
            if not partition:
                continue
            for class_part in partition.class_parts:
                stale_ids = {s.id for s in class_part.students} & {s.id for s in all_students}
                if stale_ids:
                    keep_ids = [s.id for s in class_part.students if s.id not in stale_ids]
                    class_part.update(db, {"student_ids": keep_ids})

        for bin_index, bin_students in enumerate(bins):
            if not bin_students:
                continue

            students_by_division: dict[int, list[Student]] = {}
            for student in bin_students:
                students_by_division.setdefault(student.division_id, []).append(student)

            class_part_ids = []
            for division_id, div_students in students_by_division.items():
                partition = _find_or_create_specialty_partition(db, division_id, subject)
                parts = _ensure_specialty_class_parts(db, partition, subject, len(bins))
                class_part = parts[bin_index]
                class_part.update(db, {"student_ids": [s.id for s in div_students]})
                class_part_ids.append(class_part.id)

            group = find_or_create_group(db, class_part_ids, subject_id)
            created_groups += 1

            # MEF dominant du bin : un groupe de spécialité mélange en pratique un seul MEF par
            # niveau (les autres cas, ex: mutualisation avec un MEF SEGPA du même RefGrade, sont
            # rares) — pris comme MEF porteur du Service pour éviter de générer deux Service sur le
            # même Group (ce que _courses_from_group_service ne sait pas dédupliquer).
            mef_counts: dict[int, int] = {}
            for s in bin_students:
                mef_counts[s.mef_id] = mef_counts.get(s.mef_id, 0) + 1
            dominant_mef_id = max(mef_counts, key=mef_counts.get)
            if len(mef_counts) > 1:
                mef_mismatch_warnings.append(
                    f"« {subject.name} » groupe {bin_index + 1} : élèves de {len(mef_counts)} MEF différents, "
                    f"rattaché au MEF majoritaire uniquement."
                )

            mef_service = _find_or_create_mef_service(db, dominant_mef_id, subject, ref_grade)
            vals = {"mef_service_id": mef_service.id, "group_id": group.id, "student_count": len(bin_students)}
            for field in Service._MEF_SERVICE_MIRROR_FIELDS:
                vals[field] = getattr(mef_service, field)
            Service.create(db, vals)
            created_services += 1

    return {
        "created_groups": created_groups,
        "created_services": created_services,
        "warnings": plan["warnings"] + mef_mismatch_warnings,
    }


def _render_parcours_rows(plan: dict, db: Session) -> list[dict]:
    rows = []
    for i, (subject_ids, count) in enumerate(sorted(plan["parcours_counts"].items(), key=lambda kv: -kv[1])):
        labels = []
        for subject_id in subject_ids:
            subject = db.get(Subject, subject_id)
            labels.append(subject.short_name if subject else str(subject_id))
        rows.append({"id": i, "combo_label": " + ".join(labels), "student_count": count})
    return rows


def _render_groups_rows(plan: dict, db: Session) -> list[dict]:
    rows = []
    for i, (subject_id, bins) in enumerate(plan["subject_bins"].items()):
        subject = db.get(Subject, subject_id)
        total_students = sum(len(b) for b in bins)
        rows.append({
            "id": i,
            "subject_label": subject.name if subject else str(subject_id),
            "student_count": total_students,
            "groups_needed": len(bins),
        })
    return rows


def _render_warnings_html(warnings: list[str]) -> str:
    if not warnings:
        return "<p>Aucun avertissement.</p>"
    items = "".join(f"<li>{w}</li>" for w in warnings)
    return f"<p><strong>{len(warnings)} avertissement(s) :</strong></p><ul>{items}</ul>"


class WizardSpecialtyGroupGeneration(TransientModel):
    """Enregistrement singleton (id=1 fixe, pas de liste), voir ui.json."""
    __tablename__ = "wizard_specialty_group_generations"
    _fields = ["id", "ref_grade_id", "info_html", "warnings_html", "parcours_rows", "groups_rows", "result_html"]
    _field_info = {
        "ref_grade_id": {"label": "Niveau", "type": "select", "resource": "ref_grades"},
        "info_html": {"type": "html", "label": " ", "readOnly": True},
        "warnings_html": {"type": "html", "label": " ", "readOnly": True},
        "parcours_rows": {"label": "Parcours", "type": "text", "widget": "list_preview", "readOnly": True},
        "groups_rows": {"label": "Groupes à générer", "type": "text", "widget": "list_preview", "readOnly": True},
        "result_html": {"type": "html", "label": " ", "readOnly": True},
    }
    __actions__ = [{
        "id": "generate_specialty_groups",
        "label": "Générer les groupes de spécialité",
        "type": "wizard",
        "steps": [
            {
                "id": "select",
                "title": "1. Sélection du niveau",
                "fields": [
                    {"key": "info_html", "type": "html", "label": " "},
                    {"key": "ref_grade_id", "label": "Niveau", "type": "select", "resource": "ref_grades"},
                ],
                "submitLabel": "Prévisualiser",
                "rpc": "rpc_preview",
                "rpcParams": {"ref_grade_id": "ref_grade_id"},
            },
            {
                "id": "review",
                "title": "2. Aperçu",
                "fields": [
                    {"key": "warnings_html", "type": "html", "label": " "},
                    {
                        "key": "parcours_rows", "label": "Parcours (combinaisons de spécialités)", "type": "text",
                        "widget": "list_preview", "fullWidth": True,
                        "widgetParams": {
                            "columns": [
                                {"key": "combo_label", "label": "Parcours", "width": 260},
                                {"key": "student_count", "label": "Élèves", "width": 90},
                            ],
                            "listConfig": {"editableInline": False, "disableAdd": True, "disableDelete": True, "allowMultiSelect": False},
                        },
                    },
                    {
                        "key": "groups_rows", "label": "Groupes à générer", "type": "text",
                        "widget": "list_preview", "fullWidth": True,
                        "widgetParams": {
                            "columns": [
                                {"key": "subject_label", "label": "Spécialité", "width": 200},
                                {"key": "student_count", "label": "Élèves", "width": 90},
                                {"key": "groups_needed", "label": "Groupes nécessaires", "width": 140},
                            ],
                            "listConfig": {"editableInline": False, "disableAdd": True, "disableDelete": True, "allowMultiSelect": False},
                        },
                    },
                ],
                "submitLabel": "Générer",
                "rpc": "rpc_generate",
                "rpcParams": {"ref_grade_id": "ref_grade_id"},
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

    def __init__(self, id, ref_grade_id=None, info_html=None, warnings_html=None, parcours_rows=None, groups_rows=None, result_html=None):
        self.id = id
        self.ref_grade_id = ref_grade_id
        self.info_html = info_html
        self.warnings_html = warnings_html
        self.parcours_rows = parcours_rows or []
        self.groups_rows = groups_rows or []
        self.result_html = result_html

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        html = (
            "<p>Sélectionnez le niveau (Première/Terminale) pour lequel générer les groupes de "
            "spécialité à partir des vœux saisis sur chaque élève.</p>"
        )
        return [cls(id=1, info_html=html)]

    @requires_access("write")
    def rpc_preview(self, db: Session, ref_grade_id: int) -> dict:
        """Dry-run : ne modifie rien en base (voir _compute_specialty_plan)."""
        plan = _compute_specialty_plan(db, ref_grade_id)
        return {
            "warnings_html": _render_warnings_html(plan["warnings"]),
            "parcours_rows": _render_parcours_rows(plan, db),
            "groups_rows": _render_groups_rows(plan, db),
        }

    @requires_access("write")
    def rpc_generate(self, db: Session, ref_grade_id: int) -> dict:
        plan = _compute_specialty_plan(db, ref_grade_id)
        result = _apply_specialty_plan(db, plan)
        html = (
            f"<p><strong>{result['created_groups']} groupe(s)</strong> et "
            f"<strong>{result['created_services']} service(s)</strong> générés.</p>"
        )
        if result["warnings"]:
            html += _render_warnings_html(result["warnings"])
        # mutated_resources : voir wizard_course_generation.py::rpc_generate_courses (même
        # remarque) — rafraîchit le cache navigateur des ressources réellement modifiées.
        return {"result_html": html, "mutated_resources": ["groups", "services", "partitions", "class_parts", "mef_services"]}
