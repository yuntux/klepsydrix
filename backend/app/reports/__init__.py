"""
Registre des rapports — l'équivalent de l'ensemble des enregistrements `ir.actions.report` d'Odoo.

Ajouter un rapport = un module ici (données + définition) et un gabarit dans `templates/`, puis une
ligne dans `REGISTRY`. Aucune route à écrire : `api/report.py` est générique et paramétré par le
nom du rapport.
"""
from backend.app.reports import course_list
from backend.app.reports.base import ReportDef

REGISTRY: dict[str, ReportDef] = {
    course_list.REPORT.name: course_list.REPORT,
}


def get_report(name: str) -> ReportDef | None:
    return REGISTRY.get(name)
