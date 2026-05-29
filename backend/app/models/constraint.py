from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum
from backend.app.models.base import Base, constrains, CRUDMixin

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

# Table de jointure pour ResourceConstraint <-> Division (périmètre de classes)
from sqlalchemy import Table
resource_constraint_division_associations = Table(
    "resource_constraint_division_associations",
    Base.metadata,
    Column("constraint_id", Integer, ForeignKey("resource_constraints.id", ondelete="CASCADE"), primary_key=True),
    Column("division_id", Integer, ForeignKey("divisions.id", ondelete="CASCADE"), primary_key=True),
)

class ResourceConstraint(Base):
    __tablename__ = "resource_constraints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False) # 'Subject', 'Teacher', 'Division', 'Classroom', 'Site'
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False, info={"label": "ID ressource"})
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, info={"label": "Optionnelle", "help": "Si coché, la contrainte est traitée comme un vœu (soft) plutôt que stricte (hard)."})

    # Attributs Matières (Subject)
    target_subject_b_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=True, info={"label": "Matière cible (B)", "help": "La seconde matière impliquée dans la contrainte."})

    # Incompatibilités
    incompatible_same_half_day: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, info={"label": "Interdire la même demi-journée", "help": "Les deux matières ne peuvent pas avoir lieu lors de la même demi-journée."})
    incompatible_same_day: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, info={"label": "Interdire le même jour", "help": "Les deux matières ne peuvent pas avoir lieu le même jour."})
    incompatible_two_consecutive_days: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, info={"label": "Interdire sur 2 jours consécutifs", "help": "Les deux matières ne peuvent pas avoir lieu sur deux jours qui se suivent."})
    min_free_half_days_between: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"min": 0, "label": "Demi-journées d'écart minimum", "help": "Nombre entier de demi-journées qui doivent obligatoirement séparer les deux matières."})

    # Empêchement de consécutivité
    prevent_consecutive_a_then_b: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, info={"label": "Interdire B suivant A", "help": "La matière B ne doit jamais suivre immédiatement la matière A."})
    prevent_consecutive_b_then_a: Mapped[Optional[bool]] = mapped_column(Boolean, default=False, info={"label": "Interdire A suivant B", "help": "La matière A ne doit jamais suivre immédiatement la matière B."})

    # Horaires maximum
    max_hours_per_day: Mapped[Optional[float]] = mapped_column(Float, nullable=True, info={"min": 0, "label": "Max heures par jour", "help": "Nombre maximum d'heures par jour pour cette ressource."})
    max_hours_per_half_day: Mapped[Optional[float]] = mapped_column(Float, nullable=True, info={"min": 0, "label": "Max heures par demi-journée", "help": "Nombre maximum d'heures par demi-journée pour cette ressource."})

    # Ordre hebdomadaire (A/B)
    weekly_order: Mapped[Optional[WeeklyOrderEnum]] = mapped_column(Enum(WeeklyOrderEnum), default=WeeklyOrderEnum.NONE, info={"label": "Ordre hebdomadaire (A/B)", "help": "Séquencement imposé de A et B dans la même semaine."})
    
    # Ordre cours de groupe
    group_course_order: Mapped[Optional[GroupCourseOrderEnum]] = mapped_column(Enum(GroupCourseOrderEnum), default=GroupCourseOrderEnum.NONE, info={"label": "Ordre cours de groupe", "help": "Exigences de placement par rapport aux cours d'un groupe."})
    max_separation: Mapped[Optional[MaxSeparationEnum]] = mapped_column(Enum(MaxSeparationEnum), default=MaxSeparationEnum.NONE, info={"label": "Espacement maximum (Même matière)", "help": "Empêche d'espacer deux cours d'une même matière de plus d'un certain seuil (ex: une demi-journée)."})

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

    # Navigation
    target_subject_b: Mapped[Optional["Subject"]] = relationship("Subject", foreign_keys=[target_subject_b_id])
    divisions: Mapped[list["Division"]] = relationship(
        "Division",
        secondary=resource_constraint_division_associations,
        info={"label": "Classes concernées", "help": "Si vide, la contrainte s'applique à toutes les classes. Sinon, uniquement aux classes sélectionnées."}
    )

    @classmethod
    def _apply_business_rules(cls, vals, is_update=False, current_obj=None):
        res_type = vals.get('resource_type', current_obj.resource_type if current_obj else None)
        res_id = vals.get('resource_id', current_obj.resource_id if current_obj else None)
        tgt_id = vals.get('target_subject_b_id', current_obj.target_subject_b_id if current_obj else None)

        if res_type == "Subject":
            # Rule 1: Cible Obligatoire
            if tgt_id is None:
                raise ValueError("target_subject_b_id est obligatoire pour les contraintes de matière (Subject).")

            # Rule 2: Immuabilité
            if is_update and current_obj:
                if 'resource_id' in vals and vals['resource_id'] != current_obj.resource_id:
                    raise ValueError("Il n'est pas possible de modifier resource_id après création.")
                if 'target_subject_b_id' in vals and vals['target_subject_b_id'] != current_obj.target_subject_b_id:
                    raise ValueError("Il n'est pas possible de modifier target_subject_b_id après création.")

            # Rule 3: Exclusivity of separation constraints
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
            
            # Rule 4, 5: Same subject
            if res_id is not None and tgt_id is not None and res_id == tgt_id:
                # Rule 4: Sync consecutive
                if 'prevent_consecutive_a_then_b' in vals:
                    vals['prevent_consecutive_b_then_a'] = vals['prevent_consecutive_a_then_b']
                elif 'prevent_consecutive_b_then_a' in vals:
                    vals['prevent_consecutive_a_then_b'] = vals['prevent_consecutive_b_then_a']
                elif current_obj:
                    # Sync missing keys from current object if one is updated implicitly
                    pass
                
                # Rule 5: No weekly order
                vals['weekly_order'] = WeeklyOrderEnum.NONE
            else:
                # Rule 7: Different subjects
                vals['group_course_order'] = GroupCourseOrderEnum.NONE
                vals['max_separation'] = MaxSeparationEnum.NONE
        else:
            # Rule 8: Optionnalité restreinte (seulement pour Subject)
            if vals.get('is_optional') is True:
                raise ValueError("L'attribut is_optional ne peut être vrai que pour les contraintes de type Subject.")
            vals['is_optional'] = False
            # Rule 9: division_ids uniquement pour Subject
            if 'division_ids' in vals and vals['division_ids']:
                raise ValueError("Le champ divisions n'est applicable qu'aux contraintes de type Subject.")
            vals['division_ids'] = []

    @classmethod
    def create(cls, db, vals):
        cls._apply_business_rules(vals)
        return super().create(db, vals)

    def update(self, db, vals):
        self._apply_business_rules(vals, is_update=True, current_obj=self)
        return super().update(db, vals)
        
    @constrains("resource_type", "target_subject_b_id")
    def _check_target_subject_mandatory(self, db):
        if self.resource_type == "Subject" and self.target_subject_b_id is None:
            raise ValueError("target_subject_b_id est obligatoire pour les contraintes de matière (Subject).")


# Table de jointure pour CourseToCourseConstraint <-> Course
from sqlalchemy import Table
course_constraint_associations = Table(
    "course_constraint_associations",
    Base.metadata,
    Column("constraint_id", Integer, ForeignKey("course_to_course_constraints.id", ondelete="CASCADE"), primary_key=True),
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("sequence_order", Integer, nullable=False, default=0)
)


class CourseToCourseConstraint(Base):
    __tablename__ = "course_to_course_constraints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False) # 'FORCE_SAME_SCOPE', 'FORBID_SAME_SCOPE', 'ORDER', 'FORBID_CONSECUTIVE'
    scope: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="SLOT") # 'SLOT', 'DAY', 'HALF_DAY', 'QUINZAINE', 'CUSTOM_HALF_DAYS'
    custom_half_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    courses: Mapped[list["Course"]] = relationship(
        "Course",
        secondary=course_constraint_associations,
        order_by="course_constraint_associations.c.sequence_order",
        info={"label": "Cours concernés"}
    )


