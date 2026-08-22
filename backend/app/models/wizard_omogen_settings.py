"""
Wizard « Configurer OMOGEN » (menu Paramètres) — placeholder volontaire, sans aucune action réelle :
un simple message expliquant que le paramétrage OMOGEN ne peut pas encore être mis en place auprès
du ministère, et n'entrera en service que lorsque suffisamment d'établissements en feront la
demande. Sert à inciter les établissements intéressés à nous contacter, en attendant que la demande
soit suffisante pour justifier le développement de l'intégration réelle.

Un seul step, un seul champ (info_html, même convention que wizard_course_placement.py), et
`editableForm: False` (voir GenericWizard.vue) pour n'afficher QUE le bouton Annuler — aucun bouton
de soumission n'aurait de sens ici, il n'y a rien à confirmer.
"""
from sqlalchemy.orm import Session
from backend.app.models.base import TransientModel


class WizardOmogenSettings(TransientModel):
    __tablename__ = "wizard_omogen_settings"
    _fields = ["id", "info_html"]
    # Label non vide (espace) : un label "" retombe sur la clé du champ comme libellé affiché
    # (App.vue, `prop.title || key` — "" est falsy en JS), ce qu'on veut justement éviter pour un
    # simple bloc de texte formaté qui n'a pas besoin d'étiquette.
    _field_info = {"info_html": {"type": "html", "label": " ", "readOnly": True}}
    __actions__ = [{
        "id": "configure_omogen",
        "label": "Configurer OMOGEN",
        "type": "wizard",
        "steps": [
            {
                "id": "info",
                "title": "Configurer OMOGEN",
                "isLast": True,
                "editableForm": False,
                "fields": [{"key": "info_html", "type": "html", "label": " "}],
            },
        ],
    }]

    def __init__(self, id, info_html):
        self.id = id
        self.info_html = info_html

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        html = (
            "<p>Le paramétrage OMOGEN ne peut pas encore être mis en place : "
            "Les échanges préalables avec le ministère de l'Éducation Nationale débuteront"
            "lorsque des établissements en feront la demande.</p>"
            "<p>Si vous êtes intéressé, contactez-nous pour en faire la demande.</p>"
        )
        return [cls(id=1, info_html=html)]
