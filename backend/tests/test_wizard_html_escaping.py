"""
Non-régression XSS sur les champs `type: "html"` des assistants (voir core/html_text.py).

Ces champs sont rendus par `innerHTML` côté frontend (components/GenericForm.vue) : le HTML produit
par un assistant s'EXÉCUTE dans le navigateur de qui le lance. Comme les libellés interpolés
viennent de la base — et, pour l'import STS-web, du fichier XML fourni par l'utilisateur — un nom
d'enseignant valant `<img src=x onerror=…>` suffisait à exécuter du JavaScript dans la session d'un
administrateur.

Le test vérifie la PROPRIÉTÉ (aucune balise hostile ne ressort intacte), pas la présence d'un appel
à `esc()` : c'est ce qui doit rester vrai quelle que soit la façon dont ces rapports seront
reconstruits plus tard.
"""
import pytest

from backend.app.core.html_text import esc

# Charges utiles classiques : une balise qui s'exécute sans interaction, une sortie d'attribut, et
# une fermeture de balise prématurée.
PAYLOADS = [
    '<img src=x onerror="alert(1)">',
    '"><script>alert(1)</script>',
    "'; alert(1); //",
]


class TestEscHelper:
    @pytest.mark.parametrize("payload", PAYLOADS)
    def test_no_active_markup_survives(self, payload):
        rendered = esc(payload)
        assert "<" not in rendered
        assert ">" not in rendered
        assert '"' not in rendered
        assert "'" not in rendered

    def test_none_becomes_an_empty_string_not_the_word_none(self):
        assert esc(None) == ""

    def test_plain_text_is_left_readable(self):
        assert esc("Collège Jean Jaurès") == "Collège Jean Jaurès"


class TestWizardReportsEscapeTheirData:
    """Bout en bout sur les constructeurs de rapports qui interpolent des données."""

    def test_skipped_report_escapes_labels_codes_and_reasons(self):
        from backend.app.models.wizard_sts_import import _skipped_html, ENTITY_LABELS

        plan = {key: {"create": [], "update": [], "skipped": []} for key, _ in ENTITY_LABELS}
        first_key = ENTITY_LABELS[0][0]
        plan[first_key]["skipped"] = [{
            "label": '<img src=x onerror="alert(1)">',
            "code": "<script>alert(2)</script>",
            "reason": "<b>gras</b>",
        }]

        html = _skipped_html(plan)

        assert "<img" not in html
        assert "<script>" not in html
        assert "<b>" not in html
        assert "&lt;img" in html  # la valeur reste VISIBLE, simplement inerte

    def test_missing_report_escapes_labels_and_codes(self):
        from backend.app.models.wizard_sts_import import _missing_html, ENTITY_LABELS

        missing = {key: [] for key, _ in ENTITY_LABELS}
        missing[ENTITY_LABELS[0][0]] = [{"label": "<script>alert(1)</script>", "code": "<x>"}]

        html = _missing_html(missing)

        assert "<script>" not in html
        assert "<x>" not in html

    def test_teacher_assignment_warnings_are_escaped(self):
        from backend.app.models.wizard_teacher_assignment import _render_warnings_html

        html = _render_warnings_html([{"message": '<img src=x onerror="alert(1)">'}])

        assert "<img" not in html
        assert "&lt;img" in html

    def test_audit_report_escapes_the_school_name(self):
        from backend.app.models.wizard_sts_export import _audit_html

        class _School:
            name = '<img src=x onerror="alert(1)">'

        html = _audit_html([], _School())

        assert "<img" not in html
