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
from typing import Callable, Optional

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
    # Un rapport dont le <h1> générique (voir layout.html) ne convient pas — ex: timetable.py, qui
    # rend son propre en-tête compact PAR PAGE (titre + ressource fusionnés sur une ligne) et n'a
    # donc besoin d'AUCUN <h1> — fournit ici sa propre fonction de titre plutôt qu'un booléen
    # "cache le h1" : `document_title(db, ids) -> str`, une chaîne vide supprimant le <h1>
    # (layout.html ne le rend que si `title` est non vide). Absent (None) : comportement par
    # défaut, `report.title or report.label`.
    document_title: Optional[Callable[[Session, list], str]] = None
    # Nom de fichier CSS (dans templates/), propre à CE rapport, concaténé après base.css — les
    # règles réellement communes (pagination, en-tête d'établissement, table générique) restent
    # dans base.css ; tout le reste (ex: la grille d'emploi du temps) vit dans son propre fichier.
    extra_css: str = ""


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        # Autoescape : un nom de cours ou de matière est une saisie utilisateur libre. Sans lui,
        # une matière nommée « <b>Maths » casserait la mise en page — et le gabarit est du HTML
        # rendu, donc la même surface d'injection qu'une page web.
        autoescape=select_autoescape(["html"]),
    )


def _page_chrome_css(printed_on: str) -> str:
    """
    En-tête COURANT (répété sur CHAQUE page, contrairement à du contenu de flux normal qui ne
    s'affiche qu'une fois) : établissement à gauche, heure d'impression + pagination à droite, un
    seul trait continu sous les deux (`@top-left`/`@top-right` à 50% chacun, même `border-bottom`).

    - `@top-right` : texte dynamique (l'heure d'impression, calculée à chaque génération) — ne peut
      mêler texte et `counter()` qu'en assemblant des chaînes littérales, d'où l'assemblage ici en
      Python plutôt que statique dans base.css.
    - `@top-left` : `content: string(resource-school, last)`, PAS une valeur codée en dur ici — la
      valeur réelle est déposée dans le flux HTML via `string-set` (voir
      base.css::.page-school-marker), un mécanisme CSS Paged Media natif ("running header"). C'est
      le seul moyen d'avoir une valeur qui change page par page (ex: timetable.py imprime une
      ressource différente par page, donc potentiellement un établissement différent) sans que ce
      module connaisse quoi que ce soit à la pagination réelle du document.
      ⚠️ `, last` est OBLIGATOIRE : `string()` sans second argument vaut `string(name, first)` par
      défaut (spec CSS GCPM) — quand DEUX marqueurs se suivent avant la fin d'une même page (le
      marqueur générique de layout.html, valeur par défaut, immédiatement suivi du marqueur propre
      à la première page d'un gabarit comme timetable.html), `first` capturerait le premier des
      deux (la valeur par défaut, potentiellement vide) au lieu du second qui doit gagner — bug
      constaté : la première page d'un document multi-ressources affichait un établissement vide
      quand elle aurait dû reprendre celui de sa propre ressource.
    """
    printed_on_escaped = printed_on.replace('"', '\\"')
    shared = (
        "border-bottom: 0.75pt solid #cbd5e1; padding-bottom: 1.5mm; vertical-align: bottom; "
        "font-family: sans-serif; font-size: 8pt; "
    )
    return (
        "@page { "
        f'@top-left {{ content: string(resource-school, last); width: 50%; color: #0f172a; font-weight: bold; {shared} }} '
        f'@top-right {{ content: "Édité le {printed_on_escaped} - Page " counter(page) " / " counter(pages); '
        f'width: 50%; text-align: right; color: #64748b; {shared} }} '
        "}"
    )


def render_html(report: ReportDef, db: Session, ids: list, params: dict) -> str:
    """
    Rendu HTML du rapport. Exposé tel quel par l'endpoint (`?format=html`) : c'est ce qui permet
    d'itérer sur un gabarit dans le navigateur sans regénérer un PDF, et c'est sur ce rendu que
    portent les tests de contenu — bien plus lisibles en cas d'échec qu'une comparaison d'octets.
    """
    values = report.get_values(db, ids, params)
    printed_on = datetime.now().strftime("%d/%m/%Y à %Hh%M")

    stylesheet = (TEMPLATES_DIR / "base.css").read_text(encoding="utf-8")
    if report.extra_css:
        stylesheet += "\n" + (TEMPLATES_DIR / report.extra_css).read_text(encoding="utf-8")
    stylesheet += "\n" + PAPERFORMATS[report.paperformat]
    stylesheet += "\n" + _page_chrome_css(printed_on)

    title = report.document_title(db, ids) if report.document_title else (report.title or report.label)

    template = _environment().get_template(report.template)
    return template.render(
        stylesheet=stylesheet,
        title=title,
        # <title> (onglet navigateur / métadonnées PDF) reste TOUJOURS le label du rapport, même
        # quand `title` (le <h1> visible) est délibérément vide (voir document_title ci-dessus) —
        # les deux n'ont pas la même fonction, une page sans titre visible garde un onglet lisible.
        meta_title=report.label,
        printed_on=printed_on,
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
