from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, select, Enum, Table, event
from sqlalchemy.orm import relationship, Session
from sqlalchemy.ext.hybrid import hybrid_property
from backend.app.models.base import Base
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

    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=True)
    
    # Pour les cours simples, un subject_id est requis. Pour les cours complexes (parents), il peut être NULL.
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=True)
    
    # Placements et attributs directs
    timeslot_id = Column(Integer, ForeignKey("timeslots.id", ondelete="SET NULL"), nullable=True)
    is_pinned = Column(Boolean, nullable=False, default=False)
    week_type = Column(Enum(WeekType, name="course_week_type_enum"), nullable=False, default=WeekType.W)
    is_co_teaching = Column(Boolean, nullable=False, default=False)
    
    duration_minutes = Column(Integer, nullable=False, default=55)
    label = Column(String(100), nullable=True)
    memo = Column(Text, nullable=True)
    is_complex = Column(Boolean, nullable=False, default=False)
    lock_sessions = Column(Boolean, nullable=False, default=False)
    
    mission_id = Column(Integer, ForeignKey("missions.id", ondelete="SET NULL"), nullable=True)
    election_method_id = Column(Integer, ForeignKey("election_methods.id", ondelete="SET NULL"), nullable=True)
    family_id = Column(Integer, ForeignKey("families.id", ondelete="SET NULL"), nullable=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)

    # Relations de navigation hiérarchique
    parent = relationship("Course", back_populates="children", remote_side=[id])
    children = relationship("Course", back_populates="parent", cascade="all, delete-orphan")

    # Relations de navigation Mto1
    subject_relation = relationship("Subject", back_populates="courses")
    timeslot = relationship("Timeslot")
    mission = relationship("Mission", back_populates="courses")
    election_method = relationship("ElectionMethod", back_populates="courses")
    family = relationship("Family", back_populates="courses")
    school = relationship("School", back_populates="courses")
    
    # Ressources N..N pures
    teachers = relationship("Teacher", secondary=course_teachers, back_populates="courses")
    non_teaching_staffs = relationship("NonTeachingStaff", secondary=course_non_teaching_staffs, back_populates="courses")
    classrooms = relationship("Classroom", secondary=course_classrooms)
    materials = relationship("Material", secondary=course_materials)
    divisions = relationship("Division", secondary=course_divisions, back_populates="courses")
    class_parts = relationship("ClassPart", secondary=course_class_parts)
    groups = relationship("Group", secondary=course_groups, back_populates="courses")

    def __init__(self, **kwargs):
        subj_val = kwargs.pop("subject", None)
        super().__init__(**kwargs)
        if subj_val is not None:
            if isinstance(subj_val, str):
                self._subject_str = subj_val
            else:
                self.subject_relation = subj_val

    @hybrid_property
    def subject(self):
        if self.subject_relation:
            return self.subject_relation.short_label
        return getattr(self, "_subject_str", "Cours")

    @subject.setter
    def subject(self, value):
        if isinstance(value, str):
            self._subject_str = value
        else:
            self.subject_relation = value

    @subject.expression
    def subject(cls):
        from backend.app.models.subject import Subject
        return select(Subject.short_label).where(Subject.id == cls.subject_id).correlate_except(Subject).scalar_subquery()

    @property
    def effective_week_type(self) -> str:
        """Retourne le week_type effectif du cours."""
        if not self.children:
            wt = self.week_type
            return wt.value if hasattr(wt, "value") else (wt or "W")
        types = {
            (c.week_type.value if hasattr(c.week_type, "value") else c.week_type)
            for c in self.children
            if c.week_type
        }
        if types == {"A"}:
            return "A"
        if types == {"B"}:
            return "B"
        return "W"

    def validate_child_constraints(self):
        """Vérifie qu'un cours enfant respecte les limites de temps, de ressources et de profondeur."""
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
        if not self.is_complex:
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
            'is_complex': True,
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

    def validate_placement_conflicts(self, db, vals):
        target_ts_id = vals.get('timeslot_id', self.timeslot_id)
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

        target_week_type = vals.get('week_type', getattr(self, 'week_type', 'W'))
        
        def get_conflict_query(resource_filter):
            query = db.query(Course).join(Timeslot).filter(
                Course.id != self.id,
                resource_filter,
                Timeslot.day_of_week == target_ts.day_of_week,
                (Timeslot.hour * 60) < target_end,
                target_start < (Timeslot.hour * 60 + Course.duration_minutes)
            )
            if target_week_type == 'A':
                query = query.filter(Course.week_type.in_(['A', 'W']))
            elif target_week_type == 'B':
                query = query.filter(Course.week_type.in_(['B', 'W']))
            return query

        t_ids = vals.get('teacher_ids', [t.id for t in self.teachers])
        if t_ids:
            if get_conflict_query(Course.teachers.any(Teacher.id.in_(t_ids))).first():
                raise ValueError("Conflit : L'enseignant est déjà occupé sur ce créneau (chevauchement)")

        s_ids = vals.get('non_teaching_staff_ids', [s.id for s in self.non_teaching_staffs])
        if s_ids:
            if get_conflict_query(Course.non_teaching_staffs.any(NonTeachingStaff.id.in_(s_ids))).first():
                raise ValueError("Conflit : Le membre du personnel est déjà occupé sur ce créneau (chevauchement)")

        c_ids = vals.get('classroom_ids', [c.id for c in self.classrooms])
        if c_ids:
            if get_conflict_query(Course.classrooms.any(Classroom.id.in_(c_ids))).first():
                raise ValueError("Conflit : La salle est déjà occupée sur ce créneau (chevauchement)")

        d_ids = vals.get('division_ids', [d.id for d in self.divisions])
        if d_ids:
            if get_conflict_query(Course.divisions.any(Division.id.in_(d_ids))).first():
                raise ValueError("Conflit : La division est déjà occupée sur ce créneau (chevauchement)")

    @classmethod
    def _inherit_parent_placement(cls, db, vals: dict) -> dict:
        """Méthode utilitaire commune : si parent_id est présent dans vals,
        copie le timeslot_id et is_pinned du parent dans vals.
        La vérification de profondeur est déléguée à validate_child_constraints via l'event SQLAlchemy."""
        parent_id = vals.get('parent_id')
        if parent_id:
            parent = db.query(cls).filter(cls.id == parent_id).first()
            if parent:
                vals['timeslot_id'] = parent.timeslot_id
                vals['is_pinned'] = parent.is_pinned
        return vals

    @classmethod
    def create(cls, db: Session, vals: dict):
        """Surcharge : hérite du placement du parent si nécessaire."""
        cls._inherit_parent_placement(db, vals)
        # Validation requires an instance, so we check after creation (or create a dummy instance)
        # Let's create it and then validate (if invalid, db.flush will roll back or we raise ValueError before commit)
        instance = super().create(db, vals)
        instance.validate_placement_conflicts(db, vals)
        return instance

    def update(self, db: Session, vals: dict):
        """Surcharge : hérite du placement lors d'un rattachement et propage aux enfants."""
        self.__class__._inherit_parent_placement(db, vals)
        self.validate_placement_conflicts(db, vals)

        res = super().update(db, vals)
        
        if 'timeslot_id' in vals or 'is_pinned' in vals:
            child_vals = {k: vals[k] for k in ('timeslot_id', 'is_pinned') if k in vals}
            for child in self.children:
                child.update(db, child_vals)
                
        return res


def validate_course_child_constraints_listener(mapper, connection, target):
    # 1. Si on modifie un enfant, il doit respecter son parent
    target.validate_child_constraints()
    
    # 2. Si on modifie un parent, tous ses enfants existants doivent continuer à le respecter
    if target.children:
        for child in target.children:
            child.validate_child_constraints()

event.listen(Course, 'before_insert', validate_course_child_constraints_listener)
event.listen(Course, 'before_update', validate_course_child_constraints_listener)
