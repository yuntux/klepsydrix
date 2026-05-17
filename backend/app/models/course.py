from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, select
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from backend.app.models.base import Base

class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)
    division_id = Column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=True)
    
    duration_minutes = Column(Integer, nullable=False, default=55)
    label = Column(String(100), nullable=True)
    memo = Column(Text, nullable=True)
    is_complex = Column(Boolean, nullable=False, default=False)
    lock_sessions = Column(Boolean, nullable=False, default=False)
    
    mission_id = Column(Integer, ForeignKey("missions.id", ondelete="SET NULL"), nullable=True)
    election_method_id = Column(Integer, ForeignKey("election_methods.id", ondelete="SET NULL"), nullable=True)
    family_id = Column(Integer, ForeignKey("families.id", ondelete="SET NULL"), nullable=True)
    school_id = Column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False)

    # Relations de navigation
    subject_relation = relationship("Subject", back_populates="courses")
    teacher = relationship("Teacher", back_populates="courses")
    division = relationship("Division", back_populates="courses")
    group = relationship("Group", back_populates="courses")
    mission = relationship("Mission", back_populates="courses")
    election_method = relationship("ElectionMethod", back_populates="courses")
    family = relationship("Family", back_populates="courses")
    school = relationship("School", back_populates="courses")
    
    sessions = relationship("Session", back_populates="course", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        # Intercepter le sujet s'il est fourni sous forme de chaîne
        subj_val = kwargs.pop("subject", None)
        
        # Intercepter les colonnes de planification V1 pour les rediriger vers la session
        timeslot_val = kwargs.pop("timeslot_id", None)
        classroom_val = kwargs.pop("classroom_id", None)
        is_pinned_val = kwargs.pop("is_pinned", False)
        
        super().__init__(**kwargs)
        
        # Gérer la matière s'il s'agit d'une chaîne
        if subj_val is not None:
            if isinstance(subj_val, str):
                self._subject_str = subj_val
            else:
                self.subject_relation = subj_val
                
        # Gérer la session par défaut
        from backend.app.models.session import Session as DbSession
        session = DbSession(
            timeslot_id=timeslot_val,
            classroom_id=classroom_val,
            is_pinned=is_pinned_val,
            school_id=self.school_id if getattr(self, 'school_id', None) else 1,
            week_type="T"
        )
        self.sessions.append(session)

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

    @hybrid_property
    def timeslot_id(self):
        return self.sessions[0].timeslot_id if self.sessions else None

    @timeslot_id.setter
    def timeslot_id(self, value):
        if not self.sessions:
            from backend.app.models.session import Session as DbSession
            session = DbSession(course_id=self.id, school_id=self.school_id if getattr(self, 'school_id', None) else 1, week_type="T")
            self.sessions.append(session)
        self.sessions[0].timeslot_id = value

    @timeslot_id.expression
    def timeslot_id(cls):
        from backend.app.models.session import Session as DbSession
        return select(DbSession.timeslot_id).where(DbSession.course_id == cls.id).correlate_except(DbSession).scalar_subquery()

    @hybrid_property
    def classroom_id(self):
        return self.sessions[0].classroom_id if self.sessions else None

    @classroom_id.setter
    def classroom_id(self, value):
        if not self.sessions:
            from backend.app.models.session import Session as DbSession
            session = DbSession(course_id=self.id, school_id=self.school_id if getattr(self, 'school_id', None) else 1, week_type="T")
            self.sessions.append(session)
        self.sessions[0].classroom_id = value

    @classroom_id.expression
    def classroom_id(cls):
        from backend.app.models.session import Session as DbSession
        return select(DbSession.classroom_id).where(DbSession.course_id == cls.id).correlate_except(DbSession).scalar_subquery()

    @hybrid_property
    def is_pinned(self):
        return self.sessions[0].is_pinned if self.sessions else False

    @is_pinned.setter
    def is_pinned(self, value):
        if not self.sessions:
            from backend.app.models.session import Session as DbSession
            session = DbSession(course_id=self.id, school_id=self.school_id if getattr(self, 'school_id', None) else 1, week_type="T")
            self.sessions.append(session)
        self.sessions[0].is_pinned = value

    @is_pinned.expression
    def is_pinned(cls):
        from backend.app.models.session import Session as DbSession
        return select(DbSession.is_pinned).where(DbSession.course_id == cls.id).correlate_except(DbSession).scalar_subquery()
