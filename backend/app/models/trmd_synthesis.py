from typing import Optional
from sqlalchemy.orm import Session
from backend.app.models.base import TransientModel


def _dedup_shared_reduced_repartitions(rows: list) -> list:
    """
    Dédoublonne les ServiceRepartition de type REDUCED partagées entre plusieurs divisions
    (voir ServiceRepartition.shared_divisions, Service._sync_reduced_pool) avant de sommer leur
    besoin en heures — sans quoi un même besoin mutualisé serait compté une fois par division
    participante. Fait ici (agrégation par discipline), pas dans un champ MefService.repartition_ids
    : le partage n'est pas restreint à un même MefService (deux gabarits différents du même MEF
    peuvent mutualiser un groupe réduit), un dédoublonnage local à un MefService verrait donc
    au mieux la moitié du partage.

    Règle : pour toute ligne REDUCED dont shared_divisions est non vide, ne garder que celle dont
    la division est l'id minimal parmi {division propre} ∪ {shared_divisions} — déterministe,
    sans champ supplémentaire à synchroniser.
    """
    from backend.app.models.service import RepartitionGroupType

    kept = []
    for r in rows:
        if r.group_type == RepartitionGroupType.REDUCED and r.shared_divisions:
            pool_division_ids = {d.id for d in r.shared_divisions}
            if r.service and r.service.division_id is not None:
                pool_division_ids.add(r.service.division_id)
            if pool_division_ids and r.service and r.service.division_id != min(pool_division_ids):
                continue
        kept.append(r)
    return kept


class TrmdLine(TransientModel):
    """
    Modèle virtuel (transitoire) calculé pour la synthèse TRMD (Tableau de Répartition des Moyens
    par Discipline) : une ligne par Discipline, comparant le besoin théorique en heures
    d'enseignement (issu de MefService/Service/ServiceRepartition, voir architecture.md/plan Volet
    B) aux moyens humains réellement affectés (Teacher, définitifs et temporaires).
    """
    __tablename__ = "trmd_syntheses"

    _fields = [
        "id", "discipline_id", "need_ids", "def_teacher_ids", "temp_teacher_ids",
        "need_raw_duration_minutes", "need_weighted_duration_minutes", "are_duration_minutes",
        "total_needs", "def_teacher_count", "def_teached_duration_minutes",
        "def_given_duration_minutes", "def_gap_duration_minutes", "temp_teacher_count",
        "temp_teached_duration_minutes", "temp_given_duration_minutes",
        "total_ressource_duration_minutes", "total_gap_duration_minutes",
        "total_hsa_duration_minutes", "imp_duration_minutes",
    ]
    # "type" explicite sur CHAQUE champ, sans exception : contrairement à un modèle SQLAlchemy réel
    # (dont le type Python de chaque colonne est auto-inféré par make_pydantic_model, voir
    # generic.py), un TransientModel n'a que des noms de champs dans _fields — aucune introspection
    # de type possible, tout champ non explicitement typé ici reste Optional[Any] côté schéma.
    _field_info = {
        "discipline_id": {"label": "Discipline", "resource": "disciplines", "type": "select", "readOnly": True},
        "need_ids": {"label": "Besoins", "resource": "service_repartitions", "type": "multiselect", "readOnly": True, "widget": "relation_browser"},
        "def_teacher_ids": {"label": "Moyens définitifs", "resource": "teachers", "type": "multiselect", "readOnly": True, "widget": "relation_browser"},
        "temp_teacher_ids": {"label": "Moyens provisoires", "resource": "teachers", "type": "multiselect", "readOnly": True, "widget": "relation_browser"},
        "need_raw_duration_minutes": {"label": "Heures enseignées (besoin brut)", "type": "number", "readOnly": True},
        "need_weighted_duration_minutes": {"label": "Heures pondérées (besoin)", "type": "number", "readOnly": True},
        "are_duration_minutes": {"label": "ARE", "type": "number", "readOnly": True},
        "total_needs": {"label": "Besoins totaux", "type": "number", "readOnly": True},
        "def_teacher_count": {"label": "Nb postes déf.", "type": "number", "readOnly": True},
        "def_teached_duration_minutes": {"label": "H. enseignées déf.", "type": "number", "readOnly": True},
        "def_given_duration_minutes": {"label": "Heures données à un autre établissement déf.", "type": "number", "readOnly": True},
        "def_gap_duration_minutes": {"label": "Écart ressources déf. - besoins déf.", "type": "number", "readOnly": True},
        "temp_teacher_count": {"label": "Nb postes temp.", "type": "number", "readOnly": True},
        "temp_teached_duration_minutes": {"label": "H. enseignées temp.", "type": "number", "readOnly": True},
        "temp_given_duration_minutes": {"label": "Heures données à un autre établissement temp.", "type": "number", "readOnly": True},
        "total_ressource_duration_minutes": {"label": "Moyens totaux", "type": "number", "readOnly": True},
        "total_gap_duration_minutes": {"label": "Ressource > besoin", "type": "number", "readOnly": True},
        "total_hsa_duration_minutes": {"label": "HSA (Ressource < besoin)", "type": "number", "readOnly": True},
        "imp_duration_minutes": {"label": "IMP", "type": "number", "readOnly": True},
    }

    def __init__(self, id, discipline_id, need_ids, def_teacher_ids, temp_teacher_ids,
                 need_raw_duration_minutes, need_weighted_duration_minutes, are_duration_minutes,
                 total_needs, def_teacher_count, def_teached_duration_minutes,
                 def_given_duration_minutes, def_gap_duration_minutes, temp_teacher_count,
                 temp_teached_duration_minutes, temp_given_duration_minutes,
                 total_ressource_duration_minutes, total_gap_duration_minutes,
                 total_hsa_duration_minutes, imp_duration_minutes):
        self.id = id
        self.discipline_id = discipline_id
        self.need_ids = need_ids
        self.def_teacher_ids = def_teacher_ids
        self.temp_teacher_ids = temp_teacher_ids
        self.need_raw_duration_minutes = need_raw_duration_minutes
        self.need_weighted_duration_minutes = need_weighted_duration_minutes
        self.are_duration_minutes = are_duration_minutes
        self.total_needs = total_needs
        self.def_teacher_count = def_teacher_count
        self.def_teached_duration_minutes = def_teached_duration_minutes
        self.def_given_duration_minutes = def_given_duration_minutes
        self.def_gap_duration_minutes = def_gap_duration_minutes
        self.temp_teacher_count = temp_teacher_count
        self.temp_teached_duration_minutes = temp_teached_duration_minutes
        self.temp_given_duration_minutes = temp_given_duration_minutes
        self.total_ressource_duration_minutes = total_ressource_duration_minutes
        self.total_gap_duration_minutes = total_gap_duration_minutes
        self.total_hsa_duration_minutes = total_hsa_duration_minutes
        self.imp_duration_minutes = imp_duration_minutes

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        """
        Une ligne par Discipline (pas de filtre par école pour cette itération, voir plan Volet E).
        Pour chaque discipline : les besoins viennent des ServiceRepartition de tous les Service
        dont le MefService porte cette discipline (dédupliquées, voir _dedup_shared_reduced_repartitions) ;
        les moyens viennent des Teacher rattachés à la discipline via TeacherDiscipline, répartis
        en définitifs/provisoires selon is_temporary_support (voir teacher.py, Volet D). Les
        propriétés calculées de Teacher (discipline_duration_minutes, are_duration_minutes, ...)
        sont lues sous le contexte ambiant db.filter_discipline_id (voir teacher.py, architecture.md
        §15.G) pour ne compter que l'apport de CETTE discipline.
        """
        from backend.app.models.discipline import Discipline
        from backend.app.models.teacher import Teacher, TeacherDiscipline
        from backend.app.models.mef import MefService
        from backend.app.models.service import Service, ServiceRepartition

        results = []
        counter = 1
        for discipline in db.query(Discipline).all():
            teacher_ids = [
                row[0] for row in db.query(TeacherDiscipline.teacher_id)
                .filter(TeacherDiscipline.discipline_id == discipline.id).distinct().all()
            ]
            teachers = db.query(Teacher).filter(Teacher.id.in_(teacher_ids)).all() if teacher_ids else []
            def_teachers = [t for t in teachers if not t.is_temporary_support]
            temp_teachers = [t for t in teachers if t.is_temporary_support]

            need_rows = _dedup_shared_reduced_repartitions(
                db.query(ServiceRepartition)
                .join(Service, ServiceRepartition.service_id == Service.id)
                .join(MefService, Service.mef_service_id == MefService.id)
                .filter(MefService.discipline_id == discipline.id)
                .all()
            )
            need_raw_duration_minutes = sum(r.raw_need_weekly_duration_minutes for r in need_rows)
            need_weighted_duration_minutes = sum(r.weighted_need_weekly_duration_minutes for r in need_rows)

            db.filter_discipline_id = discipline.id
            try:
                are_duration_minutes = sum(t.are_duration_minutes for t in teachers)
                imp_duration_minutes = sum(t.particular_mission_duration_minutes for t in teachers)

                def_teached_duration_minutes = sum(t.discipline_duration_minutes - t.ara_duration_minutes for t in def_teachers)
                def_given_duration_minutes = sum(t.other_school_duration_minutes for t in def_teachers)

                temp_teached_duration_minutes = sum(t.discipline_duration_minutes - t.ara_duration_minutes for t in temp_teachers)
                temp_given_duration_minutes = sum(t.other_school_duration_minutes for t in temp_teachers)
            finally:
                db.filter_discipline_id = None

            total_needs = need_weighted_duration_minutes + are_duration_minutes
            def_gap_duration_minutes = def_teached_duration_minutes - def_given_duration_minutes - total_needs
            total_ressource_duration_minutes = (
                (def_teached_duration_minutes - def_given_duration_minutes)
                + (temp_teached_duration_minutes - temp_given_duration_minutes)
            )
            total_gap_duration_minutes = max(0, total_ressource_duration_minutes - total_needs)
            total_hsa_duration_minutes = max(0, total_needs - total_ressource_duration_minutes)

            results.append(cls(
                id=counter,
                discipline_id=discipline.id,
                need_ids=[r.id for r in need_rows],
                def_teacher_ids=[t.id for t in def_teachers],
                temp_teacher_ids=[t.id for t in temp_teachers],
                need_raw_duration_minutes=need_raw_duration_minutes,
                need_weighted_duration_minutes=need_weighted_duration_minutes,
                are_duration_minutes=are_duration_minutes,
                total_needs=total_needs,
                def_teacher_count=len(def_teachers),
                def_teached_duration_minutes=def_teached_duration_minutes,
                def_given_duration_minutes=def_given_duration_minutes,
                def_gap_duration_minutes=def_gap_duration_minutes,
                temp_teacher_count=len(temp_teachers),
                temp_teached_duration_minutes=temp_teached_duration_minutes,
                temp_given_duration_minutes=temp_given_duration_minutes,
                total_ressource_duration_minutes=total_ressource_duration_minutes,
                total_gap_duration_minutes=total_gap_duration_minutes,
                total_hsa_duration_minutes=total_hsa_duration_minutes,
                imp_duration_minutes=imp_duration_minutes,
            ))
            counter += 1

        return results
