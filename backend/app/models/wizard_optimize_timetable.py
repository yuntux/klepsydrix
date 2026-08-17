"""
Wizard « Optimiser l'emploi du temps » (endpoint 4a/4b, plan salles §4/§5) — enregistrement
singleton (id=1 fixe, pas de liste), même convention que wizard_course_generation.py. Porte
uniquement les 3 champs simples décrits au plan §5 ("deux durées + une case à cocher") ; les 2
réglages avancés propres à la phase salles (max_compute_classroom_seconds/
max_no_progress_classroom_seconds) restent programmatiques, avec repli sur
SOLVER_TIME_LIMIT_SECONDS/SOLVER_UNIMPROVED_TIME_LIMIT_SECONDS (voir
solver.py::start_optimize_pipeline_async) — pas exposés dans ce wizard volontairement simple.
"""
from sqlalchemy.orm import Session
from backend.app.models.base import TransientModel, requires_access
from backend.app.core.config import settings
from backend.app.core import db_registry


class WizardOptimizeTimetable(TransientModel):
    __tablename__ = "wizard_optimize_timetables"
    _fields = ["id", "max_compute_seconds", "max_no_progress_seconds", "replace_rooms_with_groups"]
    _field_info = {
        "max_compute_seconds": {
            "label": "Durée de calcul maximale (secondes)", "type": "number",
            "min": 1, "max": settings.SOLVER_OPTIMIZE_MAX_COMPUTE_CEILING_SECONDS,
        },
        "max_no_progress_seconds": {
            "label": "Arrêt si aucune amélioration pendant (secondes)", "type": "number", "min": 1,
        },
        "replace_rooms_with_groups": {
            "label": "Remettre les salles déjà attribuées à l'état groupe avant de les réattribuer",
            "type": "boolean",
        },
    }
    __actions__ = [{
        "id": "start_optimize",
        "label": "Optimiser l'emploi du temps",
        "type": "wizard",
        "steps": [
            {
                "id": "params",
                "title": "Paramètres de l'optimisation",
                "submitLabel": "Lancer l'optimisation",
                "isLast": True,
                "rpc": "rpc_start_optimize",
                "rpcParams": {
                    "max_compute_seconds": "max_compute_seconds",
                    "max_no_progress_seconds": "max_no_progress_seconds",
                    "replace_rooms_with_groups": "replace_rooms_with_groups",
                },
                "fields": [
                    {"key": "max_compute_seconds", "label": "Durée de calcul maximale (secondes)", "type": "number", "min": 1, "max": settings.SOLVER_OPTIMIZE_MAX_COMPUTE_CEILING_SECONDS},
                    {"key": "max_no_progress_seconds", "label": "Arrêt si aucune amélioration pendant (secondes)", "type": "number", "min": 1},
                    {"key": "replace_rooms_with_groups", "label": "Remettre les salles déjà attribuées à l'état groupe avant de les réattribuer", "type": "boolean"},
                ],
            },
        ],
    }]

    def __init__(self, id, max_compute_seconds, max_no_progress_seconds, replace_rooms_with_groups):
        self.id = id
        self.max_compute_seconds = max_compute_seconds
        self.max_no_progress_seconds = max_no_progress_seconds
        self.replace_rooms_with_groups = replace_rooms_with_groups

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        return [cls(
            id=1,
            max_compute_seconds=settings.SOLVER_OPTIMIZE_DEFAULT_MAX_COMPUTE_SECONDS,
            max_no_progress_seconds=settings.SOLVER_OPTIMIZE_DEFAULT_MAX_NO_PROGRESS_SECONDS,
            replace_rooms_with_groups=False,
        )]

    @requires_access("write")
    def rpc_start_optimize(self, db: Session, max_compute_seconds: int, max_no_progress_seconds: int,
                            replace_rooms_with_groups: bool) -> dict:
        from backend.app.solver.solver import start_optimize_pipeline_async

        if not (1 <= max_compute_seconds <= settings.SOLVER_OPTIMIZE_MAX_COMPUTE_CEILING_SECONDS):
            raise ValueError(
                f"La durée de calcul maximale doit être comprise entre 1 et "
                f"{settings.SOLVER_OPTIMIZE_MAX_COMPUTE_CEILING_SECONDS} secondes."
            )
        if not (1 <= max_no_progress_seconds <= max_compute_seconds):
            raise ValueError(
                "L'arrêt sans amélioration doit être compris entre 1 seconde et la durée de calcul maximale."
            )

        start_optimize_pipeline_async(
            None,
            db_registry.slug_for_session(db),
            max_compute_seconds=max_compute_seconds,
            max_no_progress_seconds=max_no_progress_seconds,
            replace_rooms_with_groups=replace_rooms_with_groups,
        )
        # mutated_resources : "courses" (COURSE_PLACEMENT réécrit timeslot/week_type) et
        # "course_classroom_requirements" (CLASSROOM_ASSIGNMENT réécrit classroom_id/quantity, si
        # replace_rooms_with_groups) — voir GenericWizard.vue, même mécanisme que
        # WizardCourseGeneration.rpc_generate_courses.
        return {"status": "success", "mutated_resources": ["courses", "course_classroom_requirements"]}
