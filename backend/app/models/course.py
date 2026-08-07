from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, select, Enum, Table, event
from sqlalchemy.orm import relationship, Session
from sqlalchemy.ext.hybrid import hybrid_property
from backend.app.models.base import Base, exposed, constrains, onchange
from backend.app.models.preference import WeekType
from backend.app.core.time_utils import get_duration_options

course_teachers = Table(
    "course_teachers",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("teacher_id", Integer, ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

course_classrooms = Table(
    "course_classrooms",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("classroom_id", Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

course_non_teaching_staffs = Table(
    "course_non_teaching_staffs",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("non_teaching_staff_id", Integer, ForeignKey("non_teaching_staffs.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

course_materials = Table(
    "course_materials",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("material_id", Integer, ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

course_divisions = Table(
    "course_divisions",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("division_id", Integer, ForeignKey("divisions.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

course_class_parts = Table(
    "course_class_parts",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("class_part_id", Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

course_groups = Table(
    "course_groups",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

course_periods = Table(
    "course_periods",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("period_id", Integer, ForeignKey("periods.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

class Course(Base):
    __tablename__ = "courses"
    # "component" absent : GenericForm.vue route par défaut vers GenericWizard.vue (mécanisme
    # générique piloté par "steps", voir architecture.md) plutôt qu'un composant bespoke —
    # componentsMap reste un échappatoire pour un futur wizard qui ne rentrerait pas dans ce moule.
    __actions__ = [
        {
            "id": "compose_course",
            "label": "Décomposer le cours",
            "type": "wizard",
            "icon": "fa-sitemap",
            "condition": "record.is_composed === true && record.status !== 'COMPLETELY_PLACED'",
            "cancelRpc": "rpc_cancel_composition",
            "steps": [
                {
                    "id": "mapping",
                    "title": "1. Mapping et mode de répartition",
                    "submitLabel": "Générer l'aperçu",
                    "rpc": "rpc_preview_composition",
                    "rpcParams": {"mode": "composition.mode", "mapping": "composition.mapping"},
                    "fields": [
                        {"key": "composition", "label": "Répartition", "type": "text", "widget": "course_composition_mapping", "fullWidth": True}
                    ]
                },
                {
                    "id": "preview",
                    "title": "2. Aperçu des cours enfants (brouillon)",
                    "submitLabel": "Valider",
                    "rpc": "rpc_save_composition",
                    "rpcParams": {"children_vals": "children_vals"},
                    "isLast": True,
                    "fields": [
                        {"key": "children_vals", "label": "Cours enfants", "type": "text", "widget": "course_composition_preview", "fullWidth": True}
                    ]
                }
            ]
        }
    ]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, info={"label": "Cours parent"})
    
    # Pour les cours simples, un subject_id est requis. Pour les cours complexes (parents), il peut être NULL.
    subject_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=True, info={"label": "Matière"})
    
    # Placements et attributs directs
    timeslot_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("timeslots.id", ondelete="SET NULL"), nullable=True, info={"label": "Créneau de placement"})
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Épinglé"})
    
    # Offset pour les enfants de cours complexes (nombre de créneaux de décalage par rapport au parent)
    parent_timeslot_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Décalage par rapport au parent"})
    
    week_type: Mapped[Any] = mapped_column(Enum(WeekType, name="course_week_type_enum"), nullable=False, default=WeekType.W, info={"label": "Semaine", "placeholder": "ex: A, B, M"})
    period_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("period_types.id", ondelete="SET NULL"), nullable=True, info={"label": "Type de période"})
    is_co_teaching: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Co-enseignement"})
    
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60, info={"label": "Durée", "type": "select", "options": get_duration_options})
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, info={"label": "Nom / Libellé", "placeholder": "ex: Cours de maths avancé"})
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True, info={"label": "Mémo / Note interne"})
    is_composed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Cours composé"})
    lock_structure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Structure verrouillée"})
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNPLACED", server_default="UNPLACED", info={"label": "Statut de placement"})
    decomposition_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="UNVENTILATED", server_default="UNVENTILATED", info={"label": "Statut de décomposition"})
    
    mission_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, info={"label": "Mission"})
    election_method_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("election_methods.id", ondelete="SET NULL"), nullable=True, info={"label": "Mode d'élection"})
    family_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("families.id", ondelete="SET NULL"), nullable=True, info={"label": "Famille"})
    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})
    service_repartition_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("service_repartitions.id", ondelete="SET NULL"), nullable=True, info={"label": "Répartition de service d'origine", "readOnly": True})

    # Relations de navigation hiérarchique
    parent: Mapped[Optional["Course"]] = relationship("Course", back_populates="children", remote_side=[id])
    # Pas de cascade="delete-orphan" ici : la suppression en cascade des Course enfants est
    # désormais pilotée par CRUDMixin._cascade_delete_dependents() à partir du ondelete=CASCADE
    # de Course.parent_id (voir base.py) — déclarer aussi une cascade ORM ferait doublon.
    children: Mapped[list["Course"]] = relationship("Course", back_populates="parent", info={"label": "Cours enfants"})

    # Relations de navigation Mto1
    subject_relation: Mapped[Optional["Subject"]] = relationship("Subject", back_populates="courses")
    timeslot: Mapped[Optional["Timeslot"]] = relationship("Timeslot")
    period_type: Mapped[Optional["PeriodType"]] = relationship("PeriodType")
    mission: Mapped[Optional["Mission"]] = relationship("Mission", back_populates="courses")
    service_repartition: Mapped[Optional["ServiceRepartition"]] = relationship("ServiceRepartition", back_populates="courses")
    election_method: Mapped[Optional["ElectionMethod"]] = relationship("ElectionMethod", back_populates="courses")
    family: Mapped[Optional["Family"]] = relationship("Family", back_populates="courses")
    school: Mapped[Optional["School"]] = relationship("School", back_populates="courses")
    
    # Ressources N..N pures
    teachers: Mapped[list["Teacher"]] = relationship("Teacher", secondary=course_teachers, back_populates="courses", info={"label": "Enseignants"})
    non_teaching_staffs: Mapped[list["NonTeachingStaff"]] = relationship("NonTeachingStaff", secondary=course_non_teaching_staffs, back_populates="courses", info={"label": "Personnels non-enseignants"})
    classrooms: Mapped[list["Classroom"]] = relationship("Classroom", secondary=course_classrooms, info={"label": "Salles de classe"})
    materials: Mapped[list["Material"]] = relationship("Material", secondary=course_materials, info={"label": "Matériels"})
    divisions: Mapped[list["Division"]] = relationship("Division", secondary=course_divisions, back_populates="courses", info={"label": "Classes / Divisions"})
    periods: Mapped[list["Period"]] = relationship("Period", secondary=course_periods, info={"label": "Périodes"})
    class_parts: Mapped[list["ClassPart"]] = relationship("ClassPart", secondary=course_class_parts, info={"label": "Groupes de classe"})
    groups: Mapped[list["Group"]] = relationship("Group", secondary=course_groups, back_populates="courses", info={"label": "Groupes"})

    @exposed
    @property
    def is_consistent_with_service(self) -> bool:
        """
        Indicateur de dérive par rapport au service d'origine (calculé à la demande, réservé
        aux cours sans enfant). Permet de repérer les cours dont la durée ou la périodicité a
        divergé de la ServiceRepartition qui les a générés, pour mesurer l'écart avec le TRMD.
        """
        from sqlalchemy.orm import object_session
        db = object_session(self)
        has_children = bool(self.children) or (
            db is not None and self.id is not None and
            db.query(Course).filter(Course.parent_id == self.id).count() > 0
        )
        if has_children:
            return True
        if not self.service_repartition_id or not self.service_repartition:
            return True

        from backend.app.models.service import RepartitionPeriodicity
        sr = self.service_repartition
        if self.duration_minutes != sr.duration_minutes:
            return False
        if sr.periodicity == RepartitionPeriodicity.WEEKLY and self.week_type != WeekType.W:
            return False
        if sr.periodicity == RepartitionPeriodicity.BIWEEKLY and self.week_type not in (WeekType.A, WeekType.B):
            return False
        return True

    @property
    def has_conflict(self) -> bool:
        """Indique si le cours présente un conflit de ressources (calculé à la demande, séparé du statut matérialisé)."""
        from sqlalchemy.orm import object_session
        db = object_session(self)
        if not db or not self.timeslot_id:
            return False

        try:
            self.validate_placement_conflicts(db)
            return False
        except ValueError:
            return True
    def resources_fully_ventilated_list(self, children_list) -> bool:
        """Vérifie si toutes les ressources du cours composé sont attribuées à au moins un cours enfant de la liste."""
        if not self.is_composed:
            return True
        
        def check_ventilated(parent_list, child_attr):
            parent_ids = {x.id for x in parent_list}
            if not parent_ids:
                return True
            child_ids = set()
            for child in children_list:
                child_ids.update(x.id for x in getattr(child, child_attr))
            return parent_ids.issubset(child_ids)

        return (
            check_ventilated(self.teachers, 'teachers') and
            check_ventilated(self.non_teaching_staffs, 'non_teaching_staffs') and
            check_ventilated(self.classrooms, 'classrooms') and
            check_ventilated(self.divisions, 'divisions') and
            check_ventilated(self.groups, 'groups') and
            check_ventilated(self.materials, 'materials') and
            check_ventilated(self.class_parts, 'class_parts')
        )

    def resources_fully_ventilated(self, exclude_child_id=None) -> bool:
        """Vérifie si toutes les ressources du cours composé sont attribuées à au moins un cours enfant."""
        children = [c for c in self.children if c.id != exclude_child_id]
        return self.resources_fully_ventilated_list(children)

    def recompute_status(self, exclude_child_id=None) -> str:
        """Calcule et met à jour le statut et l'état de décomposition du cours en base."""
        from sqlalchemy.orm import object_session
        db = object_session(self)
        
        # Autoriser la mise à jour interne de l'instance
        self._via_crud_mixin_update = True
        
        # 1. Statut de planification de base (status) : basé uniquement sur timeslot_id
        if not self.timeslot_id:
            self.status = "UNPLACED"
        else:
            self.status = "PLACED"

        # 2. Statut de décomposition (decomposition_status) : uniquement pour les cours composés
        if not self.is_composed:
            self.decomposition_status = None
        else:
            # Récupérer les enfants par requête directe (pas via self.children) ET les nouveaux
            # objets pas encore flushés. self.children est une collection ORM back_populates :
            # une fois chargée, elle reste en mémoire telle quelle pour le reste de la session,
            # y compris après la suppression d'un frère faite "de l'autre côté" par une requête
            # directe (voir Course.rpc_save_composition, qui boucle sur plusieurs child.delete()
            # d'affilée) — un accès ultérieur à un enfant déjà supprimé-et-flushé dans cette même
            # collection lève "Instance has been deleted". Une requête fraîche évite ce piège.
            children = set()
            if db:
                children.update(db.query(Course).filter(Course.parent_id == self.id).all())
                for obj in db.new:
                    if isinstance(obj, Course) and obj.parent_id is not None and obj.parent_id == self.id:
                        children.add(obj)
                for obj in db.deleted:
                    if isinstance(obj, Course) and obj in children:
                        children.remove(obj)
            elif self.children:
                children.update(self.children)
            
            # Appliquer l'exclusion si demandée
            if exclude_child_id:
                children = {c for c in children if c.id != exclude_child_id}
                
            if not children:
                self.decomposition_status = "UNVENTILATED"
            else:
                # 4. Calcul de la ventilation
                child_statuses = [c.status for c in children]
                if all(s == "PLACED" for s in child_statuses) and self.resources_fully_ventilated_list(children):
                    self.decomposition_status = "FULLY_VENTILATED"
                else:
                    self.decomposition_status = "PARTIALLY_VENTILATED"

        # Si c'est un enfant, recalculer le statut de son parent
        if self.parent_id and db:
            parent = db.get(self.__class__, self.parent_id)
            if parent:
                parent._via_crud_mixin_update = True
                parent.recompute_status()
                
        return self.status

    @constrains()
    def validate_periods_coherence(self, db):
        if not self.period_type_id:
            if self.periods:
                raise ValueError("Un cours annuel (sans type de période défini) ne peut pas être associé à des périodes.")
        else:
            for period in self.periods:
                if period.period_type_id != self.period_type_id:
                    raise ValueError(
                        f"La période '{period.name}' (type {period.period_type_id}) ne correspond pas "
                        f"au type de période '{self.period_type_id}' du cours."
                    )

    @onchange('teacher_ids', 'is_co_teaching', 'children_ids')
    @constrains('teacher_ids', 'is_co_teaching', 'children_ids')
    def _compute_is_composed(self, db=None):
        """Marque automatiquement le cours comme composé s'il y a plusieurs profs sans co-enseignement, ou s'il a des enfants."""
        has_multiple_teachers = getattr(self, 'teachers', None) and len(self.teachers) > 1 and not getattr(self, 'is_co_teaching', False)
        has_children = getattr(self, 'children', None) and len(self.children) > 0
        
        if has_multiple_teachers or has_children:
            self.is_composed = True
        else:
            self.is_composed = False

    @constrains('week_type', 'parent_id')
    def _sync_parent_week_type(self, db, exclude_child_id=None):
        """Si un enfant change d'alternance ou est supprimé, on recalcule celle de son parent."""
        if not self.parent_id:
            return
            
        parent = db.get(self.__class__, self.parent_id)
        if not parent:
            return

        # Requête directe plutôt que parent.children (voir recompute_status ci-dessus, même piège
        # de collection ORM obsolète après une suppression faite "de l'autre côté").
        children = [c for c in db.query(self.__class__).filter(self.__class__.parent_id == parent.id).all() if c.id != exclude_child_id]
        if not children:
            return
            
        from backend.app.models.preference import WeekType
        types = {c.week_type.value for c in children if c.week_type}
        
        if types == {"A"}:
            parent.week_type = WeekType.A
        elif types == {"B"}:
            parent.week_type = WeekType.B
        else:
            parent.week_type = WeekType.W
        db.add(parent)

    @constrains('duration_minutes')
    def validate_duration_multiple(self, db):
        from backend.app.core.time_utils import validate_multiple_of_standard_timeslot
        validate_multiple_of_standard_timeslot(db, self.duration_minutes, "La durée du cours")

    @constrains('duration_minutes', 'parent_id', 'timeslot_id')
    def validate_child_constraints(self, db):
        """Vérifie qu'un cours enfant respecte les limites de temps, de ressources et de profondeur."""
        for child in self.children:
            child.validate_child_constraints(db)
            
        if not self.parent:
            return

        # 0. Contrainte de profondeur (2 niveaux max)
        if self.parent.parent_id is not None:
            raise ValueError("Un cours ne peut pas avoir comme parent un cours qui est lui-même enfant (2 niveaux maximum).")
        if self.children:
            raise ValueError("Un cours complexe (ayant déjà des enfants) ne peut pas devenir l'enfant d'un autre cours.")

        # 1. Contraintes temporelles
        # Si le cours a un parent, son créneau effectif est déterminé par le créneau du parent et l'offset
        # (évite les conflits transitoires lors de la propagation du parent vers l'enfant).
        effective_ts = self.timeslot
        if self.parent and self.parent.timeslot:
            from backend.app.models.timeslot import Timeslot
            ts_id = self.parent.timeslot.get_offset_timeslot(db, self.parent_timeslot_offset)
            effective_ts = db.get(Timeslot, ts_id) if ts_id else None

        if effective_ts and self.parent and self.parent.timeslot:
            # Même jour obligatoire
            if effective_ts.day_of_week != self.parent.timeslot.day_of_week:
                raise ValueError("Le cours enfant doit être le même jour que son parent.")
            
            # Heure de début
            if effective_ts.minutes_from_midnight < self.parent.timeslot.minutes_from_midnight:
                raise ValueError("Le début d'un cours enfant ne peut pas être antérieur au début du cours parent.")
            
            # Heure de fin
            child_end = effective_ts.minutes_from_midnight + self.duration_minutes
            parent_end = self.parent.timeslot.minutes_from_midnight + self.parent.duration_minutes
            if child_end > parent_end:
                raise ValueError("La fin d'un cours enfant ne peut pas être ultérieure à la fin du cours parent.")

        # 2. Contraintes de ressources (l'enfant ne peut pas avoir une ressource non présente dans le parent)
        def _check_resources(child_resources, parent_resources, name):
            parent_ids = {r.id for r in parent_resources}
            for cr in child_resources:
                if cr.id not in parent_ids:
                    raise ValueError(f"La ressource {name} (ID: {cr.id}) de l'enfant est absente du cours parent.")

        _check_resources(self.teachers, self.parent.teachers, "Enseignant")
        _check_resources(self.non_teaching_staffs, self.parent.non_teaching_staffs, "Personnel non enseignant")
        _check_resources(self.classrooms, self.parent.classrooms, "Salle")
        _check_resources(self.divisions, self.parent.divisions, "Division")
        _check_resources(self.groups, self.parent.groups, "Groupe")
        _check_resources(self.materials, self.parent.materials, "Matériel")
        _check_resources(self.class_parts, self.parent.class_parts, "Partie de classe")

    @constrains('subject_id', 'teacher_ids', 'division_ids', 'group_ids', 'class_part_ids', 'is_composed')
    def compute_name(self, db):
        """Met à jour dynamiquement le nom du cours en fonction de ses attributs clés."""
        # 1. Base : La matière
        parts = []
        if getattr(self, 'subject_relation', None):
            parts.append(self.subject_relation.name)
        elif getattr(self, 'subject_id', None):
            from backend.app.models.subject import Subject
            subj = db.get(Subject, self.subject_id)
            if subj:
                parts.append(subj.name)
                
        if not parts:
            parts.append("Cours")
            
        if self.is_composed:
            self.name = f"Composé : {' - '.join(parts)}"
            return
            
        # 2. Audience : Divisions et Groupes
        audiences = []
        if getattr(self, 'divisions', None):
            audiences.extend([d.name for d in self.divisions if hasattr(d, 'name')])
        if getattr(self, 'groups', None):
            audiences.extend([g.name for g in self.groups if hasattr(g, 'name')])
            
        if audiences:
            parts.append(", ".join(audiences))
            
        # 3. Intervenants : Professeurs
        profs = []
        if getattr(self, 'teachers', None):
            profs.extend([t.last_name for t in self.teachers if hasattr(t, 'last_name')])
            
        if profs:
            parts.append(", ".join(profs))
            
        self.name = " - ".join(parts)

    def transform_to_simple_courses(self, db):
        """Transforme ce cours complexe en N cours simples en libérant ses enfants et en se supprimant."""
        if not self.is_composed:
            raise ValueError("Ce cours n'est pas complexe.")
        
        for child in self.children:
            child.update(db, {'parent_id': None})
            
        self.delete(db)

    @classmethod
    def group_into_complex_course(cls, db, course_ids: list[int]):
        """Regroupe plusieurs cours simples non placés en un seul cours complexe parent."""
        courses = db.query(cls).filter(cls.id.in_(course_ids)).all()
        if not courses:
            raise ValueError("Aucun cours fourni.")
        
        for c in courses:
            if c.parent_id is not None:
                raise ValueError(f"Le cours {c.id} est déjà un cours enfant.")
            if c.timeslot_id is not None:
                raise ValueError(f"Le cours {c.id} est déjà placé sur la grille, veuillez le dépositionner d'abord.")

        first_course = courses[0]

        # Calcul de l'union de toutes les ressources des enfants
        def union_ids(attr):
            seen = set()
            result = []
            for c in courses:
                for item in getattr(c, attr):
                    if item.id not in seen:
                        seen.add(item.id)
                        result.append(item.id)
            return result

        # Création du cours parent via CRUDMixin.create() pour passer par tous les hooks
        parent = cls.create(db, {
            'is_composed': True,
            'subject_id': first_course.subject_id,
            'school_id': first_course.school_id,
            'duration_minutes': max(c.duration_minutes for c in courses),
            'week_type': first_course.week_type,
            'teacher_ids': union_ids('teachers'),
            'non_teaching_staff_ids': union_ids('non_teaching_staffs'),
            'classroom_ids': union_ids('classrooms'),
            'division_ids': union_ids('divisions'),
            'group_ids': union_ids('groups'),
            'material_ids': union_ids('materials'),
            'class_part_ids': union_ids('class_parts'),
        })

        # Rattachement des enfants au parent via update() pour passer par les hooks
        for c in courses:
            c.update(db, {'parent_id': parent.id})

        return parent



    @constrains('timeslot_id', 'duration_minutes', 'week_type', 'period_id', 'parent_id', 'teacher_ids', 'classroom_ids', 'division_ids', 'non_teaching_staff_ids')
    def validate_placement_conflicts(self, db):
        target_ts_id = self.timeslot_id
        if target_ts_id is None:
            return

        from backend.app.models.timeslot import Timeslot
        from backend.app.models.teacher import Teacher
        from backend.app.models.classroom import Classroom
        from backend.app.models.division import Division
        from backend.app.models.non_teaching_staff import NonTeachingStaff

        target_ts = db.query(Timeslot).filter(Timeslot.id == target_ts_id).first()
        if not target_ts:
            raise ValueError("Créneau invalide")

        target_start = target_ts.minutes_from_midnight
        target_end = target_start + self.duration_minutes

        # Vérification du débordement en fin de journée
        from sqlalchemy import func
        from backend.app.models.system_setting import SystemSetting, SystemSettingKey
        max_minutes = db.query(func.max(Timeslot.minutes_from_midnight)).filter(Timeslot.day_of_week == target_ts.day_of_week).scalar()
        if max_minutes is not None:
            val = SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION")
            std_duration_min = int(val)
            absolute_end_minutes = max_minutes + std_duration_min
            if target_end > absolute_end_minutes:
                raise ValueError("Le cours déborde de la grille horaire de la journée.")

        target_week_type = getattr(self, 'week_type', 'W')

        
        def get_conflict_query(resource_filter):
            query = db.query(Course).join(Timeslot).filter(
                Course.id != self.id,
                resource_filter,
                Timeslot.day_of_week == target_ts.day_of_week,
                Timeslot.minutes_from_midnight < target_end,
                target_start < (Timeslot.minutes_from_midnight + Course.duration_minutes)
            )
            
            # BR-001: Règle Globale d'Exclusivité des Ressources
            
            # Règle 1 : Orthogonalité Structurelle (Inclusion)
            from sqlalchemy import or_
            target_parent_id = getattr(self, 'parent_id', None)
            if target_parent_id:
                query = query.filter(
                    Course.id != target_parent_id,
                    or_(Course.parent_id == None, Course.parent_id != target_parent_id)
                )
            else:
                query = query.filter(
                    or_(Course.parent_id == None, Course.parent_id != self.id)
                )
                
            # Règle 2 : Orthogonalité Hebdomadaire (Alternance)
            if target_week_type == 'A':
                query = query.filter(Course.week_type.in_(['A', 'W']))
            elif target_week_type == 'B':
                query = query.filter(Course.week_type.in_(['B', 'W']))
                
            # Règle 3 : Orthogonalité Périodique (Périodes Multiples)
            if self.period_type_id and self.periods:
                from backend.app.models.period import Period
                target_period_ids = [p.id for p in self.periods]
                query = query.filter(
                    or_(
                        Course.period_type_id == None,
                        Course.period_type_id != self.period_type_id,
                        Course.periods.any(Period.id.in_(target_period_ids))
                    )
                )

            return query

        t_ids = [t.id for t in self.teachers]
        if t_ids:
            if get_conflict_query(Course.teachers.any(Teacher.id.in_(t_ids))).first():
                raise ValueError("Conflit : L'enseignant est déjà occupé sur ce créneau (chevauchement)")

        s_ids = [s.id for s in self.non_teaching_staffs]
        if s_ids:
            if get_conflict_query(Course.non_teaching_staffs.any(NonTeachingStaff.id.in_(s_ids))).first():
                raise ValueError("Conflit : Le membre du personnel est déjà occupé sur ce créneau (chevauchement)")

        c_ids = [c.id for c in self.classrooms]
        if c_ids:
            if get_conflict_query(Course.classrooms.any(Classroom.id.in_(c_ids))).first():
                raise ValueError("Conflit : La salle est déjà occupée sur ce créneau (chevauchement)")

        d_ids = [d.id for d in self.divisions]
        if d_ids:
            if get_conflict_query(Course.divisions.any(Division.id.in_(d_ids))).first():
                raise ValueError("Conflit : La division est déjà occupée sur ce créneau (chevauchement)")

    @classmethod
    def _sync_vals_from_parent(cls, db, vals: dict, instance=None):
        if 'parent_id' in vals and not vals['parent_id']:
            vals['parent_timeslot_offset'] = 0
            return
            
        parent_id = vals.get('parent_id', getattr(instance, 'parent_id', None))
        if parent := (db.get(cls, parent_id) if parent_id else None):
            from backend.app.models.timeslot import Timeslot
            
            # Si l'utilisateur ou le solveur force le timeslot_id de l'enfant, on recalcule l'offset
            if 'timeslot_id' in vals and vals['timeslot_id'] is not None:
                if not parent.timeslot_id:
                    raise ValueError("Impossible d'assigner un créneau directement à un cours enfant si son cours parent n'est pas encore planifié.")
                
                child_ts = db.get(Timeslot, vals['timeslot_id'])
                parent_ts = db.get(Timeslot, parent.timeslot_id)
                if child_ts and parent_ts:
                    if child_ts.day_of_week != parent_ts.day_of_week:
                        raise ValueError("Le cours enfant doit être placé le même jour que son parent.")
                    if child_ts.minutes_from_midnight < parent_ts.minutes_from_midnight:
                        raise ValueError("Le cours enfant ne peut pas commencer avant son parent.")
                    
                    # On compte le nombre de créneaux exacts qui séparent le parent de l'enfant
                    offset = db.query(Timeslot).filter(
                        Timeslot.day_of_week == parent_ts.day_of_week,
                        Timeslot.minutes_from_midnight > parent_ts.minutes_from_midnight,
                        Timeslot.minutes_from_midnight <= child_ts.minutes_from_midnight
                    ).count()
                    vals['parent_timeslot_offset'] = offset

            # Sync descendante (écrasement du timeslot de l'enfant)
            offset = vals.get('parent_timeslot_offset', getattr(instance, 'parent_timeslot_offset', 0))
            vals['is_pinned'] = parent.is_pinned
            vals['timeslot_id'] = None
            
            if parent.timeslot_id:
                if parent_ts := db.get(Timeslot, parent.timeslot_id):
                    vals['timeslot_id'] = parent_ts.get_offset_timeslot(db, offset)

    @classmethod
    def create(cls, db: Session, vals: dict):
        # 1. Synchronisation avec le parent (si applicable)
        cls._sync_vals_from_parent(db, vals)
        
        # 2. Sauvegarde
        instance = super().create(db, vals)
        
        # Recalculer le statut du nouveau cours
        instance.recompute_status()
        
        if instance.parent_id:
            parent = db.get(cls, instance.parent_id)
            if parent:
                parent.recompute_status()
                
        return instance

    def update(self, db: Session, vals: dict):
        # Un cours épinglé (is_pinned=True, et le restant après cet appel) ne peut pas être
        # déplacé manuellement — créneau, salle ou semaine — miroir de la garde déjà appliquée
        # par le solveur (@PlanningPin sur PlanningCourse.is_pinned, qui gèle déjà timeslot et
        # classroom pour le placement automatique) : rien ne l'empêchait côté placement manuel
        # jusqu'ici (voir attribution_week_type_auto.md, Échange 4). Déverrouiller ET déplacer
        # dans le même appel reste autorisé (is_pinned=False dans les mêmes vals désactive la
        # garde) ; seuls les VALEURS EFFECTIVEMENT CHANGÉES déclenchent le refus, pour ne pas
        # bloquer le simple renvoi du timeslot_id courant (ex: bascule du pin via CourseCard.vue).
        new_is_pinned = vals.get('is_pinned', self.is_pinned)
        if self.is_pinned and new_is_pinned:
            if 'timeslot_id' in vals and vals['timeslot_id'] != self.timeslot_id:
                raise ValueError("Impossible de déplacer un cours épinglé : déverrouillez-le d'abord.")
            if 'classroom_ids' in vals:
                raise ValueError("Impossible de changer la salle d'un cours épinglé : déverrouillez-le d'abord.")
            if 'week_type' in vals and str(vals['week_type']) != str(self.week_type.value):
                raise ValueError("Impossible de changer la semaine d'un cours épinglé : déverrouillez-le d'abord.")

        # 1. Synchronisation avec le parent (si applicable)
        self.__class__._sync_vals_from_parent(db, vals, instance=self)

        old_parent_id = self.parent_id

        # Capturé avant sauvegarde si la répartition change : une partie de classe/un groupe
        # retiré ici peut devenir orphelin (voir backend/app/models/group.py, cleanup_orphaned_resources).
        track_resource_cleanup = 'class_part_ids' in vals or 'group_ids' in vals
        before_class_part_ids = {cp.id for cp in self.class_parts} if track_resource_cleanup else set()
        before_group_ids = {g.id for g in self.groups} if track_resource_cleanup else set()

        # 3. Sauvegarde
        res = super().update(db, vals)

        if track_resource_cleanup:
            from backend.app.models.group import cleanup_orphaned_resources
            removed_class_part_ids = before_class_part_ids - {cp.id for cp in self.class_parts}
            removed_group_ids = before_group_ids - {g.id for g in self.groups}
            cleanup_orphaned_resources(db, list(removed_class_part_ids), list(removed_group_ids))

        # Propager week_type et period_id aux préférences associées
        from backend.app.models.preference import ResourcePreference
        from backend.app.models.period import Period
        
        prefs = db.execute(select(ResourcePreference).filter_by(
            resource_type="Course",
            resource_id=self.id
        )).scalars().all()
        
        if prefs:
            for pref in prefs:
                pref._via_crud_mixin_update = True
                pref.week_type = self.week_type
                pref.periods = list(self.periods)
            db.flush()
        
        # Recalculer son propre statut
        self.recompute_status()
        
        # Faire remonter au parent
        if old_parent_id and old_parent_id != self.parent_id:
            old_parent = db.get(self.__class__, old_parent_id)
            if old_parent:
                old_parent.recompute_status(exclude_child_id=self.id)
        if self.parent_id:
            parent = db.get(self.__class__, self.parent_id)
            if parent:
                parent.recompute_status()

        # 4. Si on a bougé, on propage le mouvement aux enfants en forçant leur recalcul
        if 'timeslot_id' in vals or 'is_pinned' in vals:
            for child in self.children:
                child.update(db, {})
                
        return res

    def compose_by_mode(self, db: Session, mode: int, mapping: list[dict] = None) -> dict:
        """Méthode RPC legacy conservée pour compatibilité."""
        from backend.app.models.composition_mode import CompositionModes
        children = CompositionModes.apply(db, self, mode, mapping, preview=False)
        return {
            "status": "ok",
            "parent_id": self.id,
            "mode": mode,
            "children_ids": [c.id for c in children],
            "count": len(children),
        }

    def rpc_get_available_modes(self, db: Session, mapping: list[dict]) -> dict:
        """Retourne la liste des modes de composition applicables."""
        from backend.app.models.composition_mode import CompositionModes
        modes = CompositionModes.get_available_modes(db, self, mapping)
        return {"status": "ok", "available_modes": modes}

    def rpc_preview_composition(self, db: Session, mode: int, mapping: list[dict]) -> dict:
        """Génère l'aperçu des enfants sans les sauvegarder."""
        from backend.app.models.composition_mode import CompositionModes
        children_vals = CompositionModes.apply(db, self, mode, mapping, preview=True)
        return {"status": "ok", "children_vals": children_vals}

    def rpc_cancel_composition(self, db: Session) -> dict:
        """
        Appelée quand l'utilisateur quitte l'assistant sans valider. "Générer l'aperçu" a pu créer
        pour de vrai des parties de classe/partitions/groupes (voir CompositionModes) : on nettoie
        ici celles devenues orphelines (mêmes règles qu'après une suppression/modification de cours,
        voir backend/app/models/group.py, cleanup_orphaned_resources — sans effet sur une ressource
        créée manuellement).
        """
        from backend.app.models.group import cleanup_orphaned_resources
        cleanup_orphaned_resources(db, [cp.id for cp in self.class_parts], [g.id for g in self.groups])
        return {"status": "ok"}

    def rpc_save_composition(self, db: Session, children_vals: list[dict]) -> dict:
        """Sauvegarde définitivement les enfants modifiés par l'utilisateur."""
        # 1. Supprimer les anciens enfants proprement sans déclencher de synchronisation intermédiaire sur le parent
        # Pas de détachement préalable (child.parent_id = None) : ce serait une mutation directe
        # hors CRUDMixin, or Course.delete() fait un premier db.flush() (nettoyage
        # ResourcePreference) AVANT d'appeler super().delete() — donc avant que
        # _via_crud_mixin_delete/_via_crud_mixin_update soient positionnés. Cet enfant resterait
        # "sale" au moment de ce flush, et le before_update générique le rejetterait ("Mise à jour
        # directe interdite"). Inutile de toute façon : l'enfant va être supprimé, nul besoin de
        # vider sa FK avant. Garder parent_id intact permet aussi à Course.delete() de retrouver le
        # parent pour recompute_status()/_sync_parent_week_type().
        # _skip_resource_cleanup=True : voir CompositionModes.apply, même piège — le nettoyage est
        # différé après la recréation des enfants (juste en dessous), pour ne pas supprimer pour de
        # vrai une partie de classe/un groupe que children_vals s'apprête à réutiliser.
        children_to_delete = db.query(Course).filter(Course.parent_id == self.id).all()
        former_class_part_ids = set()
        former_group_ids = set()
        for child in children_to_delete:
            former_class_part_ids.update(cp.id for cp in child.class_parts)
            former_group_ids.update(g.id for g in child.groups)
            child.delete(db, _skip_resource_cleanup=True)

        # 2. Créer les nouveaux enfants de manière isolée pour éviter de perturber le parent prématurément
        children = []
        for vals in children_vals:
            vals_copy = dict(vals)
            # Ne pas lier au parent tout de suite pour éviter les flushs conflictuels
            vals_copy.pop('parent_id', None)
            # Mais il faut s'assurer qu'ils aient le bon school_id (et subject_id) qui seraient normalement copiés du parent
            vals_copy.setdefault('school_id', self.school_id)
            vals_copy.setdefault('subject_id', self.subject_id)

            children.append(Course.create(db, vals_copy))

        from backend.app.models.group import cleanup_orphaned_resources
        cleanup_orphaned_resources(db, list(former_class_part_ids), list(former_group_ids))

        # 3. Rattacher tous les enfants au parent via la méthode officielle update()
        # Cela déclenchera correctement les calculs métier (@onchange, etc)
        self.update(db, {'children_ids': [c.id for c in children]})
            
        return {
            "status": "ok",
            "parent_id": self.id,
            "children_ids": [c.id for c in children],
            "count": len(children),
        }

    def delete(self, db: Session, _skip_resource_cleanup: bool = False):
        """
        _skip_resource_cleanup : à True quand l'appelant supprime ce cours pour le recréer aussitôt
        avec (potentiellement) les mêmes ressources (voir CompositionModes.apply et
        rpc_save_composition) — sans ça, le nettoyage réactif ci-dessous supprimerait pour de vrai
        une partie de classe/un groupe encore réutilisé par le cours qui n'a pas encore été recréé
        au moment de cet appel. L'appelant est alors responsable d'appeler lui-même
        cleanup_orphaned_resources (voir backend/app/models/group.py) une fois la recréation terminée.
        """
        from sqlalchemy import delete
        from backend.app.models.preference import ResourcePreference
        db.execute(delete(ResourcePreference).filter_by(
            resource_type="Course",
            resource_id=self.id
        ))
        db.flush()

        # Capturé avant suppression : une fois le cours supprimé, ces parties de classe/groupes
        # peuvent devenir orphelins (voir backend/app/models/group.py, cleanup_orphaned_resources).
        former_class_part_ids = [cp.id for cp in self.class_parts]
        former_group_ids = [g.id for g in self.groups]

        parent_id = self.parent_id
        res = super().delete(db)
        if parent_id:
            parent = db.get(self.__class__, parent_id)
            if parent:
                parent._via_crud_mixin_update = True
                parent.recompute_status(exclude_child_id=self.id)
            self._sync_parent_week_type(db, exclude_child_id=self.id)

        if not _skip_resource_cleanup:
            from backend.app.models.group import cleanup_orphaned_resources
            cleanup_orphaned_resources(db, former_class_part_ids, former_group_ids)
        return res
