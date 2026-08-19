"""
Wizard « Placement automatique » (endpoint 2, plan salles §4) — enregistrement singleton (id=1
fixe, pas de liste), même convention que wizard_optimize_timetable.py/wizard_classroom_assignment.py.
Remplace l'ancien bouton "Placement automatique" de TimetableGrid.vue : aucun paramètre à saisir
(start_course_placement_async ne prend que school_id/slug, déjà résolus côté backend) — un seul
step, juste un message de confirmation (info_html, même convention que
wizard_course_generation.py) et un bouton de lancement.
"""
from sqlalchemy.orm import Session
from backend.app.models.base import TransientModel, requires_access
from backend.app.core import db_registry


class WizardCoursePlacement(TransientModel):
    __tablename__ = "wizard_course_placements"
    _fields = ["id", "info_html"]
    # Label non vide (espace) : un label "" retombe sur la clé du champ comme libellé affiché
    # (App.vue, `prop.title || key` — "" est falsy en JS), ce qu'on veut justement éviter pour un
    # simple bloc de texte formaté qui n'a pas besoin d'étiquette.
    _field_info = {"info_html": {"type": "html", "label": " ", "readOnly": True}}
    __actions__ = [{
        "id": "start_course_placement",
        "label": "Placement automatique",
        "type": "wizard",
        "steps": [
            {
                "id": "confirm",
                "title": "Placement automatique",
                "submitLabel": "Lancer le placement",
                "isLast": True,
                "startsBackgroundJob": True,
                "rpc": "rpc_start_course_placement",
                "rpcParams": {},
                "fields": [{"key": "info_html", "type": "html", "label": " "}],
            },
        ],
    }]

    def __init__(self, id, info_html):
        self.id = id
        self.info_html = info_html

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        html = "<p>Voulez-vous placer automatiquement l'ensemble des cours non placés ?</p>"
        return [cls(id=1, info_html=html)]

    @requires_access("write")
    def rpc_start_course_placement(self, db: Session) -> dict:
        from backend.app.solver.solver import start_course_placement_async

        start_course_placement_async(None, db_registry.slug_for_session(db))
        return {"status": "success", "mutated_resources": ["courses"]}
