import enum
import random
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy import Column, Integer, Float, String, ForeignKey, Table, Enum
from backend.app.models.base import Base, constrains, exposed, related_field
from backend.app.models.course import get_duration_options

service_teachers = Table(
    "service_teachers",
    Base.metadata,
    Column("service_id", Integer, ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
    Column("teacher_id", Integer, ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True),
)


class RepartitionPeriodicity(str, enum.Enum):
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"


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

    weekly_duration_full_class_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée hebdo classe entière (min)", "min": 0})
    weekly_duration_reduced_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée hebdo effectif réduit (min)", "min": 0})
    weekly_duration_split_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée hebdo effectif dédoublé (min)", "min": 0})
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
        (r.occurrence_count, r.duration_minutes, r.periodicity)
        for r in service.repartitions
    )


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
    name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Nom", "readOnly": True})

    # Relations de navigation
    service: Mapped[Optional["Service"]] = relationship("Service", back_populates="repartitions")
    courses: Mapped[list["Course"]] = relationship("Course", back_populates="service_repartition", info={"label": "Cours générés"})

    @constrains("duration_minutes")
    def validate_duration_multiple(self, db: Session):
        from backend.app.models.system_setting import SystemSetting
        val = SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION")
        duration = int(val)
        if self.duration_minutes % duration != 0:
            raise ValueError(f"La durée de la répartition ({self.duration_minutes} min) doit être un multiple exact du créneau standard ({duration} min).")

    @constrains()
    def _compute_name(self, db: Session):
        """Recalcule et stocke le nom d'affichage, ex: 2x01h00(H) ou 1x01h30(Q)."""
        from backend.app.core.time_utils import minutes_to_hours
        _, hours_text = minutes_to_hours(self.duration_minutes)
        periodicity_letter = "H" if self.periodicity == RepartitionPeriodicity.WEEKLY else "Q"
        self.name = f"{self.occurrence_count}x{hours_text}({periodicity_letter})"

    @constrains()
    def _check_sibling_alignment_still_matches(self, db: Session):
        if not self.service or not self.service.alignment_id:
            return
        siblings = db.query(Service).filter(Service.alignment_id == self.service.alignment_id, Service.id != self.service_id).all()
        for sibling in siblings:
            if _repartition_signature(sibling) != _repartition_signature(self.service):
                raise ValueError("Cette modification casse l'homogénéité de répartition requise par l'alignement du service.")


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
