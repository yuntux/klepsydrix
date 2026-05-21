from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, select, Enum, Table, event
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from backend.app.models.base import Base
from backend.app.models.preference import WeekType

course_teachers = Table(
    "course_teachers",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("teacher_id", Integer, ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True)
)

course_classrooms = Table(
    "course_classrooms",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("classroom_id", Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), primary_key=True)
)

course_non_teaching_staffs = Table(
    "course_non_teaching_staffs",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("non_teaching_staff_id", Integer, ForeignKey("non_teaching_staffs.id", ondelete="CASCADE"), primary_key=True)
)

course_materials = Table(
    "course_materials",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("material_id", Integer, ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True)
)

course_divisions = Table(
    "course_divisions",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("division_id", Integer, ForeignKey("divisions.id", ondelete="CASCADE"), primary_key=True)
)

course_class_parts = Table(
    "course_class_parts",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("class_part_id", Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), primary_key=True)
)

course_groups = Table(
    "course_groups",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
)

class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=True)
    
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    
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
        """Vérifie qu'un cours enfant respecte les limites de temps et de ressources de son parent."""
        if not self.parent:
            return

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
            child.parent_id = None
            
        db.delete(self)
        db.commit()

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

        # Création du cours parent englobant
        parent = cls(
            is_complex=True,
            subject_id=first_course.subject_id, # On hérite du sujet du premier
            school_id=first_course.school_id,
            duration_minutes=max(c.duration_minutes for c in courses), # On prend la durée max par défaut
            week_type=first_course.week_type
        )
        db.add(parent)
        db.flush()

        for c in courses:
            c.parent_id = parent.id
            
            # Alimentation des ressources du parent (Union)
            for res_list, parent_res_list in [
                (c.teachers, parent.teachers),
                (c.non_teaching_staffs, parent.non_teaching_staffs),
                (c.classrooms, parent.classrooms),
                (c.divisions, parent.divisions),
                (c.groups, parent.groups),
                (c.materials, parent.materials),
                (c.class_parts, parent.class_parts),
            ]:
                for item in res_list:
                    if item not in parent_res_list:
                        parent_res_list.append(item)

        db.commit()
        return parent


def validate_course_child_constraints_listener(mapper, connection, target):
    # 1. Si on modifie un enfant, il doit respecter son parent
    target.validate_child_constraints()
    
    # 2. Si on modifie un parent, tous ses enfants existants doivent continuer à le respecter
    if target.children:
        for child in target.children:
            child.validate_child_constraints()

event.listen(Course, 'before_insert', validate_course_child_constraints_listener)
event.listen(Course, 'before_update', validate_course_child_constraints_listener)
