from datetime import date, datetime, time
from typing import Optional, Any
import enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, String, Integer, Enum
from backend.app.models.base import Base

class SystemSettingKey(str, enum.Enum):
    STANDARD_TIMESLOT_DURATION = "STANDARD_TIMESLOT_DURATION"
    DIVISION_PART_NAME_HAS_DIV_CODE = "DIVISION_PART_NAME_HAS_DIV_CODE"
    DIVISION_PART_NAME_HAS_SUBJECT_CODE = "DIVISION_PART_NAME_HAS_SUBJECT_CODE"
    DIVISION_PART_NAME_SEPARATOR = "DIVISION_PART_NAME_SEPARATOR"
    DIVISION_PART_NAME_NUMBER_FORMAT = "DIVISION_PART_NAME_NUMBER_FORMAT"
    GROUP_NAME_HAS_DIV_CODE = "GROUP_NAME_HAS_DIV_CODE"
    GROUP_NAME_HAS_SUBJECT_CODE = "GROUP_NAME_HAS_SUBJECT_CODE"
    GROUP_NAME_SEPARATOR = "GROUP_NAME_SEPARATOR"
    GROUP_NAME_NUMBER_FORMAT = "GROUP_NAME_NUMBER_FORMAT"
    MUTUALIZE_REDUCED_GROUPS_WITHOUT_ALIGNMENT = "MUTUALIZE_REDUCED_GROUPS_WITHOUT_ALIGNMENT"

SETTING_LABELS = {
    SystemSettingKey.STANDARD_TIMESLOT_DURATION: "Durée minimale d'un créneau (en minutes)",
    SystemSettingKey.DIVISION_PART_NAME_HAS_DIV_CODE: "[Nommage parties de classe] : intégrer le code classe",
    SystemSettingKey.DIVISION_PART_NAME_HAS_SUBJECT_CODE: "[Nommage parties de classe] : intégrer le code matière",
    SystemSettingKey.DIVISION_PART_NAME_SEPARATOR: "[Nommage parties de classe] : séparateur",
    SystemSettingKey.DIVISION_PART_NAME_NUMBER_FORMAT: "[Nommage parties de classe] : type numérotation",
    SystemSettingKey.GROUP_NAME_HAS_DIV_CODE: "[Nommage groupe] : intégrer la première lettre du code classe",
    SystemSettingKey.GROUP_NAME_HAS_SUBJECT_CODE: "[Nommage groupe] : intégrer le code matière",
    SystemSettingKey.GROUP_NAME_SEPARATOR: "[Nommage groupe] : séparateur",
    SystemSettingKey.GROUP_NAME_NUMBER_FORMAT: "[Nommage groupe] : type numérotation",
    SystemSettingKey.MUTUALIZE_REDUCED_GROUPS_WITHOUT_ALIGNMENT: "Mutualiser les groupes à effectif réduit même sans alignement formel",
}

# Valeurs autorisées pour les paramètres de type "liste déroulante" (*_NUMBER_FORMAT)
NUMBER_FORMAT_ALPHABETIC = "alphabetique"
NUMBER_FORMAT_NUMERIC = "numerique"
NUMBER_FORMAT_CHOICES = [NUMBER_FORMAT_ALPHABETIC, NUMBER_FORMAT_NUMERIC]

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[Any] = mapped_column(Enum(SystemSettingKey, native_enum=False), index=True, unique=True, nullable=False, info={
        "label": "Paramètre système", 
        "type": "select",
        "options": [
            {"value": k.value, "label": SETTING_LABELS.get(k, k.value)}
            for k in SystemSettingKey
        ]
    })
    value: Mapped[str] = mapped_column(String(255), nullable=False, info={"label": "Valeur", "placeholder": "ex: 30", "widget": "system_setting_value"})

    @classmethod
    def get_system_setting_value(cls, db, key: str) -> str:
        setting = db.query(cls).filter(cls.key == key).first()
        if key == "STANDARD_TIMESLOT_DURATION":
            if not setting or not setting.value or not setting.value.isdigit():
                raise ValueError("Le paramètre système STANDARD_TIMESLOT_DURATION est manquant ou invalide.")
        return setting.value if setting else None

    def delete(self, db):
        if self.key == SystemSettingKey.STANDARD_TIMESLOT_DURATION:
            raise ValueError("Il est impossible de supprimer le paramètre système 'STANDARD_TIMESLOT_DURATION'.")
        return super().delete(db)

    def update(self, db, vals: dict):
        if self.key == SystemSettingKey.STANDARD_TIMESLOT_DURATION and 'value' in vals and str(vals['value']) != str(self.value):
            new_val = str(vals['value'])
            if not new_val.isdigit() or not (5 <= int(new_val) <= 60):
                raise ValueError("La durée standard d'un créneau doit être un entier compris entre 5 et 60 minutes.")
                
            old_duration = int(self.value) if self.value.isdigit() else 30
            new_duration = int(new_val)

            from backend.app.models.course import Course

            # 1. Si on augmente la durée, on vérifie d'abord qu'aucun cours n'est placé sur un créneau qui deviendrait hors-grille
            if new_duration > old_duration:
                from backend.app.models.timeslot import Timeslot
                new_step = new_duration / 60.0
                # On inspecte les cours qui ont un timeslot assigné
                for c in db.query(Course).join(Timeslot).filter(Course.timeslot_id != None).all():
                    if abs((c.timeslot.hour / new_step) - round(c.timeslot.hour / new_step)) >= 0.001:
                        raise ValueError(
                            f"Modification interdite : le cours (ID {c.id}) est positionné sur un créneau "
                            f"({c.timeslot.hour}h) qui n'est pas un multiple de {new_duration} minutes."
                        )

            # 2. Ensuite, on vérifie et on recalcule les offsets relatifs des cours enfants
            courses_with_offset = db.query(Course).filter(Course.parent_timeslot_offset > 0).all()
            for course in courses_with_offset:
                offset_minutes = course.parent_timeslot_offset * old_duration
                if offset_minutes % new_duration != 0:
                    raise ValueError(
                        f"Modification interdite : le cours complexe (ID {course.id}) a un décalage de "
                        f"{offset_minutes} minutes, ce qui n'est pas un multiple de la nouvelle durée ({new_duration}m)."
                    )
                course.parent_timeslot_offset = offset_minutes // new_duration
                
        return super().update(db, vals)
