from sqlalchemy import Column, String, Integer
from backend.app.models.base import Base

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), index=True, unique=True, nullable=False, info={"label": "Clé du paramètre", "placeholder": "ex: STANDARD_TIMESLOT_DURATION"})
    value = Column(String(255), nullable=False, info={"label": "Valeur", "placeholder": "ex: 30"})

    def delete(self, db):
        if self.key == "STANDARD_TIMESLOT_DURATION":
            raise ValueError("Il est impossible de supprimer le paramètre système 'STANDARD_TIMESLOT_DURATION'.")
        return super().delete(db)

    def update(self, db, vals: dict):
        if self.key == "STANDARD_TIMESLOT_DURATION" and 'value' in vals and str(vals['value']) != str(self.value):
            new_val = str(vals['value'])
            if not new_val.isdigit() or int(new_val) <= 0:
                raise ValueError("La durée standard d'un créneau doit être un entier positif (en minutes).")
                
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
