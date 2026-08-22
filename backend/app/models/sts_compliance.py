from sqlalchemy.orm import Session


class StsComplianceMixin:
    """
    Mixin pour une table de référence dont certaines lignes forment la nomenclature officielle
    STS-web (`is_sts_compliant=True`) et d'autres sont des valeurs ajoutées localement par un
    établissement, sans garantie d'être acceptées par STS-web à la remontée.

    Partagé par `Modality`, `RefElectionMethod` et `RefWeightingCoefficient` : trois tables vers
    lesquelles un `Course` pointe, et dont la conformité conditionne `Course.is_exported_to_sts`
    (voir `sts_audit.py`, contrôles `_modalites_non_conformes` / `_modes_election_non_conformes` /
    `_ponderations_non_conformes`).

    **`is_sts_compliant` n'est écrit qu'une fois, par les `INSERT` SQL bruts des seeds de
    `init_db.py`** — jamais par l'API. Un `INSERT`/`UPDATE` brut ne passe pas par `create()`/
    `update()` (voir `receive_before_insert`/`receive_before_update`, base.py) : c'est ce qui rend
    possible d'écrire `True` ici alors que l'API ne le pourra jamais.

    Déclarer AVANT `Base` (`class Modality(StsComplianceMixin, Base)`) pour que
    `super().create()`/`.update()`/`.delete()` délèguent correctement à `CRUDMixin`.
    """

    @classmethod
    def create(cls, db: Session, vals: dict):
        """
        Refuse une tentative de poser `is_sts_compliant` à vrai dès la création. Une clé absente,
        ou explicitement fausse, ne change rien au défaut (`False`) : seule une tentative de la
        faire passer à vrai est rejetée.
        """
        if vals.get("is_sts_compliant"):
            raise ValueError(
                "is_sts_compliant ne peut pas être fixé à la création : seule la nomenclature "
                "officielle STS-web, posée une fois pour toutes par le seed de référence "
                "(init_db.py), porte cette valeur."
            )
        return super().create(db, vals)

    def update(self, db: Session, vals: dict):
        """
        Refuse tout changement RÉEL de `is_sts_compliant`, dans un sens comme dans l'autre. La
        valeur courante (`self.is_sts_compliant`) est lue ICI, avant l'appel à `super().update()`
        qui la remplacerait déjà par celle du payload — un `@constrains` classique, qui ne
        s'exécute qu'après le flush interne de `CRUDMixin.update()`, arrive trop tard pour la
        comparer à l'ancienne valeur (voir architecture.md, section sur ce mixin).

        Une valeur IDENTIQUE à l'existante n'est pas un changement et passe silencieusement : un
        formulaire réémet l'enregistrement complet à chaque sauvegarde (y compris les champs en
        lecture seule non touchés), la bloquer casserait toute modification anodine d'une ligne
        déjà conforme (renommer un libellé, par exemple).
        """
        if "is_sts_compliant" in vals and bool(vals["is_sts_compliant"]) != self.is_sts_compliant:
            raise ValueError(
                "is_sts_compliant n'est jamais modifiable : c'est la conformité à la nomenclature "
                "STS-web, déterminée une fois pour toutes par le seed de référence."
            )
        return super().update(db, vals)

    def delete(self, db: Session):
        """
        Une ligne de la nomenclature officielle ne se supprime jamais, qu'elle soit référencée ou
        non par un cours — contrairement à une ligne non conforme ajoutée localement, qui reste
        une donnée ordinaire (protégée seulement si elle est effectivement utilisée, via
        `ondelete=RESTRICT` côté clé étrangère).
        """
        if self.is_sts_compliant:
            raise ValueError(
                f"Impossible de supprimer « {self.display_name} » : elle appartient à la "
                f"nomenclature officielle STS-web (is_sts_compliant)."
            )
        return super().delete(db)
