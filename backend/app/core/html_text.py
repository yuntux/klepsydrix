"""
Échappement HTML des valeurs interpolées dans les champs `type: "html"` des assistants (voir
architecture.md, "champ html" / GenericForm.vue).

**Pourquoi ce module existe.** Un champ `type: "html"` est rendu côté frontend via `innerHTML`
(components/GenericForm.vue) : le HTML produit ici est donc EXÉCUTÉ dans le navigateur de
l'utilisateur. Or les assistants y interpolent des libellés qui viennent de la base — et, pour
l'import STS-web, directement du fichier XML fourni par l'utilisateur. Sans échappement, un nom
d'enseignant, un libellé de MEF ou un code de division valant `<img src=x onerror=…>` suffisait à
faire exécuter du JavaScript dans la session de qui lance l'assistant (typiquement un
administrateur) : XSS stocké, avec la pleine capacité d'appeler l'API en son nom, le cookie de
session étant `HttpOnly` mais l'origine étant la même.

**Règle** : dans un f-string qui construit du HTML, toute valeur non littérale passe par `esc()`.
Y compris les entiers — non pas qu'ils soient dangereux, mais parce qu'une règle sans exception est
la seule qui survive à une relecture rapide ; le jour où le `count` devient un libellé, personne
n'aura à s'en apercevoir. `tests/test_wizard_html_escaping.py` vérifie la propriété de bout en bout
plutôt que la présence de l'appel.
"""
import html


def esc(value) -> str:
    """Valeur prête à être insérée dans du HTML (texte comme attribut). `None` devient une chaîne
    vide, jamais la chaîne « None »."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)
