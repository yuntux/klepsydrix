"""
Wizard « Exporter le rattachement élèves/groupes vers SIECLE » — génère le fichier
`<UAJ>_ELEGROUPE_<AAAAMMJJ>.xml` (racine `IMPORT_ELEVES`), sens montant Klepsydrix -> SIECLE.

Même patron que wizard_sts_export.py : aperçu d'abord (lecture seule), génération ensuite. Pas
d'étape de correspondances — comme pour wizard_eleves_import.py, tout est soit résolu directement
depuis la base, soit bloquant (voir eleves_export.py pour le détail des exclusions).

Le fichier produit descend par un champ binaire (§15.Q) — aucune écriture disque côté serveur.

**Le compteur NUM_ENVOI n'est incrémenté qu'à la génération réelle** (`rpc_export`), jamais à
l'aperçu (`rpc_preview`) : un aperçu qu'on abandonne ne doit pas brûler un numéro d'envoi jamais
réellement transmis à SIECLE.
"""
import base64
from datetime import date

from sqlalchemy.orm import Session

from backend.app.core.eleves_export import build_import_eleves, export_filename, eligible_and_excluded_students, ElevesExportError
from backend.app.models.base import TransientModel, requires_access
from backend.app.models.school import School
from backend.app.models.system_setting import SystemSetting
from backend.app.core.html_text import esc

EXPERIMENTAL_NOTICE = (
    '<div style="border-left:4px solid #3B82F6;background:#EFF6FF;padding:12px 16px;'
    'border-radius:4px;margin-bottom:16px;">'
    "<p><strong>Fonction expérimentale.</strong> Le ministère de l'éducation nationale ne publie pas "
    "sur son site public les normes d'échange SIECLE, et l'auteur ne dispose d'aucun fichier "
    "d'exemple réel. Ce format est reconstitué à partir du code d'export de <strong>GEPI</strong>, "
    "avec deux différences assumées : le code de groupe exporté est le vrai code SIECLE/STS "
    "(<code>Group.name</code>), pas un identifiant interne, et la date de début de rattachement "
    "est la date réelle (<code>StudentClassPartLink.begin_date</code>), pas une borne globale "
    "d'établissement.</p>"
    "<p>Le fichier produit doit être réimporté manuellement dans SIECLE (menu Import de groupes "
    "d'élèves). Seuls les élèves déjà importés depuis SIECLE (identifiant SIECLE connu) et dont la "
    "date de naissance est renseignée sont exportables — les autres sont signalés ci-dessous.</p>"
    "</div>"
)


def _resolve_school(db: Session, school_id) -> School:
    if not school_id:
        raise ValueError("Choisissez l'établissement dont vous voulez exporter le rattachement élèves/groupes.")
    school = db.get(School, int(school_id))
    if not school:
        raise ValueError("Établissement introuvable.")
    return school


def _summary_rows(eligibles: list) -> list:
    return [
        {
            "id": student.id,
            "last_name": student.last_name,
            "first_name": student.first_name,
            "groups_count": nb_groupes,
        }
        for student, nb_groupes in eligibles
    ]


def _preview_html(school: School, eligibles: list, exclus: list) -> str:
    html = (
        f"<p><strong>{esc(school.name)}</strong> — RNE {esc(school.uai)}.</p>"
        f"<p>{len(eligibles)} élève(s) exportable(s).</p>"
    )
    if not school.student_end_date:
        html += (
            "<p style=\"color:#DC2626\"><strong>Génération impossible</strong> : la date de sortie "
            "des élèves n'est pas renseignée sur la fiche établissement (nécessaire pour "
            "DATE_FIN_GROUPE). Complétez-la avant de poursuivre.</p>"
        )
    if exclus:
        lignes = "".join(
            f"<li>{esc(s.first_name)} {esc(s.last_name)} : {esc(motif)}</li>"
            for s, motif in exclus[:20]
        )
        reste = len(exclus) - min(len(exclus), 20)
        if reste:
            lignes += f"<li>… et {reste} autre(s)</li>"
        html += (
            f"<p><strong>{len(exclus)} élève(s) laissé(s) de côté</strong> :</p><ul>{lignes}</ul>"
        )
    return html


class WizardElevesExport(TransientModel):
    """Enregistrement singleton (id=1 fixe, pas de liste), voir ui.json."""

    __tablename__ = "wizard_eleves_exports"
    _fields = [
        "id", "info_html", "school_id", "preview_html", "summary_rows", "result_html", "export_file",
    ]
    _field_info = {
        "info_html": {"type": "html", "label": None, "readOnly": True},
        "school_id": {"label": "Établissement", "resource": "schools"},
        "preview_html": {"type": "html", "label": None, "readOnly": True},
        "summary_rows": {"label": "Élèves exportables", "type": "text", "widget": "list_preview", "readOnly": True},
        "result_html": {"type": "html", "label": None, "readOnly": True},
        "export_file": {"label": "Fichier d'export", "type": "binary", "readOnly": True},
    }

    __actions__ = [{
        "id": "export_eleves_flux",
        "label": "Exporter le rattachement élèves/groupes vers SIECLE",
        "type": "wizard",
        "steps": [
            {
                "id": "choose",
                "title": "1. Établissement",
                "fields": [
                    {"key": "info_html", "type": "html", "label": None},
                    {"key": "school_id", "label": "Établissement", "resource": "schools"},
                ],
                "submitLabel": "Analyser",
                "rpc": "rpc_preview",
                "rpcParams": {"school_id": "school_id"},
            },
            {
                "id": "review",
                "title": "2. Aperçu",
                "fields": [
                    {"key": "preview_html", "type": "html", "label": None},
                    {
                        "key": "summary_rows", "label": "Élèves exportables", "type": "text",
                        "widget": "list_preview", "fullWidth": True,
                        "widgetParams": {
                            "columns": [
                                {"key": "last_name", "label": "Nom", "width": 200},
                                {"key": "first_name", "label": "Prénom", "width": 200},
                                {"key": "groups_count", "label": "Groupes", "width": 100},
                            ],
                            "listConfig": {"editableInline": False, "disableAdd": True, "disableDelete": True, "allowMultiSelect": False},
                        },
                    },
                ],
                "submitLabel": "Générer le fichier",
                "rpc": "rpc_export",
                "rpcParams": {"school_id": "school_id"},
            },
            {
                "id": "result",
                "title": "3. Fichier",
                "isLast": True,
                "fields": [
                    {"key": "result_html", "type": "html", "label": " "},
                    {"key": "export_file", "label": "Fichier d'export", "type": "binary"},
                ],
                "submitLabel": "Fermer",
            },
        ],
    }]

    def __init__(self, id, info_html=None, school_id=None, preview_html=None, summary_rows=None,
                 result_html=None, export_file=None):
        self.id = id
        self.info_html = info_html
        self.school_id = school_id
        self.preview_html = preview_html
        self.summary_rows = summary_rows or []
        self.result_html = result_html
        self.export_file = export_file

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        return [cls(id=1, info_html=EXPERIMENTAL_NOTICE)]

    @requires_access("write")
    def rpc_preview(self, db: Session, school_id=None) -> dict:
        """Aperçu seul : aucune écriture, le compteur NUM_ENVOI n'est pas touché."""
        school = _resolve_school(db, school_id)
        eligibles, exclus = eligible_and_excluded_students(db, school)
        prochain_num_envoi = SystemSetting.get_siecle_group_export_seq(db) + 1
        html = _preview_html(school, eligibles, exclus)
        html += f"<p>Prochain numéro d'envoi (NUM_ENVOI) si vous générez le fichier : {prochain_num_envoi}.</p>"
        return {
            "preview_html": html,
            "summary_rows": _summary_rows(eligibles),
        }

    @requires_access("write")
    def rpc_export(self, db: Session, school_id=None) -> dict:
        """
        Rejoue l'aperçu (la base a pu bouger entre les deux écrans) puis génère. Le compteur n'est
        incrémenté qu'ici, après une génération réussie — un fichier invalide (schéma non
        respecté, date de sortie manquante) ne consomme donc pas de numéro d'envoi.
        """
        school = _resolve_school(db, school_id)
        annee = SystemSetting.get_school_year(db)
        aujourdhui = date.today()

        try:
            num_envoi = SystemSetting.get_siecle_group_export_seq(db) + 1
            contenu = build_import_eleves(db, school, aujourdhui, num_envoi)
        except (ValueError, ElevesExportError) as exc:
            raise ValueError(str(exc)) from exc

        # Génération réussie : le numéro est maintenant réellement consommé.
        SystemSetting.increment_siecle_group_export_seq(db)

        eligibles, exclus = eligible_and_excluded_students(db, school)
        html = (
            f"<p>Fichier généré pour <strong>{esc(school.name)}</strong> — RNE {esc(school.uai)}, "
            f"année {esc(annee)}-{esc(annee + 1)}, envoi n°{num_envoi}.</p>"
            f"<p>{len(eligibles)} élève(s) exporté(s).</p>"
            "<p>Réimportez ce fichier dans SIECLE (menu Import de groupes d'élèves).</p>"
        )
        if exclus:
            html += f"<p>{len(exclus)} élève(s) laissé(s) de côté — voir l'étape précédente pour le détail.</p>"

        return {
            "result_html": html,
            "export_file": {
                "filename": export_filename(school, aujourdhui),
                "mime_type": "text/xml",
                "data_base64": base64.b64encode(contenu.encode("utf-8")).decode("ascii"),
            },
        }
