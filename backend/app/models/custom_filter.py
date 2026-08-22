"""
Filtres personnalisés persistés sur une generic list view (voir architecture.md, "Filtres
personnalisés façon Odoo") : une ligne par filtre sauvegardé par un utilisateur, sur le même format
de domaine JSON que `IrModelAccess.domain` (voir core/access_control.py) — notation Odoo de tuples
préfixés (`& | !`).

Évaluation du domaine CÔTÉ CLIENT (le frontend charge déjà tout le jeu de données d'une ressource en
mémoire via fetchAllGenericItems) : ce modèle ne sert qu'à PERSISTER/PARTAGER la définition du
filtre entre utilisateurs, jamais à filtrer une requête SQL — `compile_domain()` n'est utilisé ici
qu'en validation à l'écriture (voir _validate_domain), pour rejeter un domaine structurellement
invalide avant qu'il n'atteigne le frontend.
"""
from typing import Optional
from sqlalchemy import String, Text, Boolean, ForeignKey, UniqueConstraint, false as sa_false
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from backend.app.models.base import Base, constrains


class CustomFilter(Base):
    __tablename__ = "custom_filters"
    __table_args__ = (
        UniqueConstraint("user_id", "resource", "name", name="uq_custom_filter_user_resource_name"),
    )
    # Préférence utilisateur, orthogonale aux données de planning que le mode exclusif protège —
    # même raisonnement que ResGroup/IrModelAccess (voir access.py).
    __exclusive_mode_exempt__ = True

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, info={"label": "Nom du filtre"})
    # Clé de ressource = tablename (même valeur que ui.json::resourceKey et generic.py::MODEL_MAP).
    resource: Mapped[str] = mapped_column(String(100), nullable=False, index=True, info={"label": "Ressource"})
    # Domaine Odoo sérialisé JSON — même format que IrModelAccess.domain, voir docstring de module.
    domain: Mapped[Optional[str]] = mapped_column(Text, nullable=True, info={"label": "Domaine (JSON)"})
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Partagé"})
    is_auto_apply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Application automatique"})
    # Propriétaire — distinct de create_user_id (audit, voir base.py, toujours nullable/SET NULL) :
    # ondelete=CASCADE, car un CustomFilter orphelin (propriétaire supprimé) ne satisferait plus
    # jamais le domaine "user_id = user.id" et deviendrait un enregistrement fantôme, non
    # supprimable par personne d'autre qu'un Admin.
    #
    # nullable=True côté SQL bien que LOGIQUEMENT requis (voir _validate_owner ci-dessous, qui
    # applique l'invariant réel) : generic.py::make_pydantic_model rend un champ non-nullable sans
    # défaut OBLIGATOIRE dans le payload JSON de création — mais ce champ n'est justement JAMAIS
    # fourni par le client (create() ci-dessous l'injecte depuis db.klepsydrix_user_id, voir
    # anti-spoofing), un payload conforme au schéma généré échouerait donc toujours par
    # construction. Même compromis que AUDIT_COLUMNS (create_user_id etc., base.py), qui va plus
    # loin en excluant carrément ces colonnes du schéma — impossible ici sans modifier generic.py
    # pour un seul modèle, AUDIT_COLUMNS étant une liste de noms globale à toutes les tables.
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True,
        info={"label": "Propriétaire", "readOnly": True},
    )
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    @property
    def display_name(self) -> str:
        return self.name

    @classmethod
    def create(cls, db: Session, vals: dict):
        # Anti-spoofing : info={"readOnly": True} n'est qu'un hint frontend (jamais appliqué côté
        # serveur, voir generic.py) — sans cette ligne, n'importe quel payload pourrait créer un
        # filtre au nom d'un autre utilisateur. Mode système (db.klepsydrix_user_id absent : seed/
        # import) : vals["user_id"] doit alors être fourni explicitement par l'appelant.
        user_id = getattr(db, "klepsydrix_user_id", None)
        if user_id is not None:
            vals["user_id"] = user_id
        return super().create(db, vals)

    def update(self, db: Session, vals: dict):
        # La propriété ne se réassigne jamais via l'API, même par l'auteur — un filtre partagé
        # reste attribué à son créateur d'origine. Pop plutôt que reject : un client qui renvoie
        # l'enregistrement complet ne doit pas échouer sur ce champ readOnly, juste le voir ignoré.
        vals.pop("user_id", None)
        return super().update(db, vals)

    @constrains()
    def _validate_owner(self, db: Session):
        # Invariant réel malgré la colonne SQL nullable (voir son commentaire) — @constrains() sans
        # argument s'exécute inconditionnellement (même convention que service.py), contrairement à
        # @constrains("resource") ci-dessous qui ne s'exécute que si "resource" a été fourni : ici,
        # user_id est presque toujours ABSENT du payload client (c'est tout le problème que la
        # colonne nullable contourne), donc une garde conditionnelle sur sa présence ne se
        # déclencherait jamais dans le cas qu'elle est censée couvrir.
        if self.user_id is None:
            raise ValueError("Un filtre personnalisé doit avoir un propriétaire.")

    @constrains("resource")
    def _validate_resource(self, db: Session):
        from backend.app.api.generic import MODEL_MAP  # import tardif : generic.py importe les modèles, pas l'inverse
        if self.resource not in MODEL_MAP:
            raise ValueError(f"« {self.resource} » n'est pas une ressource connue.")

    @constrains("domain", "resource")
    def _validate_domain(self, db: Session):
        # Validation STRUCTURELLE uniquement (JSON bien formé, champs/opérateurs valides sur le
        # modèle cible) — voir docstring de module : l'évaluation réelle appartient au frontend.
        if not self.domain:
            return
        from backend.app.api.generic import MODEL_MAP
        from backend.app.core.access_control import compile_domain
        from backend.app.models.user import User
        target_model = MODEL_MAP.get(self.resource)
        if target_model is None:
            return  # déjà signalé par _validate_resource
        user_id = getattr(db, "klepsydrix_user_id", None)
        user = db.get(User, user_id) if user_id is not None else None
        try:
            compile_domain(target_model, self.domain, user)
        except Exception as e:
            raise ValueError(f"Domaine de filtre invalide pour « {self.resource} » : {e}")
