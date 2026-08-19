"""
Wizard « Attribuer les salles » (endpoint 3, plan salles §4) — enregistrement singleton (id=1
fixe, pas de liste), même convention que wizard_optimize_timetable.py. Remplace l'ancien bouton
"Attribuer les salles" de TimetableGrid.vue : l'utilisateur choisit ici l'axe de continuité de
salle (professeurs ou divisions) qui reçoit un poids ×10 par rapport à l'autre, voir
room_constraints.py::teacher_room_continuity_penalty / division_room_continuity_penalty.
"""
from sqlalchemy.orm import Session
from backend.app.models.base import TransientModel, requires_access
from backend.app.core import db_registry


class WizardClassroomAssignment(TransientModel):
    __tablename__ = "wizard_classroom_assignments"
    _fields = ["id", "optimize_target"]
    _field_info = {
        "optimize_target": {
            "label": "Priorité de continuité des salles",
            "type": "select",
            "options": [
                {"value": "TEACHER", "label": "Minimiser les déplacements des professeurs"},
                {"value": "DIVISION", "label": "Minimiser les déplacements des divisions"},
            ],
        },
    }
    __actions__ = [{
        "id": "start_classroom_assignment",
        "label": "Attribuer les salles",
        "type": "wizard",
        "steps": [
            {
                "id": "params",
                "title": "Priorité de continuité des salles",
                "submitLabel": "Attribuer les salles",
                "isLast": True,
                "rpc": "rpc_start_classroom_assignment",
                "rpcParams": {
                    "optimize_target": "optimize_target",
                },
                "fields": [
                    {
                        "key": "optimize_target",
                        "label": "Priorité de continuité des salles",
                        "type": "select",
                        "options": [
                            {"value": "TEACHER", "label": "Minimiser les déplacements des professeurs"},
                            {"value": "DIVISION", "label": "Minimiser les déplacements des divisions"},
                        ],
                    },
                ],
            },
        ],
    }]

    def __init__(self, id, optimize_target):
        self.id = id
        self.optimize_target = optimize_target

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        return [cls(id=1, optimize_target="TEACHER")]

    @requires_access("write")
    def rpc_start_classroom_assignment(self, db: Session, optimize_target: str) -> dict:
        from backend.app.solver.solver import start_classroom_assignment_async

        if optimize_target not in ("TEACHER", "DIVISION"):
            raise ValueError("Priorité de continuité invalide.")

        start_classroom_assignment_async(
            None,
            db_registry.slug_for_session(db),
            optimize_target=optimize_target,
        )
        return {"status": "success", "mutated_resources": ["course_classroom_requirements"]}
