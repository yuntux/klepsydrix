from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, Enum, UniqueConstraint, CheckConstraint
import enum
from backend.app.models.base import Base, constrains, onchange, CRUDMixin

class WeeklyOrderEnum(str, enum.Enum):
    NONE = "NONE"
    A_BEFORE_B = "a_before_b"
    B_BEFORE_A = "b_before_a"

class MaxSeparationEnum(str, enum.Enum):
    NONE = "NONE"
    SUCCESSIVE_DAYS = "successive_days"
    SUCCESSIVE_HALF_DAYS = "successive_half_days"

class GroupCourseOrderEnum(str, enum.Enum):
    NONE = "NONE"
    GROUP_BEFORE = "GROUP_BEFORE"
    GROUP_AFTER = "GROUP_AFTER"
    GROUP_BEFORE_OR_AFTER = "GROUP_BEFORE_OR_AFTER"
    GROUP_BEFORE_OR_AFTER_FORTNIGHT = "GROUP_BEFORE_OR_AFTER_FORTNIGHT"

class CourseToCourseConstraintType(str, enum.Enum):
    FORCE_SAME_SCOPE = 'FORCE_SAME_SCOPE'
    FORBID_SAME_SCOPE = 'FORBID_SAME_SCOPE'
    ORDER = 'ORDER'
    FORBID_CONSECUTIVE = 'FORBID_CONSECUTIVE'

class CourseToCourseConstraintScope(str, enum.Enum):
    SLOT = 'SLOT'
    DAY = 'DAY'
    HALF_DAY = 'HALF_DAY'
    QUINZAINE = 'QUINZAINE'
    CUSTOM_HALF_DAYS = 'CUSTOM_HALF_DAYS'

class ResourceConstraint(Base):
    __tablename__ = "resource_constraints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False) # 'Teacher', 'Division', 'Classroom', 'Site'
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False, info={"label": "ID ressource"})

    # Attributs Profs et Classes (Teacher / Division)
    max_hours_per_am: Mapped[Optional[float]] = mapped_column(Float, nullable=True, info={"min": 0, "label": "Heures max matin", "help": "Nombre maximum d'heures travaillées en matinée (avant 12h)."})
    max_hours_per_pm: Mapped[Optional[float]] = mapped_column(Float, nullable=True, info={"min": 0, "label": "Heures max après-midi", "help": "Nombre maximum d'heures travaillées l'après-midi (après 12h)."})
    max_presence_days_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"min": 0, "label": "Jours de présence max", "help": "Nombre maximum de jours de présence par semaine."})
    max_presence_hours_per_day: Mapped[Optional[float]] = mapped_column(Float, nullable=True, info={"min": 0, "label": "Amplitude horaire max par jour", "help": "Nombre maximum d'heures écoulées entre le premier et le dernier cours de la journée."})
    late_start_days_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"min": 0, "label": "Nombre de jours avec arrivée tardive", "help": "Garantit de ne pas commencer avant l'heure définie."})
    late_start_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True, info={"label": "Heure d'arrivée tardive", "help": "Heure minimum pour commencer, ex: 09:00", "placeholder": "09:00"})
    early_end_days_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"min": 0, "label": "Nombre de jours avec départ anticipé", "help": "Garantit de terminer au plus tard à l'heure définie."})
    early_end_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True, info={"label": "Heure de départ anticipé", "help": "Heure maximum pour terminer, ex: 16:30", "placeholder": "16:30"})
    min_free_days_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"min": 0, "label": "Jours libres garantis", "help": "Nombre minimum de jours sans aucun cours dans la semaine."})
    min_free_half_days_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"min": 0, "label": "Demi-journées libres garanties", "help": "Nombre minimum de demi-journées sans aucun cours dans la semaine."})
    max_worked_am_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"min": 0, "label": "Matins travaillés max", "help": "Nombre maximum de matinées avec au moins un cours."})
    max_worked_pm_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"min": 0, "label": "Après-midis travaillés max", "help": "Nombre maximum d'après-midis avec au moins un cours."})
    only_one_half_day_per_day: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, info={"label": "N'avoir cours qu'une demi-journée par jour", "help": "Si coché, la ressource ne travaillera jamais le matin et l'après-midi le même jour."})
    max_gap_hours_per_week: Mapped[Optional[int]] = mapped_column(Integer, default=2, info={"min": 0, "label": "Heures de trou tolérées par semaine", "help": "Nombre d'heures creuses tolérées entre deux cours sur une semaine complète."})

    # Attributs Site
    max_travel_trips_per_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"min": 0, "label": "Déplacements inter-sites max", "help": "Nombre maximum de changements de site autorisés par jour."})


from sqlalchemy import Table
subject_constraint_division_associations = Table(
    "subject_constraint_division_associations",
    Base.metadata,
    Column("constraint_id", Integer, ForeignKey("subject_to_subject_constraints.id", ondelete="CASCADE"), primary_key=True),
    Column("division_id", Integer, ForeignKey("divisions.id", ondelete="CASCADE"), primary_key=True),
)

class SubjectToSubjectConstraint(Base):
    __tablename__ = "subject_to_subject_constraints"
    __table_args__ = (UniqueConstraint('target_subject_a_id', 'target_subject_b_id', name='uix_subject_a_b'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    target_subject_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, info={"label": "Matière A"})
    target_subject_b_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, info={"label": "Matière B"})

    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Optionnelle", "help": "Si coché, la contrainte est traitée comme un vœu (soft) plutôt que stricte (hard)."})

    incompatible_same_half_day: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, info={"label": "Interdire la même demi-journée", "help": "Les deux matières ne peuvent pas avoir lieu lors de la même demi-journée."})
    incompatible_same_day: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, info={"label": "Interdire le même jour", "help": "Les deux matières ne peuvent pas avoir lieu le même jour."})
    incompatible_two_consecutive_days: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, info={"label": "Interdire sur 2 jours consécutifs", "help": "Les deux matières ne peuvent pas avoir lieu sur deux jours qui se suivent."})
    min_free_half_days_between: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"min": 0, "label": "Demi-journées d'écart minimum", "help": "Nombre entier de demi-journées qui doivent obligatoirement séparer les deux matières."})

    prevent_consecutive_a_then_b: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, info={"label": "Interdire B suivant A", "help": "La matière B ne doit jamais suivre immédiatement la matière A."})
    prevent_consecutive_b_then_a: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, info={"label": "Interdire A suivant B", "help": "La matière A ne doit jamais suivre immédiatement la matière B."})

    max_hours_per_day: Mapped[Optional[float]] = mapped_column(Float, nullable=True, info={"min": 0, "label": "Max heures par jour", "help": "Nombre maximum d'heures par jour pour cette ressource."})
    max_hours_per_half_day: Mapped[Optional[float]] = mapped_column(Float, nullable=True, info={"min": 0, "label": "Max heures par demi-journée", "help": "Nombre maximum d'heures par demi-journée pour cette ressource."})

    weekly_order: Mapped[Optional[WeeklyOrderEnum]] = mapped_column(Enum(WeeklyOrderEnum), default=WeeklyOrderEnum.NONE, info={"label": "Ordre hebdomadaire (A/B)", "help": "Séquencement imposé de A et B dans la même semaine.", "type": "select", "options": [{"label": "Aucun", "value": "NONE"}, {"label": "A avant B", "value": "a_before_b"}, {"label": "B avant A", "value": "b_before_a"}]})
    group_course_order: Mapped[Optional[GroupCourseOrderEnum]] = mapped_column(Enum(GroupCourseOrderEnum), default=GroupCourseOrderEnum.NONE, info={"label": "Ordre cours de groupe", "help": "Exigences de placement par rapport aux cours d'un groupe.", "type": "select", "options": [{"label": "Aucun", "value": "NONE"}, {"label": "Groupe avant", "value": "GROUP_BEFORE"}, {"label": "Groupe après", "value": "GROUP_AFTER"}, {"label": "Groupe aux extrémités", "value": "GROUP_BEFORE_OR_AFTER"}, {"label": "Extrémités (Quinzaine)", "value": "GROUP_BEFORE_OR_AFTER_FORTNIGHT"}]})
    max_separation: Mapped[Optional[MaxSeparationEnum]] = mapped_column(Enum(MaxSeparationEnum), default=MaxSeparationEnum.NONE, info={"label": "Espacement maximum (Même matière)", "help": "Empêche d'espacer deux cours d'une même matière de plus d'un certain seuil (ex: une demi-journée).", "type": "select", "options": [{"label": "Aucun", "value": "NONE"}, {"label": "Jours successifs", "value": "successive_days"}, {"label": "Demi-journées successives", "value": "successive_half_days"}]})

    target_subject_a: Mapped[Optional["Subject"]] = relationship("Subject", foreign_keys=[target_subject_a_id])
    target_subject_b: Mapped[Optional["Subject"]] = relationship("Subject", foreign_keys=[target_subject_b_id])
    divisions: Mapped[list["Division"]] = relationship(
        "Division",
        secondary=subject_constraint_division_associations,
        info={"label": "Classes concernées", "help": "Si vide, la contrainte s'applique à toutes les classes. Sinon, uniquement aux classes sélectionnées."}
    )

    @onchange('incompatible_same_half_day', 'incompatible_same_day', 'incompatible_two_consecutive_days', 'min_free_half_days_between')
    def _onchange_incompatibilities(self, changed_field=None):
        sep_fields = ['incompatible_same_half_day', 'incompatible_same_day', 'incompatible_two_consecutive_days', 'min_free_half_days_between']
        new_sep = changed_field if changed_field and getattr(self, changed_field) else None
        
        if not new_sep:
            for f in sep_fields:
                if getattr(self, f):
                    new_sep = f
                    break
                    
        if new_sep:
            for f in sep_fields:
                if f != new_sep:
                    setattr(self, f, False if f != 'min_free_half_days_between' else None)

    @onchange('prevent_consecutive_a_then_b', 'prevent_consecutive_b_then_a')
    def _onchange_consecutive(self):
        if self.target_subject_a_id is not None and self.target_subject_b_id is not None and self.target_subject_a_id == self.target_subject_b_id:
            # Sync the two
            if getattr(self, 'prevent_consecutive_a_then_b'):
                self.prevent_consecutive_b_then_a = True
            elif getattr(self, 'prevent_consecutive_b_then_a'):
                self.prevent_consecutive_a_then_b = True
            else:
                self.prevent_consecutive_a_then_b = False
                self.prevent_consecutive_b_then_a = False

    @onchange('target_subject_a_id', 'target_subject_b_id')
    def _onchange_targets(self):
        if self.target_subject_a_id is not None and self.target_subject_b_id is not None:
            if self.target_subject_a_id == self.target_subject_b_id:
                self.weekly_order = WeeklyOrderEnum.NONE
            else:
                self.group_course_order = GroupCourseOrderEnum.NONE
                self.max_separation = MaxSeparationEnum.NONE

    @classmethod
    def _apply_business_rules(cls, vals, is_update=False, current_obj=None):
        subject_a = vals.get('target_subject_a_id', current_obj.target_subject_a_id if current_obj else None)
        subject_b = vals.get('target_subject_b_id', current_obj.target_subject_b_id if current_obj else None)

        if subject_b is None:
            raise ValueError("target_subject_b_id est obligatoire.")


        sep_fields = ['incompatible_same_half_day', 'incompatible_same_day', 'incompatible_two_consecutive_days', 'min_free_half_days_between']
        new_sep = None
        for f in sep_fields:
            if f in vals and vals[f]:
                new_sep = f
                break
        
        if new_sep:
            for f in sep_fields:
                if f != new_sep:
                    vals[f] = False if f != 'min_free_half_days_between' else None
        
        if subject_a is not None and subject_b is not None and subject_a == subject_b:
            if 'prevent_consecutive_a_then_b' in vals:
                vals['prevent_consecutive_b_then_a'] = vals['prevent_consecutive_a_then_b']
            elif 'prevent_consecutive_b_then_a' in vals:
                vals['prevent_consecutive_a_then_b'] = vals['prevent_consecutive_b_then_a']
            
            vals['weekly_order'] = WeeklyOrderEnum.NONE
        else:
            vals['group_course_order'] = GroupCourseOrderEnum.NONE
            vals['max_separation'] = MaxSeparationEnum.NONE

    @classmethod
    def create(cls, db, vals):
        cls._apply_business_rules(vals)
        return super().create(db, vals)

    def update(self, db, vals):
        if 'target_subject_a_id' in vals and vals['target_subject_a_id'] != self.target_subject_a_id:
            raise ValueError("Il n'est pas possible de modifier les matières associées après création.")
        if 'target_subject_b_id' in vals and vals['target_subject_b_id'] != self.target_subject_b_id:
            raise ValueError("Il n'est pas possible de modifier les matières associées après création.")

        self._apply_business_rules(vals, is_update=True, current_obj=self)
        return super().update(db, vals)


course_constraint_associations = Table(
    "course_constraint_associations",
    Base.metadata,
    Column("constraint_id", Integer, ForeignKey("course_to_course_constraints.id", ondelete="CASCADE"), primary_key=True),
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("sequence_order", Integer, nullable=False, default=0)
)

class CourseToCourseConstraint(Base):
    __tablename__ = "course_to_course_constraints"
    __table_args__ = (
        CheckConstraint('custom_half_days > 0', name='check_custom_half_days_positive'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type: Mapped[CourseToCourseConstraintType] = mapped_column(
        Enum(CourseToCourseConstraintType), nullable=False,
        info={"label": "Type de contrainte", "type": "select", "options": [
            {"value": "FORCE_SAME_SCOPE", "label": "Forcer dans le même périmètre"},
            {"value": "FORBID_SAME_SCOPE", "label": "Interdire dans le même périmètre"},
            {"value": "ORDER", "label": "Imposer un ordre"},
            {"value": "FORBID_CONSECUTIVE", "label": "Interdire qu'ils soient consécutifs"}
        ]}
    )
    scope: Mapped[Optional[CourseToCourseConstraintScope]] = mapped_column(
        Enum(CourseToCourseConstraintScope), nullable=True, default=CourseToCourseConstraintScope.SLOT,
        info={"label": "Périmètre", "placeholder": "Ex: Journée, Demi-journée", "requiredExpr": "model.type === 'FORCE_SAME_SCOPE' || model.type === 'FORBID_SAME_SCOPE'", "invisibleExpr": "!(model.type === 'FORCE_SAME_SCOPE' || model.type === 'FORBID_SAME_SCOPE')", "type": "select", "options": [
            {"value": "SLOT", "label": "Même créneau"},
            {"value": "DAY", "label": "Même journée"},
            {"value": "HALF_DAY", "label": "Même demi-journée"},
            {"value": "QUINZAINE", "label": "Même quinzaine (A/B)"},
            {"value": "CUSTOM_HALF_DAYS", "label": "Fenêtre de N demi-journées"}
        ]}
    )
    custom_half_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        info={"label": "Nombre de demi-journées personnalisées", "placeholder": "Ex: 3", "min": 1, "requiredExpr": "model.scope === 'CUSTOM_HALF_DAYS'", "invisibleExpr": "model.scope !== 'CUSTOM_HALF_DAYS'"}
    )
    label: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        info={"label": "Libellé de la contrainte", "placeholder": "Ex: Pas de math après sport"}
    )
    is_optional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        info={"label": "Est optionnel", "description": "Si coché, la contrainte sera pénalisée sans empêcher la résolution."}
    )

    courses: Mapped[list["Course"]] = relationship(
        "Course",
        secondary=course_constraint_associations,
        order_by="course_constraint_associations.c.sequence_order",
        info={"label": "Cours concernés"}
    )

    @classmethod
    def _apply_business_rules(cls, vals, is_update=False, current_obj=None):
        ctype = vals.get('type', current_obj.type if current_obj else None)
        cscope = vals.get('scope', current_obj.scope if current_obj else None)
        chalf_days = vals.get('custom_half_days', current_obj.custom_half_days if current_obj else None)

        if ctype in [CourseToCourseConstraintType.FORCE_SAME_SCOPE, CourseToCourseConstraintType.FORBID_SAME_SCOPE] or ctype in ['FORCE_SAME_SCOPE', 'FORBID_SAME_SCOPE']:
            if not cscope:
                raise ValueError("Le périmètre (scope) est obligatoire pour les types FORCE_SAME_SCOPE et FORBID_SAME_SCOPE.")
        else:
            if cscope:
                raise ValueError("Le périmètre (scope) est interdit pour ce type de contrainte.")
            vals['scope'] = None

        if cscope == CourseToCourseConstraintScope.CUSTOM_HALF_DAYS or cscope == 'CUSTOM_HALF_DAYS':
            if not chalf_days:
                raise ValueError("Le nombre de demi-journées personnalisées est obligatoire lorsque le périmètre est CUSTOM_HALF_DAYS.")
        else:
            vals['custom_half_days'] = None

    @classmethod
    def create(cls, db, vals):
        cls._apply_business_rules(vals)
        return super().create(db, vals)

    def update(self, db, vals):
        if 'type' in vals and vals['type'] != self.type:
            raise ValueError("Il n'est pas possible de modifier le type après création.")
        if 'scope' in vals and vals['scope'] != self.scope:
            raise ValueError("Il n'est pas possible de modifier le périmètre (scope) après création.")

        self._apply_business_rules(vals, is_update=True, current_obj=self)
        return super().update(db, vals)
