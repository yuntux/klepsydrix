from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, select, Enum, Table, event
from sqlalchemy.orm import relationship, Session
from sqlalchemy.ext.hybrid import hybrid_property
from backend.app.models.base import Base, exposed, constrains
from backend.app.models.preference import WeekType

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

class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=True)
    
    # Pour les cours simples, un subject_id est requis. Pour les cours complexes (parents), il peut être NULL.
    subject_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=True)
    
    # Placements et attributs directs
    timeslot_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("timeslots.id", ondelete="SET NULL"), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Offset pour les enfants de cours complexes (nombre de créneaux de décalage par rapport au parent)
    parent_timeslot_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    week_type: Mapped[Any] = mapped_column(Enum(WeekType, name="course_week_type_enum"), nullable=False, default=WeekType.W)
    period_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("periods.id", ondelete="SET NULL"), nullable=True)
    is_co_teaching: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=55)
    label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_composed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lock_structure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNPLACED", server_default="UNPLACED")
    decomposition_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="UNVENTILATED", server_default="UNVENTILATED")
    
    mission_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("missions.id", ondelete="SET NULL"), nullable=True)
    election_method_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("election_methods.id", ondelete="SET NULL"), nullable=True)
    family_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("families.id", ondelete="SET NULL"), nullable=True)
    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)

    # Relations de navigation hiérarchique
    parent: Mapped[Optional["Course"]] = relationship("Course", back_populates="children", remote_side=[id])
    children: Mapped[list["Course"]] = relationship("Course", back_populates="parent", cascade="all, delete-orphan")

    # Relations de navigation Mto1
    subject_relation: Mapped[Optional["Subject"]] = relationship("Subject", back_populates="courses")
    timeslot: Mapped[Optional["Timeslot"]] = relationship("Timeslot")
    mission: Mapped[Optional["Mission"]] = relationship("Mission", back_populates="courses")
    election_method: Mapped[Optional["ElectionMethod"]] = relationship("ElectionMethod", back_populates="courses")
    family: Mapped[Optional["Family"]] = relationship("Family", back_populates="courses")
    school: Mapped[Optional["School"]] = relationship("School", back_populates="courses")
    
    # Ressources N..N pures
    teachers: Mapped[list["Teacher"]] = relationship("Teacher", secondary=course_teachers, back_populates="courses")
    non_teaching_staffs: Mapped[list["NonTeachingStaff"]] = relationship("NonTeachingStaff", secondary=course_non_teaching_staffs, back_populates="courses")
    classrooms: Mapped[list["Classroom"]] = relationship("Classroom", secondary=course_classrooms)
    materials: Mapped[list["Material"]] = relationship("Material", secondary=course_materials)
    divisions: Mapped[list["Division"]] = relationship("Division", secondary=course_divisions, back_populates="courses")
    class_parts: Mapped[list["ClassPart"]] = relationship("ClassPart", secondary=course_class_parts)
    groups: Mapped[list["Group"]] = relationship("Group", secondary=course_groups, back_populates="courses")


    def has_conflicts(self, db: Session) -> bool:
        """Vérifie si le cours a des conflits de ressources sans lever d'exception."""
        if not self.timeslot_id:
            return False

        from backend.app.models.timeslot import Timeslot
        from backend.app.models.teacher import Teacher
        from backend.app.models.classroom import Classroom
        from backend.app.models.division import Division
        from backend.app.models.non_teaching_staff import NonTeachingStaff
        from backend.app.models.period import Period
        from sqlalchemy import or_

        target_ts = db.get(Timeslot, self.timeslot_id)
        if not target_ts:
            return False

        target_start = target_ts.hour * 60
        target_end = target_start + self.duration_minutes
        target_week_type = getattr(self.week_type, 'value', 'W')

        def get_conflict_query(resource_filter):
            query = db.query(Course).join(Timeslot).filter(
                Course.id != self.id,
                resource_filter,
                Timeslot.day_of_week == target_ts.day_of_week,
                (Timeslot.hour * 60) < target_end,
                target_start < (Timeslot.hour * 60 + Course.duration_minutes)
            )
            
            # Règle 1 : Orthogonalité Structurelle
            if self.parent_id:
                query = query.filter(
                    Course.id != self.parent_id,
                    or_(Course.parent_id == None, Course.parent_id != self.parent_id)
                )
            else:
                query = query.filter(
                    or_(Course.parent_id == None, Course.parent_id != self.id)
                )

            # Règle 2 : Orthogonalité Hebdomadaire
            if target_week_type == 'A':
                query = query.filter(Course.week_type.in_(['A', 'W']))
            elif target_week_type == 'B':
                query = query.filter(Course.week_type.in_(['B', 'W']))

            # Règle 3 : Orthogonalité Périodique
            if self.period_id:
                target_period = db.get(Period, self.period_id)
                if target_period:
                    query = query.outerjoin(Period, Course.period_id == Period.id).filter(
                        or_(
                            Course.period_id == None,
                            Period.period_type_id != target_period.period_type_id,
                            Course.period_id == target_period.id
                        )
                    )
            return query

        t_ids = [t.id for t in self.teachers]
        if t_ids and get_conflict_query(Course.teachers.any(Teacher.id.in_(t_ids))).first():
            return True

        s_ids = [s.id for s in self.non_teaching_staffs]
        if s_ids and get_conflict_query(Course.non_teaching_staffs.any(NonTeachingStaff.id.in_(s_ids))).first():
            return True

        c_ids = [c.id for c in self.classrooms]
        if c_ids and get_conflict_query(Course.classrooms.any(Classroom.id.in_(c_ids))).first():
            return True

        d_ids = [d.id for d in self.divisions]
        if d_ids and get_conflict_query(Course.divisions.any(Division.id.in_(d_ids))).first():
            return True

        return False

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
            # Récupérer les enfants depuis la relation en mémoire ET les nouveaux objets dans la session
            children = set()
            if self.children:
                children.update(self.children)
            if db:
                for obj in db.new:
                    if isinstance(obj, Course) and obj.parent_id is not None and obj.parent_id == self.id:
                        children.add(obj)
                for obj in db.deleted:
                    if isinstance(obj, Course) and obj in children:
                        children.remove(obj)
            
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

    @constrains('week_type', 'parent_id')
    def _sync_parent_week_type(self, db, exclude_child_id=None):
        """Si un enfant change d'alternance ou est supprimé, on recalcule celle de son parent."""
        if not self.parent_id:
            return
            
        parent = db.get(self.__class__, self.parent_id)
        if not parent:
            return
            
        children = [c for c in parent.children if c.id != exclude_child_id]
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
        if self.timeslot and self.parent.timeslot:
            # Même jour obligatoire
            if self.timeslot.day_of_week != self.parent.timeslot.day_of_week:
                raise ValueError("Le cours enfant doit être le même jour que son parent.")
            
            # Heure de début
            if self.timeslot.hour < self.parent.timeslot.hour:
                raise ValueError("Le début d'un cours enfant ne peut pas être antérieur au début du cours parent.")
            
            # Heure de fin
            child_end = self.timeslot.hour + (self.duration_minutes / 60.0)
            parent_end = self.parent.timeslot.hour + (self.parent.duration_minutes / 60.0)
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

        target_start = target_ts.hour * 60
        target_end = target_start + self.duration_minutes

        # Vérification du débordement en fin de journée
        from sqlalchemy import func
        from backend.app.models.system_setting import SystemSetting, SystemSettingKey
        max_hour = db.query(func.max(Timeslot.hour)).filter(Timeslot.day_of_week == target_ts.day_of_week).scalar()
        if max_hour is not None:
            setting = db.query(SystemSetting).filter(SystemSetting.key == SystemSettingKey.STANDARD_TIMESLOT_DURATION).first()
            if not setting or not setting.value:
                raise ValueError("Le paramètre système obligatoire 'STANDARD_TIMESLOT_DURATION' est manquant ou non défini.")
            std_duration_min = int(setting.value)
            absolute_end_minutes = (max_hour * 60) + std_duration_min
            if target_end > absolute_end_minutes:
                raise ValueError("Le cours déborde de la grille horaire de la journée.")

        target_week_type = getattr(self, 'week_type', 'W')

        
        def get_conflict_query(resource_filter):
            query = db.query(Course).join(Timeslot).filter(
                Course.id != self.id,
                resource_filter,
                Timeslot.day_of_week == target_ts.day_of_week,
                (Timeslot.hour * 60) < target_end,
                target_start < (Timeslot.hour * 60 + Course.duration_minutes)
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
                
            # Règle 3 : Orthogonalité Périodique
            target_period_id = getattr(self, 'period_id', None)
            if target_period_id:
                from backend.app.models.period import Period
                target_period = db.get(Period, target_period_id)
                if target_period:
                    query = query.outerjoin(Period, getattr(Course, 'period_id', None) == Period.id).filter(
                        or_(
                            getattr(Course, 'period_id', None) == None,
                            Period.period_type_id != target_period.period_type_id,
                            getattr(Course, 'period_id', None) == target_period.id
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
            offset = vals.get('parent_timeslot_offset', getattr(instance, 'parent_timeslot_offset', 0))
            vals['is_pinned'] = parent.is_pinned
            vals['timeslot_id'] = None
            
            if parent.timeslot_id:
                from backend.app.models.timeslot import Timeslot
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
        return instance

    def update(self, db: Session, vals: dict):
        # 1. Synchronisation avec le parent (si applicable)
        self.__class__._sync_vals_from_parent(db, vals, instance=self)
        
        # 3. Sauvegarde
        res = super().update(db, vals)
        
        # Recalculer son propre statut
        self.recompute_status()

        # 4. Si on a bougé, on propage le mouvement aux enfants en forçant leur recalcul
        if 'timeslot_id' in vals or 'is_pinned' in vals:
            for child in self.children:
                child.update(db, {})
                
        return res

    def delete(self, db: Session):
        parent_id = self.parent_id
        res = super().delete(db)
        if parent_id:
            parent = db.get(self.__class__, parent_id)
            if parent:
                parent._via_crud_mixin_update = True
                parent.recompute_status(exclude_child_id=self.id)
            self._sync_parent_week_type(db, exclude_child_id=self.id)
        return res

