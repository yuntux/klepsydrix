"""
Génération en masse des Course à partir de la répartition Service/ServiceRepartition/Alignment
saisie en Pré-rentrée. Convention de nommage : tout modèle de wizard (TransientModel + logique
métier associée) est préfixé wizard_ (voir architecture.md), regroupé dans un seul fichier plutôt
que scindé logique/modèle.
"""
from typing import Optional
from sqlalchemy.orm import Session
from backend.app.models.base import TransientModel, requires_access
from backend.app.models.course import Course
from backend.app.models.division import Division
from backend.app.models.subject import Subject
from backend.app.models.service import Service, Alignment, RepartitionGroupType, RepartitionPeriodicity
from backend.app.models.group import find_or_create_partition, find_or_create_group, PartitionSpecialType


def _dedup_ids(ids) -> list:
    seen = set()
    ordered = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            ordered.append(i)
    return ordered


def _week_type_for(periodicity) -> str:
    return "W" if periodicity == RepartitionPeriodicity.WEEKLY else "Q"


def _courses_from_alignment(db: Session, alignment: Alignment) -> list[dict]:
    """
    Un Course composé par occurrence de répartition, agrégeant les ressources de tous les
    services alignés liés à une Division (un service lié à un Group est exclu de l'agrégation,
    non géré pour l'instant) — sans class_part_ids/group_ids, gérés lors de la décomposition
    manuelle (voir Alignment, docstring).
    """
    division_services = [s for s in alignment.services if s.group_id is None]
    if not division_services:
        return []

    teacher_ids = _dedup_ids(t.id for s in division_services for t in s.teachers)
    division_ids = _dedup_ids(s.division_id for s in division_services if s.division_id is not None)
    subject_ids = {s.subject_id for s in division_services}
    subject_id = next(iter(subject_ids)) if len(subject_ids) == 1 else None

    school_id = None
    if division_ids:
        division = db.get(Division, division_ids[0])
        school_id = division.school_id if division else None
    if school_id is None:
        return []

    template_service = division_services[0]
    vals_list = []
    for repartition in template_service.repartitions:
        # occurrence_count (séances/élève/semaine) x group_count (groupes parallèles) = nombre
        # réel de Course à générer, depuis leur séparation (plan Volet B) — group_count vaut 1
        # pour un Alignment composé de services FULL_CLASS/SPLIT non REDUCED (voir _repartition_signature).
        for _ in range(repartition.occurrence_count * repartition.group_count):
            vals_list.append({
                "school_id": school_id,
                "subject_id": subject_id,
                "is_composed": True,
                "teacher_ids": teacher_ids,
                "division_ids": division_ids,
                "duration_minutes": repartition.duration_minutes,
                "week_type": _week_type_for(repartition.periodicity),
                "weighting_coefficient_id": template_service.weighting_coefficient_id,
                "is_excluded_from_sts": template_service.is_excluded_from_sts,
            })
    return vals_list


def _school_id_for_group(db: Session, group_id: int) -> Optional[int]:
    """
    school_id d'un Group : dérivé de la Division de n'importe laquelle de ses ClassPart (un Group
    de spécialité peut couvrir plusieurs divisions, mais toutes appartiennent au même
    établissement — voir wizard_specialty_group_generation.py).
    """
    from backend.app.models.group import Group
    group = db.get(Group, group_id)
    if not group or not group.class_parts:
        return None
    partition = group.class_parts[0].partition
    division = partition.division if partition else None
    return division.school_id if division else None


def _courses_from_group_service(db: Session, service: Service) -> list[dict]:
    """
    Cours simples issus d'un Service non aligné directement lié à un Group déjà constitué (cas
    des groupes de spécialité, voir wizard_specialty_group_generation.py) — la population est
    déjà figée par le Group, aucune dérivation de partition/sous-groupe supplémentaire ici
    (contrairement à _courses_from_service, dont le Group est dérivé d'une Division source).
    """
    school_id = _school_id_for_group(db, service.group_id)
    if school_id is None:
        return []

    teacher_ids = [t.id for t in service.teachers]
    is_co_teaching = len(teacher_ids) > 1

    vals_list = []
    for repartition in service.repartitions:
        if repartition.group_type != RepartitionGroupType.FULL_CLASS:
            raise ValueError(
                "Un Service directement lié à un Group ne peut porter que des répartitions de type "
                "Classe entière (FULL_CLASS) : le Group représente déjà la population cible, un "
                "dédoublement/effectif réduit supplémentaire n'est pas géré."
            )
        base_vals = {
            "school_id": school_id,
            "subject_id": service.subject_id,
            "teacher_ids": teacher_ids,
            "is_co_teaching": is_co_teaching,
            "duration_minutes": repartition.duration_minutes,
            "week_type": _week_type_for(repartition.periodicity),
            "weighting_coefficient_id": service.weighting_coefficient_id,
            "is_excluded_from_sts": service.is_excluded_from_sts,
            "group_ids": [service.group_id],
        }
        for _ in range(repartition.occurrence_count):
            vals_list.append(dict(base_vals))
    return vals_list


def _courses_from_service(db: Session, service: Service) -> list[dict]:
    """Cours simples issus d'un Service non aligné et lié à une Division (voir group_type)."""
    if service.group_id is not None:
        return _courses_from_group_service(db, service)

    school_id = None
    division = db.get(Division, service.division_id) if service.division_id else None
    if division:
        school_id = division.school_id
    if school_id is None:
        return []

    teacher_ids = [t.id for t in service.teachers]
    is_co_teaching = len(teacher_ids) > 1

    vals_list = []
    for repartition in service.repartitions:
        base_vals = {
            "school_id": school_id,
            "subject_id": service.subject_id,
            "teacher_ids": teacher_ids,
            "is_co_teaching": is_co_teaching,
            "duration_minutes": repartition.duration_minutes,
            "week_type": _week_type_for(repartition.periodicity),
            "weighting_coefficient_id": service.weighting_coefficient_id,
            "is_excluded_from_sts": service.is_excluded_from_sts,
        }

        if repartition.group_type == RepartitionGroupType.FULL_CLASS:
            for _ in range(repartition.occurrence_count):
                vals_list.append({**base_vals, "division_ids": [service.division_id]})
            continue

        # SPLIT/REDUCED : groups_need vient directement de group_count (calculé et stocké, voir
        # ServiceRepartition/_sync_reduced_pool) — plus de validation de divisibilité, occurrence_count
        # et group_count varient désormais indépendamment (plan Volet B).
        groups_need = repartition.group_count
        if repartition.group_type == RepartitionGroupType.SPLIT:
            partition = find_or_create_partition(db, service.division_id, "", special_type=PartitionSpecialType.HALF_ALPHA)
        elif repartition.group_type == RepartitionGroupType.REDUCED:
            subject = db.get(Subject, service.subject_id)
            partition = find_or_create_partition(db, service.division_id, subject.name if subject else "", part_count=groups_need)
        else:
            raise ValueError(f"Type de répartition non géré : {repartition.group_type}")

        group_pool = [find_or_create_group(db, [cp.id], service.subject_id) for cp in partition.class_parts]
        for i in range(repartition.occurrence_count * groups_need):
            vals_list.append({**base_vals, "group_ids": [group_pool[i % groups_need].id]})

    return vals_list


def generate_courses_from_services(db: Session) -> dict:
    """
    Point d'entrée : supprime tous les Course existants puis régénère l'intégralité à partir des
    Alignment et des Service non alignés (voir _courses_from_alignment/_courses_from_service).
    """
    # Compte TOUS les Course (top-level + enfants) — même métrique que WizardCourseGeneration.read()
    # (info_html), pour que "N cours existants seront supprimés" et "N supprimés" coïncident. La
    # boucle de suppression elle-même ne parcourt que les cours de haut niveau : supprimer un
    # parent cascade déjà vers ses enfants (FK ondelete=CASCADE), qu'il ne faut donc pas supprimer
    # une seconde fois individuellement.
    deleted_count = db.query(Course).count()
    for course in db.query(Course).filter(Course.parent_id.is_(None)).all():
        course.delete(db)

    vals_list = []
    for alignment in db.query(Alignment).all():
        vals_list.extend(_courses_from_alignment(db, alignment))
    for service in db.query(Service).filter(Service.alignment_id.is_(None)).all():
        vals_list.extend(_courses_from_service(db, service))

    for vals in vals_list:
        Course.create(db, vals)

    return {"generated_count": len(vals_list), "deleted_count": deleted_count}


class WizardCourseGeneration(TransientModel):
    """
    Wizard (voir __actions__) qui régénère tous les Course à partir de la répartition des
    services — enregistrement singleton (id=1 fixe, pas de liste), voir ui.json.
    """
    __tablename__ = "wizard_course_generations"
    _fields = ["id", "info_html"]
    # Label non vide (espace) : un label "" retombe sur la clé du champ comme libellé affiché
    # (App.vue, `prop.title || key` — "" est falsy en JS), ce qu'on veut justement éviter pour un
    # simple bloc de texte formaté qui n'a pas besoin d'étiquette.
    _field_info = {"info_html": {"type": "html", "label": " ", "readOnly": True}}
    __actions__ = [{
        "id": "generate_courses",
        "label": "Générer les cours",
        "type": "wizard",
        "steps": [
            {
                "id": "confirm",
                "title": "Confirmation",
                "fields": [{"key": "info_html", "type": "html", "label": " "}],
                "submitLabel": "Générer les cours",
                "rpc": "rpc_generate_courses",
            },
            {
                "id": "result",
                "title": "Résultat",
                "isLast": True,
                "fields": [{"key": "result_html", "type": "html", "label": " "}],
                "submitLabel": "Fermer",
            },
        ],
    }]

    def __init__(self, id, info_html):
        self.id = id
        self.info_html = info_html

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        count = db.query(Course).count()
        html = "<p>Les cours vont être générés à partir de la répartition des services.</p>"
        if count > 0:
            html += f"<p><strong>{count} cours existant(s) seront supprimés.</strong></p>"
        return [cls(id=1, info_html=html)]

    @requires_access("write")
    def rpc_generate_courses(self, db: Session) -> dict:
        result = generate_courses_from_services(db)
        html = f"<p><strong>{result['generated_count']} cours générés</strong> ({result['deleted_count']} supprimés).</p>"
        # mutated_resources : lu par GenericWizard.vue à la fermeture pour rafraîchir le cache
        # navigateur des Course (ex: le visualiseur emploi du temps affiché derrière la popin) —
        # la ressource propre du wizard (wizard_course_generations) n'est pas ce qui a réellement
        # été modifié en base.
        return {"result_html": html, "mutated_resources": ["courses"]}
