from datetime import date, datetime, time
from typing import Optional, Any
import enum
from typing import List
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint, Table, Enum
from sqlalchemy.orm import relationship
from backend.app.models.base import Base

class WeekType(str, enum.Enum):
    A = "A"
    B = "B"
    W = "W"

# Table de jointure Many-to-Many pour Preference <-> Period
preference_periods = Table(
    "preference_periods",
    Base.metadata,
    Column("preference_id", Integer, ForeignKey("resource_preferences.id", ondelete="CASCADE"), primary_key=True),
    Column("period_id", Integer, ForeignKey("periods.id", ondelete="CASCADE"), primary_key=True)
)

class ResourcePreference(Base):
    __tablename__ = "resource_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False) # 'Teacher', 'Classroom', 'Division', 'Subject', 'Group', 'Material'
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    timeslot_id: Mapped[int] = mapped_column(Integer, ForeignKey("timeslots.id", ondelete="CASCADE"), nullable=False)
    preference_level: Mapped[str] = mapped_column(String(15), nullable=False) # 'Unsuited', 'Undesirable', 'Preferred', 'Neutral'
    week_type: Mapped[Any] = mapped_column(Enum(WeekType, name="week_type_enum"), nullable=False, default=WeekType.W) # 'A', 'B', 'W'

    # Navigation
    timeslot: Mapped[Optional["Timeslot"]] = relationship("Timeslot")
    periods: Mapped[list["Period"]] = relationship("Period", secondary=preference_periods)

    @classmethod
    def create(cls, db: "Session", vals: dict):
        """
        Surcharge de create pour implémenter l'upsert, la scission et le nettoyage Neutral.
        """
        level = vals.get("preference_level")
        resource_type = vals.get("resource_type")
        resource_id = vals.get("resource_id")
        timeslot_id = vals.get("timeslot_id")
        week_type = vals.get("week_type", "W")
        period_ids = vals.get("period_ids", [])
        if resource_type == "Course":
            from backend.app.models.course import Course
            course = db.query(Course).filter_by(id=resource_id).first()
            if course:
                week_type = course.week_type
                period_ids = [course.period_id] if course.period_id else []
        is_annual = not period_ids

        # 1. Récupérer toutes les préférences existantes pour ce créneau/ressource
        existings = db.query(cls).filter(
            cls.resource_type == resource_type,
            cls.resource_id == resource_id,
            cls.timeslot_id == timeslot_id
        ).all()

        # 2. Déterminer si un type de période est concerné
        from backend.app.models.period import Period
        period_type_id = None
        school_id = None

        # Récupérer le school_id de la ressource
        if resource_type == "Teacher":
            from backend.app.models.teacher import Teacher
            res = db.query(Teacher).filter_by(id=resource_id).first()
            if res:
                school_id = res.school_id
        elif resource_type == "Classroom":
            from backend.app.models.classroom import Classroom
            res = db.query(Classroom).filter_by(id=resource_id).first()
            if res:
                school_id = res.school_id
        elif resource_type == "Division":
            from backend.app.models.division import Division
            res = db.query(Division).filter_by(id=resource_id).first()
            if res:
                school_id = res.school_id
        elif resource_type == "Course":
            from backend.app.models.course import Course
            res = db.query(Course).filter_by(id=resource_id).first()
            if res:
                school_id = res.school_id

        if period_ids:
            first_p = db.query(Period).filter(Period.id == period_ids[0]).first()
            if first_p:
                period_type_id = first_p.period_type_id
        else:
            for ext in existings:
                if ext.periods:
                    period_type_id = ext.periods[0].period_type_id
                    break

        # 3. Évaluation de la grille et reconstruction
        final_prefs = [] # liste de tuples (w, lvl, list_of_pids)

        if school_id and period_type_id:
            # On a des périodes spécifiques d'un type donné
            type_periods = db.query(Period).filter_by(
                school_id=school_id,
                period_type_id=period_type_id
            ).all()
            
            grid = {}
            for w in ["A", "B"]:
                for p in type_periods:
                    matched_level = "Neutral"
                    best_score = -1
                    for ext in existings:
                        ext_w = ext.week_type.value if hasattr(ext.week_type, "value") else ext.week_type
                        covers_w = (ext_w == "W" or ext_w == w)
                        covers_p = (not ext.periods or p.id in [item.id for item in ext.periods])
                        if covers_w and covers_p:
                            score = 0
                            if ext_w != "W":
                                score += 2
                            if ext.periods:
                                score += 1
                            if score > best_score:
                                best_score = score
                                matched_level = ext.preference_level
                    grid[(w, p.id)] = matched_level

            # Appliquer le nouveau niveau sur les cellules cibles
            target_weeks = ["A", "B"] if week_type == "W" else [week_type]
            target_p_ids = [p.id for p in type_periods] if is_annual else period_ids

            for w in target_weeks:
                for pid in target_p_ids:
                    grid[(w, pid)] = level

            # Supprimer tous les existants pour repartir propre
            for ext in existings:
                ext.delete(db)

            # Reconstruire les candidats
            candidates = []
            for w in ["A", "B"]:
                levels_in_w = set(grid[(w, p.id)] for p in type_periods)
                for lvl in levels_in_w:
                    if lvl == "Neutral":
                        continue
                    pids = [p.id for p in type_periods if grid[(w, p.id)] == lvl]
                    if len(pids) == len(type_periods):
                        candidates.append((w, lvl, frozenset()))
                    elif pids:
                        candidates.append((w, lvl, frozenset(pids)))

            # Fusionner A et B en W si possible
            by_key = {}
            for w, lvl, pids in candidates:
                by_key.setdefault((lvl, pids), []).append(w)

            for (lvl, pids), weeks in by_key.items():
                if len(weeks) == 2:
                    final_prefs.append(("W", lvl, list(pids)))
                else:
                    final_prefs.append((weeks[0], lvl, list(pids)))

        else:
            # Cas sans dimension de période (uniquement semaine A/B/W)
            grid = {}
            for w in ["A", "B"]:
                matched_level = "Neutral"
                best_score = -1
                for ext in existings:
                    ext_w = ext.week_type.value if hasattr(ext.week_type, "value") else ext.week_type
                    covers_w = (ext_w == "W" or ext_w == w)
                    if covers_w:
                        score = 1 if ext_w != "W" else 0
                        if score > best_score:
                            best_score = score
                            matched_level = ext.preference_level
                grid[w] = matched_level

            # Appliquer la cible
            target_weeks = ["A", "B"] if week_type == "W" else [week_type]
            for w in target_weeks:
                grid[w] = level

            # Supprimer existants
            for ext in existings:
                ext.delete(db)

            # Reconstruire candidats
            candidates = []
            for w in ["A", "B"]:
                lvl = grid[w]
                if lvl != "Neutral":
                    candidates.append((w, lvl))

            # Fusionner A et B en W
            by_lvl = {}
            for w, lvl in candidates:
                by_lvl.setdefault(lvl, []).append(w)

            for lvl, weeks in by_lvl.items():
                if len(weeks) == 2:
                    final_prefs.append(("W", lvl, []))
                else:
                    final_prefs.append((weeks[0], lvl, []))

        # 4. Créer les nouveaux enregistrements
        created_instances = []
        for w, lvl, pids in final_prefs:
            pref = cls(
                resource_type=resource_type,
                resource_id=resource_id,
                timeslot_id=timeslot_id,
                preference_level=lvl,
                week_type=w
            )
            if pids:
                pref.periods = db.query(Period).filter(Period.id.in_(pids)).all()
            pref._via_crud_mixin_create = True
            db.add(pref)
            created_instances.append(pref)

        # 5. Retourner l'instance principale
        main_instance = None
        for inst in created_instances:
            inst_w = inst.week_type.value if hasattr(inst.week_type, "value") else inst.week_type
            req_w = week_type.value if hasattr(week_type, "value") else week_type
            if inst_w == req_w:
                main_instance = inst
                break
        if not main_instance and created_instances:
            main_instance = created_instances[0]

        db.flush()
        if main_instance:
            db.refresh(main_instance)
        return main_instance

    def update(self, db: "Session", vals: dict):
        """
        Surcharge de update pour nettoyer la ligne si le niveau devient Neutral.
        """
        level = vals.get("preference_level", self.preference_level)
        if level == "Neutral" or not level:
            self.delete(db)
            return None
            
        return super().update(db, vals)


