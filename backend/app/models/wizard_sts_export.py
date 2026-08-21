"""
Wizard « Remonter vers STS-web » — audit puis génération du fichier montant.

Deux étapes, dans cet ordre et jamais l'inverse : **l'audit précède l'export**. Générer d'abord et
diagnostiquer ensuite reviendrait à laisser STS-web rendre le verdict, dans un message qui ne dit
ni quel objet est en cause ni quoi corriger.

Politique retenue pour ce projet (décision explicite) : **bloquant sur les anomalies
structurelles, avertissement sur les écarts de volume**. Une anomalie bloquante interdit la
génération ; un avertissement la laisse passer après affichage.

Le fichier produit descend par un champ binaire (§15.Q) — aucune écriture disque côté serveur,
aucun fichier temporaire à nettoyer.
"""
import base64

from sqlalchemy.orm import Session

from backend.app.core.sts_audit import BLOCKING, WARNING, audit, has_blocking
from backend.app.core.sts_export import build_emp_sts, export_filename
from backend.app.models.base import TransientModel, requires_access
from backend.app.models.school import School
from backend.app.models.system_setting import SystemSetting
from backend.app.core.html_text import esc


def _resolve_school(db: Session, school_id) -> School:
    """Un fichier vaut pour un RNE et un seul : l'établissement est un choix, pas un défaut."""
    if not school_id:
        raise ValueError("Choisissez l'établissement dont vous voulez remonter les services.")
    school = db.get(School, int(school_id))
    if not school:
        raise ValueError("Établissement introuvable.")
    return school


def _anomaly_rows(anomalies: list) -> list:
    return [
        {
            "id": index + 1,
            "severity_label": a["severity_label"],
            "code": a["code"],
            "label": a["label"],
            "message": a["message"],
        }
        for index, a in enumerate(anomalies)
    ]


def _audit_html(anomalies: list, school: School) -> str:
    bloquantes = [a for a in anomalies if a["severity"] == BLOCKING]
    avertissements = [a for a in anomalies if a["severity"] == WARNING]

    if not anomalies:
        return (
            f"<p><strong>{esc(school.name)}</strong> — aucune anomalie détectée. Le fichier peut être "
            f"généré.</p>"
        )
    entete = f"<p><strong>{esc(school.name)}</strong> — {len(bloquantes)} anomalie(s) bloquante(s), {len(avertissements)} avertissement(s).</p>"
    if bloquantes:
        entete += (
            "<p style=\"border-left:4px solid #DC2626;background:#FEF2F2;padding:12px 16px;"
            "border-radius:4px;\"><strong>La génération est impossible tant que les anomalies "
            "bloquantes subsistent.</strong> Ce sont des défauts structurels : le fichier serait "
            "rejeté par STS-web, ou produirait une remontée fausse en silence.</p>"
        )
    else:
        entete += (
            "<p style=\"border-left:4px solid #F59E0B;background:#FFFBEB;padding:12px 16px;"
            "border-radius:4px;\">Aucune anomalie bloquante. Les avertissements ci-dessus "
            "n'empêchent pas la génération, mais méritent un regard avant de transmettre.</p>"
        )
    return entete


class WizardStsExport(TransientModel):
    """Enregistrement singleton (id=1 fixe, pas de liste), voir ui.json."""

    __tablename__ = "wizard_sts_exports"
    _fields = [
        "id", "info_html", "school_id", "audit_html", "anomaly_rows", "result_html", "export_file",
    ]
    _field_info = {
        "info_html": {"type": "html", "label": " ", "readOnly": True},
        "school_id": {"label": "Établissement", "resource": "schools"},
        "audit_html": {"type": "html", "label": " ", "readOnly": True},
        "anomaly_rows": {"label": "Anomalies", "type": "text", "widget": "list_preview", "readOnly": True},
        "result_html": {"type": "html", "label": " ", "readOnly": True},
        "export_file": {"label": "Fichier de remontée", "type": "binary", "readOnly": True},
    }

    __actions__ = [{
        "id": "export_sts_flux",
        "label": "Remonter vers STS-web",
        "type": "wizard",
        "steps": [
            {
                "id": "choose",
                "title": "1. Établissement",
                "fields": [
                    {"key": "info_html", "type": "html", "label": " "},
                    {"key": "school_id", "label": "Établissement", "resource": "schools"},
                ],
                "submitLabel": "Auditer",
                "rpc": "rpc_audit",
                "rpcParams": {"school_id": "school_id"},
            },
            {
                "id": "review",
                "title": "2. Audit",
                "fields": [
                    {"key": "audit_html", "type": "html", "label": " "},
                    {
                        "key": "anomaly_rows", "label": "Anomalies", "type": "text",
                        "widget": "list_preview", "fullWidth": True,
                        "widgetParams": {
                            "columns": [
                                {"key": "severity_label", "label": "Sévérité", "width": 120},
                                {"key": "label", "label": "Objet", "width": 220},
                                {"key": "message", "label": "Anomalie", "width": 520},
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
                    {"key": "export_file", "label": "Fichier de remontée", "type": "binary"},
                ],
                "submitLabel": "Fermer",
            },
        ],
    }]

    def __init__(self, id, info_html=None, school_id=None, audit_html=None, anomaly_rows=None,
                 result_html=None, export_file=None):
        self.id = id
        self.info_html = info_html
        self.school_id = school_id
        self.audit_html = audit_html
        self.anomaly_rows = anomaly_rows or []
        self.result_html = result_html
        self.export_file = export_file

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        html = (
            '<div style="border-left:4px solid #3B82F6;background:#EFF6FF;padding:12px 16px;'
            'border-radius:4px;margin-bottom:16px;">'
            "<p><strong>Fonction expérimentale.</strong> Le format du fichier de remontée n'est pas "
            "publié par le ministère. Sur les quatre familles de données que STS-web attend — "
            "services, ARE, indemnités, cours et alternances — seule la dernière a des balises "
            "attestées, déduites du code de <strong>CDT</strong>. Le fichier produit est donc "
            "<strong>partiel par construction</strong> : ni les volumes horaires de service, ni les "
            "ARE, ni les indemnités n'y figurent.</p>"
            "<p>Si vous disposez des spécifications officielles, ou d'un fichier "
            "<code>emp_sts</code> réel pseudonymisé, n'hésitez pas à me les envoyer.</p>"
            "</div>"
            "<p>L'audit passe d'abord : les anomalies <strong>bloquantes</strong> interdisent la "
            "génération, les <strong>avertissements</strong> la laissent passer.</p>"
        )
        return [cls(id=1, info_html=html)]

    @requires_access("write")
    def rpc_audit(self, db: Session, school_id=None) -> dict:
        """Audit seul : aucune écriture, aucun fichier produit."""
        school = _resolve_school(db, school_id)
        anomalies = audit(db, school)
        return {
            "audit_html": _audit_html(anomalies, school),
            "anomaly_rows": _anomaly_rows(anomalies),
        }

    @requires_access("write")
    def rpc_export(self, db: Session, school_id=None) -> dict:
        """
        Génère le fichier, après avoir **rejoué l'audit**. Le rejouer plutôt que se fier au
        résultat de l'étape précédente : entre les deux, l'utilisateur a pu corriger les anomalies
        dans un autre onglet — ou les aggraver.
        """
        school = _resolve_school(db, school_id)
        anomalies = audit(db, school)
        if has_blocking(anomalies):
            bloquantes = [a for a in anomalies if a["severity"] == BLOCKING]
            raise ValueError(
                f"{len(bloquantes)} anomalie(s) bloquante(s) subsistent : la remontée produirait "
                f"un fichier rejeté par STS-web. Corrigez-les puis relancez l'audit. "
                f"Première anomalie : {bloquantes[0]['label']} — {bloquantes[0]['message']}"
            )

        annee = SystemSetting.get_school_year(db)
        contenu = build_emp_sts(db, school)
        avertissements = [a for a in anomalies if a["severity"] == WARNING]

        html = (
            f"<p>Fichier de remontée généré pour <strong>{esc(school.name)}</strong> — RNE "
            f"{esc(school.uai)}, année {esc(annee)}-{esc(annee + 1)}.</p>"
            "<p>Chargez-le dans STS-web par <em>Imports</em> puis <em>Emploi du temps</em>. "
            "À la question « Souhaitez-vous conserver les services, ARE, indemnités saisies dans "
            "STSWEB… ? », <strong>répondez NON</strong> : répondre oui n'importerait que les cours, "
            "et ceux dont le service n'existe pas déjà seraient rejetés.</p>"
            "<p>Si la remontée réussit, STS-web n'affiche aucun message.</p>"
        )
        if avertissements:
            html += (
                f"<p>{len(avertissements)} avertissement(s) subsistent, sans empêcher la "
                f"génération — ils restent listés à l'étape précédente.</p>"
            )

        return {
            "result_html": html,
            "export_file": {
                "filename": export_filename(school, annee),
                "mime_type": "text/xml",
                "data_base64": base64.b64encode(contenu.encode("utf-8")).decode("ascii"),
            },
        }
