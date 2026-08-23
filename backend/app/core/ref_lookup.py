"""
Résolution d'un référentiel simple (`code`, `name`) par son code, avec création de la ligne si le
code est inconnu — partagé entre les wizards d'import (STS-web, élèves/responsables) pour les
nomenclatures que le flux désigne par un code sans que Klepsydrix en connaisse la liste
exhaustive (grade, fonction, académie, motif de sortie, lien de parenté, profession...).

Perdre l'information parce qu'un code n'est pas seedé serait pire que d'ajouter une ligne au
référentiel — l'utilisateur peut toujours en corriger le libellé après coup. Réservé aux
référentiels à nomenclature OUVERTE : RefRegime, RefLegalGuardian, RefTitle (nomenclatures
fermées et seedées) ne passent jamais par ici, une valeur inconnue y est simplement laissée de
côté plutôt qu'inventée.
"""


def find_or_create_ref(db, model, code: str, name: str = None):
    code = (code or "").strip()
    if not code:
        return None
    existing = db.query(model).filter(model.code == code).first()
    if existing:
        return existing.id
    return model.create(db, {"code": code[:20], "name": (name or code)[:100]}).id
