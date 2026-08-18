"""
Socle d'impression PDF (voir architecture.md §22). Reprend l'architecture d'Odoo — un rapport est
une DONNÉE (métadonnées + gabarit HTML) servie par un endpoint générique, pas une route par
document — avec deux écarts délibérés :

1. **Moteur de rendu : WeasyPrint, pas wkhtmltopdf.** Pas de sous-processus, pas de fichiers
   temporaires, et surtout la pagination en CSS Paged Media natif (`@page`, `counter(page)`,
   `display: table-header-group` pour répéter un en-tête de tableau). C'est précisément ce
   qu'Odoo/wkhtmltopdf fait mal, au prix d'en-têtes et pieds de page passés en fichiers HTML
   séparés (`--header-html`).
2. **`get_values` lit via `read()`/`browse()`, jamais par traversée de relations.** Contrairement
   à Odoo, dont l'ORM applique les `ir.rules` à toute lecture y compris obtenue par traversée, le
   moteur de droits de Klepsydrix s'applique à `read()` (voir architecture.md §18.B) : un
   `course.subject_relation` dans un gabarit contournerait le domaine de l'utilisateur. Séparer la
   collecte des données de leur mise en forme est donc une contrainte de sécurité ici, pas
   seulement une bonne pratique — et c'est aussi ce qui rend un rapport testable sans PDF.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Formats papier — fragment CSS `@page` par nom, plutôt qu'un modèle `report.paperformat` comme
# Odoo. Odoo a besoin d'un modèle parce que ses clients configurent les marges depuis l'IHM ; tant
# que ce n'est pas un besoin exprimé, une constante suffit et évite une table de plus.
PAPERFORMATS = {
    "a4-portrait": "@page { size: A4 portrait; margin: 18mm 15mm 20mm 15mm; }",
    "a4-landscape": "@page { size: A4 landscape; margin: 15mm 12mm 18mm 12mm; }",
}


@dataclass(frozen=True)
class ReportDef:
    """
    Définition déclarative d'un rapport — l'équivalent d'un enregistrement `ir.actions.report`.

    `model` sert à rattacher le rapport à une ressource (affichage du bouton côté IHM via
    `__actions__`, et entrée du registre). `get_values(db, ids, params)` est le pendant direct de
    `_get_report_values()` d'Odoo : il retourne le dictionnaire passé au gabarit.
    """
    name: str
    label: str
    model: type
    template: str
    get_values: Callable[[Session, list, dict], dict]
    filename: Callable[[Session, list], str]
    paperformat: str = "a4-portrait"
    title: str = ""


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        # Autoescape : un nom de cours ou de matière est une saisie utilisateur libre. Sans lui,
        # une matière nommée « <b>Maths » casserait la mise en page — et le gabarit est du HTML
        # rendu, donc la même surface d'injection qu'une page web.
        autoescape=select_autoescape(["html"]),
    )


def render_html(report: ReportDef, db: Session, ids: list, params: dict) -> str:
    """
    Rendu HTML du rapport. Exposé tel quel par l'endpoint (`?format=html`) : c'est ce qui permet
    d'itérer sur un gabarit dans le navigateur sans regénérer un PDF, et c'est sur ce rendu que
    portent les tests de contenu — bien plus lisibles en cas d'échec qu'une comparaison d'octets.
    """
    values = report.get_values(db, ids, params)
    stylesheet = (TEMPLATES_DIR / "base.css").read_text(encoding="utf-8")
    stylesheet += "\n" + PAPERFORMATS[report.paperformat]
    template = _environment().get_template(report.template)
    return template.render(
        stylesheet=stylesheet,
        title=report.title or report.label,
        printed_on=datetime.now().strftime("%d/%m/%Y à %Hh%M"),
        **values,
    )


def render_pdf(report: ReportDef, db: Session, ids: list, params: dict) -> bytes:
    """
    Même rendu que ci-dessus, converti par WeasyPrint. `base_url` pointe sur le dossier des
    gabarits pour qu'une future ressource locale (logo de l'établissement) soit résolue — aucune
    ressource distante n'est chargée, le rendu doit rester hors-ligne et reproductible.
    """
    from weasyprint import HTML

    html = render_html(report, db, ids, params)
    return HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf()
