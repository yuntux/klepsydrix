"""
Wizard (voir __actions__) d'affectation automatique des besoins aux professeurs — trois étapes
(simuler / valider / résultat), sur le patron exact de wizard_course_generation.py (TransientModel
+ __actions__). Pas de filtrage par établissement/niveau/filière dans cette première itération
(voir specs/002-yearly-timetabling-core/teacher-assignment-proposal.md §1) : rpc_simulate porte sur
tous les Service non verrouillés, comme generate_courses_from_services() porte sur tous les
Service — un filtrage pourra être ajouté plus tard comme un champ de plus à l'étape "scope", sans
changer la structure du wizard.
"""
from sqlalchemy.orm import Session
from backend.app.models.base import TransientModel, requires_access
from backend.app.models.service import Service
from backend.app.models.teacher import Teacher
from backend.app.models.division import Division
from backend.app.solver.teacher_assignment import compute_assignment_proposal


def _division_label(service: Service) -> str:
    if service.division_id:
        from sqlalchemy.orm import object_session
        db = object_session(service)
        division = db.get(Division, service.division_id) if db else None
        return division.name if division else ""
    if service.group:
        return service.group.name
    return ""


def _render_proposal_rows(db: Session, proposals: list) -> list:
    rows = []
    for p in proposals:
        service = db.get(Service, p["service_id"])
        if not service:
            continue
        teachers = db.query(Teacher).filter(Teacher.id.in_(p["teacher_ids"])).all()
        rows.append({
            "id": service.id,
            "service_id": service.id,
            "teacher_ids": p["teacher_ids"],
            "tier": p["tier"],
            "division_label": _division_label(service),
            "subject_label": service.subject.name if service.subject else "",
            "teacher_labels": ", ".join(t.display_name for t in teachers),
        })
    return rows


def _render_warnings_html(warnings: list) -> str:
    if not warnings:
        return "<p>Aucun avertissement.</p>"
    items = "".join(f"<li>{w['message']}</li>" for w in warnings)
    return f"<p><strong>{len(warnings)} avertissement(s) :</strong></p><ul>{items}</ul>"


class WizardTeacherAssignment(TransientModel):
    """Enregistrement singleton (id=1 fixe, pas de liste), voir ui.json."""
    __tablename__ = "wizard_teacher_assignments"
    _fields = ["id", "info_html", "proposals", "warnings_html", "result_html"]
    _field_info = {
        "info_html": {"type": "html", "label": " ", "readOnly": True},
        "proposals": {"label": "Propositions", "type": "text", "widget": "list_preview", "readOnly": True},
        "warnings_html": {"type": "html", "label": " ", "readOnly": True},
        "result_html": {"type": "html", "label": " ", "readOnly": True},
    }
    __actions__ = [{
        "id": "assign_teachers",
        "label": "Affecter les professeurs",
        "type": "wizard",
        "steps": [
            {
                "id": "confirm",
                "title": "1. Simulation",
                "fields": [{"key": "info_html", "type": "html", "label": " "}],
                "submitLabel": "Lancer la simulation",
                "rpc": "rpc_simulate",
            },
            {
                "id": "review",
                "title": "2. Résultat de la simulation",
                "fields": [
                    {"key": "warnings_html", "type": "html", "label": " "},
                    {
                        "key": "proposals", "label": "Propositions", "type": "text", "widget": "list_preview", "fullWidth": True,
                        # widgetParams.columns/listConfig : même dictionnaire de config qu'un panneau
                        # GenericList classique dans ui.json (ListPreviewField.vue en fait un
                        # passe-plat pur, voir ce fichier) — la seule différence avec un panneau
                        # normal est que `columns` doit être fourni en toutes lettres ici (pas de
                        # schéma OpenAPI à dériver, ces lignes ne correspondent à aucune ressource
                        # backend réelle, voir _render_proposal_rows ci-dessous).
                        "widgetParams": {
                            "columns": [
                                {"key": "division_label", "label": "Classe / Groupe", "width": 160},
                                {"key": "subject_label", "label": "Matière", "width": 140},
                                {"key": "teacher_labels", "label": "Professeur(s) proposé(s)", "width": 240},
                                {"key": "tier", "label": "Palier", "width": 90},
                            ],
                            "listConfig": {
                                "editableInline": False,
                                "disableAdd": True,
                                "disableDelete": True,
                                "allowMultiSelect": True,
                                # Toutes les propositions démarrent cochées ; décocher = exclure de
                                # rpc_apply (voir listConfig.selectAllLine, GenericList.vue).
                                "selectAllLine": True,
                            },
                        },
                    },
                ],
                "submitLabel": "Valider",
                "rpc": "rpc_apply",
                "rpcParams": {"proposals": "proposals"},
            },
            {
                "id": "result",
                "title": "3. Résultat",
                "isLast": True,
                "fields": [{"key": "result_html", "type": "html", "label": " "}],
                "submitLabel": "Fermer",
            },
        ],
    }]

    def __init__(self, id, info_html, proposals=None, warnings_html=None, result_html=None):
        self.id = id
        self.info_html = info_html
        self.proposals = proposals or []
        self.warnings_html = warnings_html
        self.result_html = result_html

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        count = db.query(Service).filter(Service.teachers_locked.is_(False)).count()
        html = "<p>L'affectation automatique va être simulée sur tous les services non verrouillés.</p>"
        html += f"<p><strong>{count} service(s)</strong> seront pris en compte. Aucune écriture n'a lieu à cette étape.</p>"
        return [cls(id=1, info_html=html)]

    @requires_access("write")
    def rpc_simulate(self, db: Session) -> dict:
        """Dry-run : ne modifie rien en base (voir compute_assignment_proposal), uniquement une
        proposition rejouable à volonté."""
        result = compute_assignment_proposal(db)
        return {
            "proposals": _render_proposal_rows(db, result["proposals"]),
            "warnings_html": _render_warnings_html(result["warnings"]),
        }

    @requires_access("write")
    def rpc_apply(self, db: Session, proposals: list) -> dict:
        """
        `proposals` : la liste retournée par rpc_simulate, éventuellement amputée par
        l'utilisateur (lignes décochées dans l'étape de review, voir GenericList mode
        transitoire/widget list_preview) — écrit directement dans Service.teachers. Tout Service
        verrouillé entre-temps (teachers_locked=True, saisi manuellement pendant que la
        simulation était affichée) est ignoré plutôt qu'écrasé.
        """
        applied_count = 0
        skipped_count = 0
        for row in proposals:
            service = db.get(Service, row["service_id"])
            if not service or service.teachers_locked:
                skipped_count += 1
                continue
            service.update(db, {"teacher_ids": row["teacher_ids"]})
            applied_count += 1

        html = f"<p><strong>{applied_count} service(s) affecté(s).</strong></p>"
        if skipped_count:
            html += f"<p>{skipped_count} proposition(s) ignorée(s) (service verrouillé entre-temps).</p>"
        # mutated_resources : lu par GenericWizard.vue à la fermeture pour rafraîchir le cache
        # navigateur des Service (ex: le panneau Services par classe affiché derrière la popin) —
        # la ressource propre du wizard (wizard_teacher_assignments) n'est pas ce qui a réellement
        # été modifié en base (même remarque que WizardCourseGeneration.rpc_generate_courses).
        return {"result_html": html, "mutated_resources": ["services"]}
