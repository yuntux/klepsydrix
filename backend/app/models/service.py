import enum
import math
import random
from functools import partial
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy import Column, Integer, Float, String, ForeignKey, Table, Enum
from backend.app.models.base import Base, constrains, exposed, related_field
from backend.app.core.time_utils import get_duration_options

# Les 3 champs weekly_duration_*_minutes de Service/MefService valent 0 par défaut ("modalité non
# utilisée") : contrairement à Course/ServiceRepartition, leurs options doivent inclure 0.
_weekly_duration_options = partial(get_duration_options, include_zero=True)

service_teachers = Table(
    "service_teachers",
    Base.metadata,
    Column("service_id", Integer, ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
    Column("teacher_id", Integer, ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True),
)


class RepartitionPeriodicity(str, enum.Enum):
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"


class RepartitionGroupType(str, enum.Enum):
    FULL_CLASS = "FULL_CLASS"
    SPLIT = "SPLIT"
    REDUCED = "REDUCED"


# Lettre affichée dans ServiceRepartition.name (voir _compute_name), ex: 2x1h(H/C).
_REPARTITION_GROUP_TYPE_LETTERS = {
    RepartitionGroupType.FULL_CLASS: "C",
    RepartitionGroupType.SPLIT: "D",
    RepartitionGroupType.REDUCED: "P",
}


class Service(Base):
    """
    Service opérationnel : affectation réelle qui lie une structure (Division via MefDivision,
    ou Groupe), un ou plusieurs professeurs et une matière. Toujours généré à partir d'un
    MefService (gabarit réglementaire) — jamais créé ni supprimé directement, uniquement via la
    propagation MefService/MefDivision (voir MefService.create()/.update()/.delete() et
    MefDivision.create()) — mais librement modifiable ensuite sans impact sur son gabarit d'origine
    (propagation à sens unique). is_synced_with_mef_service permet de détecter la dérive.
    """
    __tablename__ = "services"
    # Action groupée exposée par GenericPivot (architecture.md section 15.L) : type "bulk_api",
    # nouvelle valeur (les seuls types préexistants — "api"/"wizard" — supposent un enregistrement
    # unique). condition s'évalue sur un tableau `records` (la sélection courante), pas un `record`
    # singulier. La vraie contrainte métier (répartition homogène) reste vérifiée côté serveur dans
    # align_bulk — cette condition n'est qu'un filtre d'affichage, pas l'autorité.
    __actions__ = [
        {
            "id": "align_bulk",
            "label": "Aligner",
            "type": "bulk_api",
            "icon": "fa-link",
            "condition": "records.length >= 2"
        }
    ]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # nullable=False + ondelete=CASCADE : un Service n'existe jamais sans son MefService d'origine
    # (ni à la création, ni après coup) — il ne doit jamais survivre à la suppression de son gabarit.
    mef_service_id: Mapped[int] = mapped_column(Integer, ForeignKey("mef_services.id", ondelete="CASCADE"), nullable=False, info={"label": "Service MEF d'origine", "readOnly": True})
    mef_division_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("mef_divisions.id", ondelete="SET NULL"), nullable=True, info={"label": "Lien MEF/Division"})
    group_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, info={"label": "Groupe"})
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, info={"label": "Matière"})
    discipline_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("disciplines.id", ondelete="SET NULL"), nullable=True, info={"label": "Discipline"})
    election_method_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("election_methods.id", ondelete="SET NULL"), nullable=True, info={"label": "Modalité d'élection"})
    alignment_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("alignments.id", ondelete="SET NULL"), nullable=True, info={"label": "Alignement"})

    student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Effectif", "min": 0, "max": 50})
    weighting_coefficient: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, info={"label": "Pondération", "min": 0.0, "max": 5.0, "step": "0.05"})

    weekly_duration_full_class_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée hebdo classe entière (min)", "type": "select", "options": _weekly_duration_options})
    weekly_duration_reduced_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée hebdo effectif réduit (min)", "type": "select", "options": _weekly_duration_options})
    weekly_duration_split_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée hebdo effectif dédoublé (min)", "type": "select", "options": _weekly_duration_options})
    reduced_group_student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Élèves en effectif réduit", "min": 0})

    # Champs mirroir du MefService d'origine : copiés à la génération, comparés par
    # is_synced_with_mef_service. student_count est volontairement exclu (voir MefService.student_count).
    _MEF_SERVICE_MIRROR_FIELDS = (
        "subject_id", "discipline_id", "election_method_id", "weighting_coefficient",
        "weekly_duration_full_class_minutes", "weekly_duration_reduced_minutes",
        "weekly_duration_split_minutes", "reduced_group_student_count",
    )

    # Relations de navigation
    mef_service: Mapped[Optional["MefService"]] = relationship("MefService", back_populates="services")
    mef_division: Mapped[Optional["MefDivision"]] = relationship("MefDivision")
    division_id = related_field("mef_division", "division_id", info={"label": "Division", "resource": "divisions", "readOnly": True})
    mef_id = related_field("mef_division", "mef_id", info={"label": "MEF", "resource": "mefs", "readOnly": True})
    # Couleur de l'Alignment lié, à plat sur le Service — évite au frontend (ex: GenericPivot,
    # section 15.L de architecture.md) d'avoir à résoudre un chemin imbriqué "alignment.color" ;
    # même pattern que division_id/mef_id ci-dessus.
    alignment_color = related_field("alignment", "color", info={"label": "Couleur alignement", "readOnly": True})
    group: Mapped[Optional["Group"]] = relationship("Group")
    subject: Mapped[Optional["Subject"]] = relationship("Subject")
    discipline: Mapped[Optional["Discipline"]] = relationship("Discipline")
    election_method: Mapped[Optional["ElectionMethod"]] = relationship("ElectionMethod")
    alignment: Mapped[Optional["Alignment"]] = relationship("Alignment", back_populates="services")
    teachers: Mapped[list["Teacher"]] = relationship("Teacher", secondary=service_teachers, info={"label": "Enseignants"})
    # Pas de cascade="delete-orphan" ici : la suppression en cascade des ServiceRepartition est
    # désormais pilotée par CRUDMixin._cascade_delete_dependents() à partir du ondelete=CASCADE
    # de ServiceRepartition.service_id (voir base.py) — déclarer aussi une cascade ORM ferait
    # doublon (tentative de suppression redondante sur des lignes déjà supprimées).
    repartitions: Mapped[list["ServiceRepartition"]] = relationship("ServiceRepartition", back_populates="service", info={"label": "Répartitions"})

    @constrains()
    def _check_structure_exclusivity(self, db: Session):
        if self.mef_division_id and self.group_id:
            raise ValueError("Un service ne peut pas être rattaché à la fois à une Division (via MEF/Division) et à un Groupe.")
        if not self.mef_division_id and not self.group_id:
            raise ValueError("Un service doit être rattaché soit à une Division (via MEF/Division), soit à un Groupe.")

    @constrains()
    def _check_mef_consistency(self, db: Session):
        if self.mef_division_id and self.mef_service and self.mef_division:
            if self.mef_service.mef_id != self.mef_division.mef_id:
                raise ValueError("Le service MEF d'origine et le lien MEF/Division doivent concerner le même MEF.")

    @constrains()
    def _check_unique_mef_service_mef_division_pair(self, db: Session):
        if not self.mef_service_id or not self.mef_division_id:
            return
        duplicate = db.query(Service).filter(
            Service.mef_service_id == self.mef_service_id,
            Service.mef_division_id == self.mef_division_id,
            Service.id != self.id,
        ).first()
        if duplicate:
            raise ValueError("Un Service existe déjà pour ce couple MefService/MefDivision (générés automatiquement à la création du MefService ou du MefDivision).")

    @constrains('weekly_duration_full_class_minutes', 'weekly_duration_reduced_minutes', 'weekly_duration_split_minutes')
    def validate_weekly_durations_multiple(self, db: Session):
        from backend.app.core.time_utils import validate_multiple_of_standard_timeslot
        validate_multiple_of_standard_timeslot(db, self.weekly_duration_full_class_minutes, "La durée hebdomadaire classe entière du service")
        validate_multiple_of_standard_timeslot(db, self.weekly_duration_reduced_minutes, "La durée hebdomadaire effectif réduit du service")
        validate_multiple_of_standard_timeslot(db, self.weekly_duration_split_minutes, "La durée hebdomadaire effectif dédoublé du service")

    @constrains('weekly_duration_full_class_minutes')
    def _sync_full_class_repartitions(self, db: Session):
        _generate_repartition_service(db, self, RepartitionGroupType.FULL_CLASS, self.weekly_duration_full_class_minutes, 1)

    @constrains('weekly_duration_split_minutes')
    def _sync_split_repartitions(self, db: Session):
        _generate_repartition_service(db, self, RepartitionGroupType.SPLIT, self.weekly_duration_split_minutes, 2)

    @constrains('weekly_duration_reduced_minutes', 'student_count', 'reduced_group_student_count')
    def _sync_reduced_repartitions(self, db: Session):
        groups_need = _reduced_groups_need(self)
        _generate_repartition_service(db, self, RepartitionGroupType.REDUCED, self.weekly_duration_reduced_minutes, groups_need)

    @constrains("alignment_id")
    def _check_alignment_repartition_match(self, db: Session):
        if not self.alignment_id:
            return
        siblings = db.query(Service).filter(Service.alignment_id == self.alignment_id, Service.id != self.id).all()
        for sibling in siblings:
            if _repartition_signature(sibling) != _repartition_signature(self):
                raise ValueError("Tous les services d'un même alignement doivent partager le même modèle de répartition.")

    @exposed
    @property
    def total_weekly_duration_minutes(self) -> int:
        return (self.weekly_duration_full_class_minutes or 0) \
            + (self.weekly_duration_reduced_minutes or 0) \
            + (self.weekly_duration_split_minutes or 0)

    @exposed
    @property
    def is_synced_with_mef_service(self) -> bool:
        ms = self.mef_service
        return all(getattr(self, f) == getattr(ms, f) for f in self._MEF_SERVICE_MIRROR_FIELDS)

    @classmethod
    def generate_from_mef_service(cls, db: Session, mef_service: "MefService", mef_division: "MefDivision") -> "Service":
        """
        Crée un Service pour ce couple (MefService, MefDivision), en copiant les valeurs du
        gabarit. Appelé automatiquement par MefService.create() (pour chaque MefDivision déjà
        liée au MEF) et par MefDivision.create() (pour chaque MefService déjà existant du MEF) —
        propagation à sens unique, en création seulement (voir is_synced_with_mef_service pour
        détecter la dérive après coup, plutôt que de re-synchroniser de force sur update).
        """
        vals = {
            "mef_service_id": mef_service.id,
            "mef_division_id": mef_division.id,
            "student_count": mef_service.student_count,
        }
        for field in cls._MEF_SERVICE_MIRROR_FIELDS:
            vals[field] = getattr(mef_service, field)
        return cls.create(db, vals)

    @classmethod
    def align_bulk(cls, db: Session, ids: list[int]) -> dict:
        """
        Action groupée "Aligner" (voir __actions__ ci-dessus et architecture.md section 15.L) :
        crée toujours un nouvel Alignment (jamais de fusion avec un Alignment existant — décision
        confirmée) et y rattache tous les Service listés. La contrainte de répartition homogène est
        vérifiée deux fois : ici en amont (message clair, aucun Alignment orphelin créé si ça
        échoue) et de toute façon par _check_alignment_repartition_match à chaque Service.update().

        Paramètre nommé `ids` (pas `service_ids`) : make_class_call_endpoint (generic.py) injecte
        toujours `db` en kwarg quand la signature le porte, donc tout appel positionnel (`args`)
        entrerait en collision avec lui dès que `db` précède le vrai paramètre métier — les actions
        `bulk_api` doivent donc être appelées via `kwargs`, avec ce nom de paramètre générique
        (réutilisable tel quel par une future action groupée sur une autre ressource).
        """
        services = db.query(cls).filter(cls.id.in_(ids)).all()
        if len(services) < 2:
            raise ValueError("Il faut sélectionner au moins 2 services pour créer un alignement.")
        if len({_repartition_signature(s) for s in services}) > 1:
            raise ValueError("Tous les services sélectionnés doivent partager le même modèle de répartition pour être alignés.")

        import uuid
        suffix = uuid.uuid4().hex[:8].upper()
        alignment = Alignment.create(db, {"code": f"AL_AUTO_{suffix}", "name": f"Alignement auto {suffix}"})
        for service in services:
            service.update(db, {"alignment_id": alignment.id})
        return {"alignment_id": alignment.id, "alignment_code": alignment.code}


def _repartition_signature(service: "Service") -> frozenset:
    return frozenset(
        (r.occurrence_count, r.duration_minutes, r.periodicity, r.group_type)
        for r in service.repartitions
    )


def _sync_aligned_repartitions(db: Session, service: "Service"):
    """
    Propage le modèle de répartition de `service` vers tous les autres Service du même Alignment,
    en remplaçant entièrement leurs ServiceRepartition par des copies des siennes — pour qu'ils
    partagent exactement la même _repartition_signature. Remplace l'ancien comportement qui
    rejetait la modification avec une erreur ("casse l'homogénéité...") : modifier la répartition
    d'un service aligné répercute désormais le changement sur les autres services alignés, plutôt
    que de le bloquer.

    Garde de réentrance (db._syncing_alignment_repartitions) : recréer les ServiceRepartition d'un
    service voisin ci-dessous déclenche à son tour ce même mécanisme sur ses propres lignes — sans
    cette garde, chaque voisin re-déclencherait une synchronisation complète des AUTRES voisins,
    déjà couverte par la boucle en cours.
    """
    if not service.alignment_id or getattr(db, "_syncing_alignment_repartitions", False):
        return
    # service.repartitions (et celle de chaque voisin) a pu être chargée plus tôt dans cette même
    # opération, avant que d'autres ServiceRepartition ne soient créées/supprimées "de l'autre
    # côté" (FK posée directement plutôt que via cette collection) — sans l'expirer, la comparaison
    # de signature ci-dessous se ferait sur un état obsolète (un aller-retour supplémentaire aurait
    # alors semblé inutile alors qu'il ne l'était pas).
    db.expire(service, ["repartitions"])
    siblings = db.query(Service).filter(Service.alignment_id == service.alignment_id, Service.id != service.id).all()
    for sibling in siblings:
        db.expire(sibling, ["repartitions"])
    target_signature = _repartition_signature(service)
    mismatched = [s for s in siblings if _repartition_signature(s) != target_signature]
    if not mismatched:
        return

    db._syncing_alignment_repartitions = True
    try:
        reference_rows = [
            {"occurrence_count": r.occurrence_count, "duration_minutes": r.duration_minutes, "periodicity": r.periodicity.value, "group_type": r.group_type.value}
            for r in service.repartitions
        ]
        for sibling in mismatched:
            for old_row in list(sibling.repartitions):
                old_row.delete(db)
            for vals in reference_rows:
                ServiceRepartition.create(db, {**vals, "service_id": sibling.id})
    finally:
        db._syncing_alignment_repartitions = False

    # _recompute_service_weekly_durations (voir plus bas) ignore tout appel pendant que
    # db._syncing_alignment_repartitions est vrai — le miroir ci-dessus supprime puis recrée toutes
    # les lignes d'un voisin, et sans cette garde, chaque étape intermédiaire (incomplète) du miroir
    # déclencherait un recalcul avec un état transitoire, écrasant le précédent. On recalcule donc
    # explicitement, une seule fois, une fois le miroir stabilisé.
    for sibling in mismatched:
        db.expire(sibling)
        _recompute_service_weekly_durations(db, sibling)


def _reduced_groups_need(service: "Service") -> int:
    """Nombre de groupes en effectif réduit — 1 par défaut tant que reduced_group_student_count
    n'est pas renseigné (traité comme un unique groupe, pas une erreur bloquante)."""
    if not service.reduced_group_student_count:
        return 1
    return math.ceil(service.student_count / service.reduced_group_student_count)


def _generate_repartition_service(db: Session, service: "Service", group_type: "RepartitionGroupType", target_weekly_duration: int, occurrence_multiple: int):
    """
    Implémente generate_repartitionService (voir spec.md, section « Synchronisation Service ↔
    ServiceRepartition ») : régénère les ServiceRepartition de type `group_type` de `service` à
    partir d'une durée hebdomadaire cible, en blocs d'1h (+ un éventuel reliquat), toutes en
    periodicity=WEEKLY. `occurrence_multiple` compense la définition du type (SPLIT double le
    nombre de séances car chaque moitié de classe a la sienne ; REDUCED le multiplie par le nombre
    de groupes) — voir _recompute_service_weekly_durations pour la réciproque.

    Garde de réentrance (db._weekly_duration_sync_service_id) : les create()/delete() ci-dessous
    déclenchent à leur tour _recompute_service_weekly_durations sur CE service — sans la garde, la
    réciproque réécrirait aussitôt les mêmes champs, qui redéclencheraient cette fonction, etc.
    """
    if getattr(db, "_weekly_duration_sync_service_id", None) == service.id:
        return

    previous_sync_id = getattr(db, "_weekly_duration_sync_service_id", None)
    db._weekly_duration_sync_service_id = service.id
    try:
        existing = db.query(ServiceRepartition).filter(
            ServiceRepartition.service_id == service.id,
            ServiceRepartition.group_type == group_type,
        ).all()
        for row in existing:
            row.delete(db)

        if target_weekly_duration > 0:
            full_hours = target_weekly_duration // 60
            remainder = target_weekly_duration % 60
            if remainder > 0:
                if full_hours > 0:
                    ServiceRepartition.create(db, {
                        "service_id": service.id, "group_type": group_type.value,
                        "periodicity": RepartitionPeriodicity.WEEKLY.value,
                        "duration_minutes": 60 + remainder, "occurrence_count": occurrence_multiple,
                    })
                    full_hours -= 1
                else:
                    ServiceRepartition.create(db, {
                        "service_id": service.id, "group_type": group_type.value,
                        "periodicity": RepartitionPeriodicity.WEEKLY.value,
                        "duration_minutes": remainder, "occurrence_count": occurrence_multiple,
                    })
            if full_hours > 0:
                ServiceRepartition.create(db, {
                    "service_id": service.id, "group_type": group_type.value,
                    "periodicity": RepartitionPeriodicity.WEEKLY.value,
                    "duration_minutes": 60, "occurrence_count": full_hours * occurrence_multiple,
                })
    finally:
        db._weekly_duration_sync_service_id = previous_sync_id


def _recompute_service_weekly_durations(db: Session, service: "Service"):
    """
    Réciproque de _generate_repartition_service (voir spec.md) : recalcule les 3
    weekly_duration_*_minutes de `service` à partir de l'ensemble de ses ServiceRepartition
    actuelles, après toute création/modification/suppression de l'une d'elles.

    Ne s'exécute PAS si ce service est déjà celui en cours de synchronisation
    (db._weekly_duration_sync_service_id) : les create()/delete() de _generate_repartition_service
    déclenchent cette fonction à leur tour, mais les valeurs qu'elle recalculerait sont déjà
    exactement celles qui ont déclenché la régénération — un aller-retour inutile. Ce garde-fou a
    aussi pour effet voulu qu'un édit manuel d'une seule ligne (hors synchro) met à jour les
    totaux du service SANS réécrire les autres lignes de répartition.

    Ne s'exécute pas non plus pendant un miroir d'alignement en cours (db._syncing_alignment_repartitions,
    voir _sync_aligned_repartitions) : ce miroir supprime puis recrée toutes les lignes d'un voisin
    d'un coup, et un recalcul déclenché sur un état intermédiaire (incomplet) écraserait le suivant —
    _sync_aligned_repartitions se charge d'appeler cette fonction lui-même, une fois le miroir stable.
    """
    if getattr(db, "_weekly_duration_sync_service_id", None) == service.id:
        return
    if getattr(db, "_syncing_alignment_repartitions", False):
        return

    totals = {RepartitionGroupType.FULL_CLASS: 0.0, RepartitionGroupType.SPLIT: 0.0, RepartitionGroupType.REDUCED: 0.0}
    for repartition in service.repartitions:
        periodicity_multiple = 0.5 if repartition.periodicity == RepartitionPeriodicity.BIWEEKLY else 1

        if repartition.group_type == RepartitionGroupType.FULL_CLASS:
            totals[RepartitionGroupType.FULL_CLASS] += repartition.duration_minutes * repartition.occurrence_count * periodicity_multiple

        elif repartition.group_type == RepartitionGroupType.SPLIT:
            if repartition.occurrence_count % 2 != 0:
                raise ValueError("Le nombre d'occurrences doit être un multiple de 2 puisqu'il s'agit d'une répartition de type Dédoublement.")
            totals[RepartitionGroupType.SPLIT] += repartition.duration_minutes * (repartition.occurrence_count // 2) * periodicity_multiple

        elif repartition.group_type == RepartitionGroupType.REDUCED:
            groups_need = _reduced_groups_need(service)
            if repartition.occurrence_count % groups_need != 0:
                raise ValueError(f"Le nombre d'occurrences doit être un multiple du nombre de groupes ({groups_need}, de {service.reduced_group_student_count} élèves maximum) puisqu'il s'agit d'une répartition de type Effectif réduit.")
            totals[RepartitionGroupType.REDUCED] += repartition.duration_minutes * (repartition.occurrence_count // groups_need) * periodicity_multiple

    previous_sync_id = getattr(db, "_weekly_duration_sync_service_id", None)
    db._weekly_duration_sync_service_id = service.id
    try:
        service.update(db, {
            "weekly_duration_full_class_minutes": int(round(totals[RepartitionGroupType.FULL_CLASS])),
            "weekly_duration_split_minutes": int(round(totals[RepartitionGroupType.SPLIT])),
            "weekly_duration_reduced_minutes": int(round(totals[RepartitionGroupType.REDUCED])),
        })
    finally:
        db._weekly_duration_sync_service_id = previous_sync_id


class ServiceRepartition(Base):
    """
    Ligne de décomposition d'un Service : un nombre d'occurrences hebdomadaires, d'une durée
    donnée, avec une périodicité (chaque semaine, ou une semaine sur deux — la répartition ne
    précise pas encore si ce sera la semaine A ou B, ce choix se fait à la génération du Course).
    """
    __tablename__ = "service_repartitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    service_id: Mapped[int] = mapped_column(Integer, ForeignKey("services.id", ondelete="CASCADE"), nullable=False, info={"label": "Service"})
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, info={"label": "Nombre d'occurrences", "min": 1, "max": 20})
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60, info={"label": "Durée", "type": "select", "options": get_duration_options})
    periodicity: Mapped[Any] = mapped_column(Enum(RepartitionPeriodicity, name="repartition_periodicity_enum"), nullable=False, default=RepartitionPeriodicity.WEEKLY, info={
        "label": "Périodicité", "type": "select",
        "options": [{"value": "WEEKLY", "label": "Chaque semaine"}, {"value": "BIWEEKLY", "label": "Une semaine sur deux"}],
    })
    group_type: Mapped[Any] = mapped_column(Enum(RepartitionGroupType, name="repartition_group_type_enum"), nullable=False, default=RepartitionGroupType.FULL_CLASS, info={
        "label": "Type de regroupement", "type": "select",
        "options": [
            {"value": "FULL_CLASS", "label": "Classe entière"},
            {"value": "SPLIT", "label": "Dédoublement"},
            {"value": "REDUCED", "label": "Effectif réduit"},
        ],
    })
    name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Nom", "readOnly": True})

    # Relations de navigation
    service: Mapped[Optional["Service"]] = relationship("Service", back_populates="repartitions")
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="service_repartition", info={"label": "Cours générés"})

    @constrains("duration_minutes")
    def validate_duration_multiple(self, db: Session):
        from backend.app.core.time_utils import validate_multiple_of_standard_timeslot
        validate_multiple_of_standard_timeslot(db, self.duration_minutes, "La durée de la répartition")

    @constrains()
    def _check_unique_service_periodicity_group_type_duration(self, db: Session):
        duplicate = db.query(ServiceRepartition).filter(
            ServiceRepartition.service_id == self.service_id,
            ServiceRepartition.periodicity == self.periodicity,
            ServiceRepartition.group_type == self.group_type,
            ServiceRepartition.duration_minutes == self.duration_minutes,
            ServiceRepartition.id != self.id,
        ).first()
        if duplicate:
            raise ValueError("Une répartition existe déjà pour ce service avec la même périodicité, le même type de regroupement et la même durée.")

    @constrains()
    def _compute_name(self, db: Session):
        """Recalcule et stocke le nom d'affichage, ex: 2x01h00(H/C) ou 1x01h30(Q/D)."""
        from backend.app.core.time_utils import minutes_to_hours
        _, hours_text = minutes_to_hours(self.duration_minutes)
        periodicity_letter = "H" if self.periodicity == RepartitionPeriodicity.WEEKLY else "Q"
        group_type_letter = _REPARTITION_GROUP_TYPE_LETTERS[self.group_type]
        self.name = f"{self.occurrence_count}x{hours_text}({periodicity_letter}/{group_type_letter})"

    @classmethod
    def create(cls, db: Session, vals: dict):
        # _sync_aligned_repartitions et _recompute_service_weekly_durations appellent tous deux, en
        # cascade, create()/update()/delete() sur d'autres ServiceRepartition — donc un flush avant
        # la fin de CE create()-ci (CRUDMixin ne positionne _via_crud_mixin_update sur l'instance
        # QU'À LA TOUTE FIN). Si ces deux fonctions tournaient comme de simples @constrains
        # (dispatchées AVANT ce point), un tel flush prématuré retomberait sur cette instance avec
        # son nom déjà recalculé par _compute_name mais pas encore flaggée — rejeté par le event
        # listener before_update ("Mise à jour directe interdite"). D'où ces appels explicites
        # APRÈS super().create(), une fois l'instance pleinement flushée/flaggée (même schéma que
        # ClassPart.create()/_auto_generate_links).
        instance = super().create(db, vals)
        if instance.service:
            _sync_aligned_repartitions(db, instance.service)
            _recompute_service_weekly_durations(db, instance.service)
        return instance

    def update(self, db: Session, vals: dict):
        result = super().update(db, vals)
        if self.service:
            _sync_aligned_repartitions(db, self.service)
            _recompute_service_weekly_durations(db, self.service)
        return result

    def delete(self, db: Session):
        # Capturé avant suppression : self.service devient inaccessible une fois la ligne supprimée.
        # Contrairement à create()/update(), delete() ne déclenche pas les méthodes @constrains
        # (voir CRUDMixin.delete()) — d'où ces appels explicites pour couvrir aussi ce cas.
        service = self.service
        result = super().delete(db)
        if service:
            # service.repartitions a pu être chargée (et mise en cache par la Session) avant cette
            # suppression — sans l'expirer, elle continuerait de renvoyer la ligne qu'on vient de
            # retirer, faussant _repartition_signature(service)/_recompute_service_weekly_durations
            # juste en dessous.
            db.expire(service)
            _sync_aligned_repartitions(db, service)
            _recompute_service_weekly_durations(db, service)
        return result


class Alignment(Base):
    """
    Regroupe plusieurs Service partageant le même modèle de répartition. Génère un Course
    composé par occurrence de répartition, avec une ligne de mapping par service aligné
    (décomposition Mode 1 : un cours enfant par professeur).
    """
    __tablename__ = "alignments"

    # Palette utilisée par create() ci-dessous pour l'affectation automatique de couleur — voir
    # architecture.md section 15.L (couleur de cellule dans GenericPivot : deux Alignment
    # visuellement indissociables rendraient ce mécanisme inutile).
    _PASTEL_PALETTE = [
        "#FFADAD", "#FFD6A5", "#FDFFB6", "#CAFFBF", "#9BF6FF",
        "#A0C4FF", "#BDB2FF", "#FFC6FF", "#FFB4A2", "#B5EAD7",
        "#C7CEEA", "#FFDAC1", "#E2F0CB", "#B5B9FF", "#FFCBF2", "#F1FFC4",
    ]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False, info={"label": "Code", "placeholder": "ex: BARRETTE_LV2_3EME"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom", "placeholder": "ex: Barrette LV2 - Niveau 3ème"})
    # nullable, SANS default SQL : un default de colonne serait repris tel quel par le schéma
    # Pydantic (make_pydantic_model) et rendrait "couleur omise" indistinguable de "couleur =
    # #CCCCCC" au moment où create() ci-dessous inspecte vals — cassant l'affectation automatique.
    # En pratique jamais NULL en base : create() assigne toujours une couleur, fournie ou pastel.
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True, info={"label": "Couleur", "type": "color", "placeholder": "ex: #3498DB"})

    # Relations de navigation
    services: Mapped[list["Service"]] = relationship("Service", back_populates="alignment", info={"label": "Services alignés"})

    @classmethod
    def create(cls, db: Session, vals: dict):
        """
        Si aucune couleur n'est fournie, affecte automatiquement la première couleur de
        _PASTEL_PALETTE pas encore utilisée par un autre Alignment (repli sur un tirage aléatoire
        dans la palette si elle est entièrement épuisée) — plutôt que de laisser le défaut de
        colonne #CCCCCC identique pour tous, ce qui rendrait plusieurs Alignment indistinguables
        dans GenericPivot. S'applique aussi bien à une création via l'IHM qu'à Service.align_bulk.
        """
        if not vals.get("color"):
            used_colors = {c for (c,) in db.query(cls.color).all()}
            available = [c for c in cls._PASTEL_PALETTE if c not in used_colors]
            vals["color"] = available[0] if available else random.choice(cls._PASTEL_PALETTE)
        return super().create(db, vals)
