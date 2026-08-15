from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Float, Boolean, Date, JSON, ForeignKey, Table
from sqlalchemy.orm import relationship, Session
from backend.app.models.base import Base, related_field, constrains, onchange, exposed
from backend.app.models.user import HasUserAccount

teacher_subjects = Table(
    "teacher_subjects",
    Base.metadata,
    Column("teacher_id", Integer, ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", Integer, ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True),
)

class Teacher(HasUserAccount, Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, unique=True, info={"label": "Compte utilisateur"})
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False, info={"label": "Code Enseignant", "placeholder": "ex: T1"})
    first_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Prénom", "placeholder": "ex: Marc"})
    last_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom de famille", "placeholder": "ex: Dupont"})
    max_weekly_hours: Mapped[float] = mapped_column(Float, nullable=False, default=18.0, info={"label": "Heures max hebdomadaires", "min": 1.0, "max": 40.0, "step": "0.5"})

    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement Principal"})
    # Nullable : un prof peut ne déclarer aucune matière préférée, même s'il a des matières
    # enseignées (subject_ids) — cf. _sync_preferred_subject ci-dessous pour le seul cas où ce
    # champ est calculé automatiquement plutôt que saisi librement.
    preferred_subject_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=True, info={"label": "Matière préférée"})

    # --- État civil ---
    title_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_titles.id", ondelete="SET NULL"), nullable=True, info={"label": "Civilité"})
    birth_last_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Nom de naissance"})
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date de naissance"})
    birth_city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_cities.id", ondelete="SET NULL"), nullable=True, info={"label": "Ville de naissance"})
    # Valeur générique {filename, mime_type, data_base64} — voir architecture.md, champ binaire
    # générique. widget="image" sélectionne l'aperçu dédié plutôt que le widget par défaut
    # (Télécharger/Effacer/Parcourir), qui reste le comportement de tout autre champ binaire.
    photo: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, info={"label": "Photo", "type": "binary", "widget": "image"})
    photo_diffusion_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Autorisation de diffuser la photo"})

    # --- Coordonnées ---
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Téléphone"})
    phone_diffusion_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Autorisation de diffuser le n° de téléphone"})
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Email"})
    email_diffusion_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Autorisation de diffuser l'adresse email"})
    address_line1: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Adresse (ligne 1)"})
    address_line2: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Adresse (ligne 2)"})
    address_line3: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Adresse (ligne 3)"})
    address_line4: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Adresse (ligne 4)"})
    # Champ texte libre, ne pointe vers aucune table : sert uniquement à filtrer dynamiquement les
    # options d'address_city_id (voir ui.json, dynamicOptionsFilter, architecture.md §15.R).
    address_zipcode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Code postal"})
    address_city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_cities.id", ondelete="SET NULL"), nullable=True, info={"label": "Ville"})
    address_country_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_countries.id", ondelete="SET NULL"), nullable=True, info={"label": "Pays"})

    # --- Données administratives ---
    numen: Mapped[Optional[str]] = mapped_column(String(20), unique=True, index=True, nullable=True, info={"label": "NUMEN"})
    is_board_member: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Membre du conseil d'administration"})

    # --- Données propres à l'enseignement ---
    function_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_functions.id", ondelete="SET NULL"), nullable=True, info={"label": "Fonction"})
    support_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_supports.id", ondelete="SET NULL"), nullable=True, info={"label": "Support"})
    support_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_support_types.id", ondelete="SET NULL"), nullable=True, info={"label": "Type de support"})
    is_temporary_support: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Support temporaire (suppléant...)"})
    support_comment: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, info={"label": "Commentaire sur le support"})

    # --- Dossier administratif : données propres au poste ---
    degree_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_degrees.id", ondelete="SET NULL"), nullable=True, info={"label": "Diplôme le plus élevé"})
    administrative_group_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_administrative_groups.id", ondelete="SET NULL"), nullable=True, info={"label": "Corps"})
    administrative_group_entry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date d'entrée dans le corps"})
    level_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_levels.id", ondelete="SET NULL"), nullable=True, info={"label": "Grade"})
    level_entry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date d'entrée dans le grade"})
    step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"label": "Échelon"})
    step_entry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date d'entrée dans l'échelon"})
    recruit_discipline_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("disciplines.id", ondelete="SET NULL"), nullable=True, info={"label": "Discipline de recrutement"})
    affectation_mode_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_affectation_modes.id", ondelete="SET NULL"), nullable=True, info={"label": "Modalité d'affectation"})
    affectation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date d'affectation"})

    # --- Dossier administratif : dernière inspection ---
    last_inspection_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date de la dernière inspection"})
    last_inspection_note: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, info={"label": "Note de la dernière inspection"})
    last_inspection_inspector_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_inspectors.id", ondelete="SET NULL"), nullable=True, info={"label": "Inspecteur"})
    service_mode_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_service_modes.id", ondelete="SET NULL"), nullable=True, info={"label": "Modalité de service"})

    # Relations de navigation
    user: Mapped[Optional["User"]] = relationship("User", back_populates="teacher")
    school: Mapped[Optional["School"]] = relationship("School", back_populates="teachers")
    courses: Mapped[list["Course"]] = relationship("Course", secondary="course_teachers", back_populates="teachers", passive_deletes="all", info={"label": "Cours"})
    # Noter que l'association avec les sessions se fait via session_teachers (Many-to-Many)
    subjects: Mapped[list["Subject"]] = relationship("Subject", secondary=teacher_subjects, info={"label": "Matières enseignées"})
    preferred_subject: Mapped[Optional["Subject"]] = relationship("Subject", foreign_keys=[preferred_subject_id])

    title: Mapped[Optional["RefTitle"]] = relationship("RefTitle", foreign_keys=[title_id])
    birth_city: Mapped[Optional["RefCity"]] = relationship("RefCity", foreign_keys=[birth_city_id])
    address_city: Mapped[Optional["RefCity"]] = relationship("RefCity", foreign_keys=[address_city_id])
    address_country: Mapped[Optional["RefCountry"]] = relationship("RefCountry", foreign_keys=[address_country_id])
    function: Mapped[Optional["RefFunction"]] = relationship("RefFunction", foreign_keys=[function_id])
    support: Mapped[Optional["RefSupport"]] = relationship("RefSupport", foreign_keys=[support_id])
    support_type: Mapped[Optional["RefSupportType"]] = relationship("RefSupportType", foreign_keys=[support_type_id])
    degree: Mapped[Optional["RefDegree"]] = relationship("RefDegree", foreign_keys=[degree_id])
    administrative_group: Mapped[Optional["RefAdministrativeGroup"]] = relationship("RefAdministrativeGroup", foreign_keys=[administrative_group_id])
    level: Mapped[Optional["RefLevel"]] = relationship("RefLevel", foreign_keys=[level_id])
    recruit_discipline: Mapped[Optional["Discipline"]] = relationship("Discipline", foreign_keys=[recruit_discipline_id])
    affectation_mode: Mapped[Optional["RefAffectationMode"]] = relationship("RefAffectationMode", foreign_keys=[affectation_mode_id])
    last_inspection_inspector: Mapped[Optional["RefInspector"]] = relationship("RefInspector", foreign_keys=[last_inspection_inspector_id])
    service_mode: Mapped[Optional["RefServiceMode"]] = relationship("RefServiceMode", foreign_keys=[service_mode_id])

    # Lignes de volumes horaires annexes (ARA, ARE, discipline, missions, service ailleurs) —
    # relations 1-N possédées : détectées automatiquement par le moteur générique (parentField,
    # voir architecture.md §15.J) et exposées en popin CRUD via OwnedRelationField, sans widget
    # dédié à écrire.
    ara_lines: Mapped[list["TeacherAra"]] = relationship("TeacherAra", back_populates="teacher", passive_deletes="all", info={"label": "Lignes ARA"})
    are_lines: Mapped[list["TeacherAre"]] = relationship("TeacherAre", back_populates="teacher", passive_deletes="all", info={"label": "Lignes ARE"})
    # required_field=True : un enseignant doit toujours être rattaché à au moins une discipline
    # (évite une ligne "Sans discipline" dans le TRMD) — bloque la soumission du formulaire tant
    # que la collection est vide (voir GenericForm.vue). Garde-fou définitif côté backend :
    # TeacherDiscipline.delete() (voir plus bas).
    # PAS la clé "required" : réservée par JSON-Schema/OpenAPI au niveau de l'objet PARENT (liste
    # des clés obligatoires du payload, voir schema.required dans App.vue) — un booléen "required"
    # sur le schéma d'UNE propriété fait planter la génération OpenAPI (Pydantic ValidationError
    # sur OpenAPI.components.schemas.*.properties.discipline_line_ids.required : "Input should be
    # a valid list"). D'où cette clé dédiée, non réservée — générique, pas spécifique aux
    # relations/collections : App.vue la fusionne directement dans le même `required` frontend que
    # les champs scalaires classiques, donc utilisable sur n'importe quel type de champ.
    discipline_lines: Mapped[list["TeacherDiscipline"]] = relationship("TeacherDiscipline", back_populates="teacher", passive_deletes="all", info={"label": "Lignes Discipline", "required_field": True})
    particular_mission_lines: Mapped[list["TeacherParticularMission"]] = relationship("TeacherParticularMission", back_populates="teacher", passive_deletes="all", info={"label": "Lignes Missions particulières"})
    pacte_mission_lines: Mapped[list["TeacherPacteMission"]] = relationship("TeacherPacteMission", back_populates="teacher", passive_deletes="all", info={"label": "Lignes Missions Pacte"})
    other_school_lines: Mapped[list["TeacherOtherSchool"]] = relationship("TeacherOtherSchool", back_populates="teacher", passive_deletes="all", info={"label": "Lignes Autres établissements"})

    @constrains("subject_ids", "preferred_subject_id")
    def _sync_preferred_subject(self, db: Session):
        """
        S'il n'y a qu'une seule matière enseignée, la matière préférée est nécessairement
        celle-là — champ calculé et stocké dans ce cas précis (pattern déjà utilisé ailleurs,
        ex: ServiceRepartition.name), pas une simple validation qui rejetterait la sauvegarde :
        avec un seul choix possible, il n'y a rien à demander explicitement à l'utilisateur.
        Dans tous les autres cas (0 ou plusieurs matières enseignées), preferred_subject_id reste
        un champ librement éditable.
        """
        if len(self.subjects) == 1:
            self.preferred_subject_id = self.subjects[0].id

    @constrains("last_name", "first_name", "birth_date")
    def _check_identity_unique(self, db: Session):
        if not self.birth_date:
            return
        existing = db.query(Teacher).filter(
            Teacher.last_name == self.last_name,
            Teacher.first_name == self.first_name,
            Teacher.birth_date == self.birth_date,
            Teacher.id != (self.id or 0),
        ).first()
        if existing:
            raise ValueError("Un enseignant avec le même nom, prénom et date de naissance existe déjà.")

    @onchange("address_city_id")
    def _onchange_address_city(self, db: Session):
        if not self.address_city_id:
            self.address_country_id = None
            return
        from backend.app.models.ref_city import RefCity
        city = db.query(RefCity).filter(RefCity.id == self.address_city_id).first()
        self.address_country_id = city.country_id if city else None

    # Déclaration déclarative et compacte des champs liés (Style Odoo)
    max_hours_per_day = related_field("constraint_record", "max_hours_per_day", info={"label": "Max Heures par Jour", "min": 0, "max": 12, "step": "0.5"})
    max_hours_per_am = related_field("constraint_record", "max_hours_per_am", info={"label": "Max Heures par Matinée", "min": 0, "max": 8, "step": "0.5"})
    max_hours_per_pm = related_field("constraint_record", "max_hours_per_pm", info={"label": "Max Heures par Après-midi", "min": 0, "max": 8, "step": "0.5"})
    max_presence_days_per_week = related_field("constraint_record", "max_presence_days_per_week", info={"label": "Max Jours Présence par Semaine", "min": 0, "max": 6})
    max_presence_hours_per_day = related_field("constraint_record", "max_presence_hours_per_day", info={"label": "Max Heures Présence par Jour", "min": 0, "max": 12, "step": "0.5"})
    late_start_days_per_week = related_field("constraint_record", "late_start_days_per_week", info={"label": "Jours de démarrage tardif par Semaine", "min": 0, "max": 6})
    late_start_time = related_field("constraint_record", "late_start_time", info={"label": "Heure de démarrage au plus tôt", "type": "time", "placeholder": "ex: 08h30"})
    early_end_days_per_week = related_field("constraint_record", "early_end_days_per_week", info={"label": "Jours de fin précoce par Semaine", "min": 0, "max": 6})
    early_end_time = related_field("constraint_record", "early_end_time", info={"label": "Heure de fin au plus tard", "type": "time", "placeholder": "ex: 16h30"})
    min_free_days_per_week = related_field("constraint_record", "min_free_days_per_week", info={"label": "Jours libres minimum par Semaine", "min": 0, "max": 6})
    min_free_half_days_per_week = related_field("constraint_record", "min_free_half_days_per_week", info={"label": "Demi-jours libres minimum par Semaine", "min": 0, "max": 12})
    max_worked_am_per_week = related_field("constraint_record", "max_worked_am_per_week", info={"label": "Max Matinées travaillées par Semaine", "min": 0, "max": 6})
    max_worked_pm_per_week = related_field("constraint_record", "max_worked_pm_per_week", info={"label": "Max Après-midis travaillées par Semaine", "min": 0, "max": 6})
    only_one_half_day_per_day = related_field("constraint_record", "only_one_half_day_per_day", default=False, info={"label": "Ne travailler qu'une demi-journée par jour"})
    max_gap_hours_per_week = related_field("constraint_record", "max_gap_hours_per_week", default=2, info={"label": "Max heures creuses (trous) par Semaine", "min": 0, "max": 20})

    @property
    def constraint_record(self):
        from sqlalchemy.orm import object_session
        session = object_session(self)
        if not session or not self.id:
            return None
        
        from backend.app.models.constraint import ResourceConstraint
        return session.query(ResourceConstraint).filter(
            ResourceConstraint.resource_type == 'Teacher',
            ResourceConstraint.resource_id == self.id
        ).first()

    def _ensure_constraint_record(self):
        """
        Méthode appelée automatiquement par le CRUDMixin parent pour
        garantir l'existence de la contrainte liée.
        """
        from backend.app.models.constraint import ResourceConstraint
        from sqlalchemy.orm import object_session
        session = object_session(self)
        if not session:
            return None
            
        constraint = session.query(ResourceConstraint).filter(
            ResourceConstraint.resource_type == 'Teacher',
            ResourceConstraint.resource_id == self.id
        ).first()
        if not constraint:
            constraint = ResourceConstraint(
                resource_type='Teacher',
                resource_id=self.id
            )
            constraint._via_crud_mixin_create = True
            session.add(constraint)
        return constraint

    @property
    def display_name(self) -> str:
        if self.first_name:
            return f"{self.first_name} {self.last_name}"
        return self.last_name

    # --- Champs calculés pour le TRMD (volet D) ---
    #
    # Contexte ambiant : trmd_synthesis.py pose `db.filter_discipline_id = <id>` avant de lire ces
    # propriétés (try/finally, même idiome que db._weekly_duration_sync_service_id, voir
    # architecture.md §15.G) pour restreindre leur calcul à une discipline précise. Sans contexte
    # actif (ex: une liste Teacher normale), filter_discipline_id est absent et ces propriétés
    # retombent sur "aucun filtre" = somme totale du professeur.

    @property
    def _discipline_majeure_id(self) -> Optional[int]:
        """
        Discipline dont l'apport (discipline_lines) est le plus important pour ce professeur —
        toujours calculée sur l'ENSEMBLE de ses lignes, jamais filtrée par le contexte ambiant.
        Sert de référence pour ventiler ARE/ARA/missions/dons de service à une discipline précise
        quand l'apport d'un enseignant est réparti sur plusieurs disciplines (voir spec.md — TODO
        d'origine : "l'ARE/ARA/mission particulière/mission PACTE/dons de service sont rattachés
        à la discipline dont l'apport est le plus important").
        """
        lines = self.discipline_lines
        if not lines:
            return None
        return max(lines, key=lambda l: l.duration_minutes or 0).discipline_id

    def _filter_discipline_id(self) -> Optional[int]:
        from sqlalchemy.orm import object_session
        return getattr(object_session(self), "filter_discipline_id", None)

    def _sum_lines_by_own_discipline(self, lines) -> int:
        """Chaque ligne porte sa propre discipline_id (ex: discipline_lines) — filtrage ligne à
        ligne, pas de recours à la discipline majeure."""
        filter_discipline_id = self._filter_discipline_id()
        if filter_discipline_id is None:
            return sum(l.duration_minutes or 0 for l in lines)
        return sum(l.duration_minutes or 0 for l in lines if l.discipline_id == filter_discipline_id)

    def _sum_lines_by_discipline_majeure(self, lines) -> int:
        """Ces lignes (ARE/ARA/missions/dons de service) ne portent aucune discipline propre —
        attribuées en bloc à la discipline majeure du professeur (tout ou rien)."""
        filter_discipline_id = self._filter_discipline_id()
        if filter_discipline_id is not None and filter_discipline_id != self._discipline_majeure_id:
            return 0
        return sum(l.duration_minutes or 0 for l in lines)

    @exposed(info={"label": "Heures dans sa discipline", "type": "duration", "readOnly": True})
    @property
    def discipline_duration_minutes(self) -> int:
        return self._sum_lines_by_own_discipline(self.discipline_lines)

    @exposed(info={"label": "ARE", "type": "duration", "readOnly": True})
    @property
    def are_duration_minutes(self) -> int:
        return self._sum_lines_by_discipline_majeure(self.are_lines)

    @exposed(info={"label": "ARA", "type": "duration", "readOnly": True})
    @property
    def ara_duration_minutes(self) -> int:
        return self._sum_lines_by_discipline_majeure(self.ara_lines)

    @exposed(info={"label": "Mission particulière", "type": "duration", "readOnly": True})
    @property
    def particular_mission_duration_minutes(self) -> int:
        return self._sum_lines_by_discipline_majeure(self.particular_mission_lines)

    @exposed(info={"label": "Mission Pacte", "type": "duration", "readOnly": True})
    @property
    def pacte_mission_duration_minutes(self) -> int:
        return self._sum_lines_by_discipline_majeure(self.pacte_mission_lines)

    @exposed(info={"label": "Heures données à un autre établissement", "type": "duration", "readOnly": True})
    @property
    def other_school_duration_minutes(self) -> int:
        return self._sum_lines_by_discipline_majeure(self.other_school_lines)


# Objets de liaison à volume horaire (teacher_id CASCADE, ref_*_id RESTRICT) — dans ce fichier
# plutôt que dans un fichier dédié par classe, comme le reste du projet (MefService/MefDivision
# dans mef.py, ServiceRepartition/Alignment dans service.py) : un fichier par objet N-à-N/de
# liaison n'est pas la convention ici, il vit avec son modèle propriétaire.
class TeacherAra(Base):
    __tablename__ = "teacher_aras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    ref_ara_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref_aras.id", ondelete="RESTRICT"), nullable=False, info={"label": "ARA"})
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée", "type": "duration"})

    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="ara_lines")
    ref_ara: Mapped["RefAra"] = relationship("RefAra")

    @constrains('duration_minutes')
    def _validate_duration(self, db: Session):
        from backend.app.core.time_utils import validate_multiple_of_standard_timeslot
        validate_multiple_of_standard_timeslot(db, self.duration_minutes, "La durée de la ligne ARA")


class TeacherAre(Base):
    __tablename__ = "teacher_ares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    ref_are_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref_ares.id", ondelete="RESTRICT"), nullable=False, info={"label": "ARE"})
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée", "type": "duration"})

    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="are_lines")
    ref_are: Mapped["RefAre"] = relationship("RefAre")

    @constrains('duration_minutes')
    def _validate_duration(self, db: Session):
        from backend.app.core.time_utils import validate_multiple_of_standard_timeslot
        validate_multiple_of_standard_timeslot(db, self.duration_minutes, "La durée de la ligne ARE")


class TeacherDiscipline(Base):
    __tablename__ = "teacher_disciplines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    discipline_id: Mapped[int] = mapped_column(Integer, ForeignKey("disciplines.id", ondelete="RESTRICT"), nullable=False, info={"label": "Discipline"})
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée", "type": "duration"})

    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="discipline_lines")
    discipline: Mapped["Discipline"] = relationship("Discipline")

    @constrains('duration_minutes')
    def _validate_duration(self, db: Session):
        from backend.app.core.time_utils import validate_multiple_of_standard_timeslot
        validate_multiple_of_standard_timeslot(db, self.duration_minutes, "La durée de la ligne discipline")

    def delete(self, db: Session):
        """
        Garantie backend (garde-fou définitif, imparable même hors IHM) qu'un Teacher reste
        toujours rattaché à au moins une discipline — voir architecture.md section 15.H pour le
        principe similaire côté MefDivision. Ne bloque pas la création d'un Teacher sans ligne
        (impossible à empêcher transactionnellement, le panneau détail crée les lignes après
        coup) : seule la suppression de la DERNIÈRE ligne restante, alors que le Teacher lui-même
        survit, est refusée — complétée côté IHM par le flag `required` sur
        `Teacher.discipline_lines` (voir OwnedRelationField.vue). Ne s'applique PAS quand la
        ligne est supprimée en cascade par la suppression du Teacher lui-même (CRUDMixin
        pose `_via_crud_mixin_delete` sur le Teacher avant de cascader vers ses dépendants,
        voir base.py::_cascade_delete_dependents) — sinon un Teacher ne pourrait plus jamais
        être supprimé du tout.
        """
        if getattr(self.teacher, "_via_crud_mixin_delete", False):
            return super().delete(db)
        sibling_count = db.query(TeacherDiscipline).filter(
            TeacherDiscipline.teacher_id == self.teacher_id,
            TeacherDiscipline.id != self.id,
        ).count()
        if sibling_count == 0:
            raise ValueError("Impossible de supprimer la dernière discipline d'un enseignant : un enseignant doit toujours être rattaché à au moins une discipline.")
        return super().delete(db)


class TeacherParticularMission(Base):
    __tablename__ = "teacher_particular_missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    ref_particular_mission_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref_particular_missions.id", ondelete="RESTRICT"), nullable=False, info={"label": "Mission particulière"})
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée", "type": "duration"})

    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="particular_mission_lines")
    ref_particular_mission: Mapped["RefParticularMission"] = relationship("RefParticularMission")

    @constrains('duration_minutes')
    def _validate_duration(self, db: Session):
        from backend.app.core.time_utils import validate_multiple_of_standard_timeslot
        validate_multiple_of_standard_timeslot(db, self.duration_minutes, "La durée de la ligne mission particulière")


class TeacherPacteMission(Base):
    __tablename__ = "teacher_pacte_missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    ref_pacte_mission_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref_pacte_missions.id", ondelete="RESTRICT"), nullable=False, info={"label": "Mission Pacte"})
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée", "type": "duration"})

    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="pacte_mission_lines")
    ref_pacte_mission: Mapped["RefPacteMission"] = relationship("RefPacteMission")

    @constrains('duration_minutes')
    def _validate_duration(self, db: Session):
        from backend.app.core.time_utils import validate_multiple_of_standard_timeslot
        validate_multiple_of_standard_timeslot(db, self.duration_minutes, "La durée de la ligne mission Pacte")


class TeacherOtherSchool(Base):
    __tablename__ = "teacher_other_schools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    ref_external_school_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref_external_schools.id", ondelete="RESTRICT"), nullable=False, info={"label": "Autre établissement"})
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Durée", "type": "duration"})

    teacher: Mapped["Teacher"] = relationship("Teacher", back_populates="other_school_lines")
    ref_external_school: Mapped["RefExternalSchool"] = relationship("RefExternalSchool")

    @constrains('duration_minutes')
    def _validate_duration(self, db: Session):
        from backend.app.core.time_utils import validate_multiple_of_standard_timeslot
        validate_multiple_of_standard_timeslot(db, self.duration_minutes, "La durée de la ligne autre établissement")