"""
Petits accesseurs de texte partagés entre les parseurs XML SIECLE/STS (sts_flux.py,
eleves_flux.py) : extraits ici pour ne pas dupliquer la même paire de fonctions dans chaque
module au fil des formats ajoutés.
"""


def text(node, tag: str):
    child = node.find(tag)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def first_label(node, *tags):
    """Premier libellé renseigné, dans l'ordre de préférence donné."""
    for tag in tags:
        value = text(node, tag)
        if value:
            return value
    return None
