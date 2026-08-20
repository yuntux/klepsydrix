"""
Droits façon Odoo — voir architecture.md, plan "Multi-SGBD, Multi-Base, Utilisateurs/IDP, Droits,
Console Admin". Modèle volontairement réduit par rapport à Odoo : `IrModelAccess` fusionne
`ir.model.access` (perms par modèle) et le domaine par enregistrement (`ir.rule` chez Odoo) en une
seule ligne — pas de modèle `ir.rule` séparé, pas de `res.groups.privilege` (organisation d'IHM,
pas un niveau de contrôle en plus).

Plusieurs lignes pour un même (modèle, groupe) se combinent en OR ; AUCUNE ligne pour un modèle =
aucun accès, pour quiconque (voir CRUDMixin, base.py).
"""
from typing import Optional
from sqlalchemy import Table, Column, Integer, String, Boolean, ForeignKey, Text, false as sa_false
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from backend.app.models.base import Base

res_group_implied = Table(
    "res_group_implied",
    Base.metadata,
    Column("group_id", Integer, ForeignKey("res_groups.id", ondelete="CASCADE"), primary_key=True),
    Column("implied_group_id", Integer, ForeignKey("res_groups.id", ondelete="CASCADE"), primary_key=True),
)

res_group_users = Table(
    "res_group_users",
    Base.metadata,
    Column("group_id", Integer, ForeignKey("res_groups.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class ResGroup(Base):
    __tablename__ = "res_groups"
    # Gestion des utilisateurs/de la sécurité, orthogonale aux données de planning que le mode
    # exclusif protège — voir User.__exclusive_mode_exempt__ (models/user.py), core/exclusive_mode.py.
    __exclusive_mode_exempt__ = True

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, info={"label": "Nom du groupe"})
    # Groupe créé par le seed (Admin, Consultation — voir init_db.py::seed_admin_access/
    # seed_readonly_access) : ni renommable ni supprimable (voir update/delete ci-dessous), même
    # patron que Partition.is_system_generated (models/group.py). Seule son appartenance
    # (`user_ids`) reste modifiable — voir update() : un admin doit pouvoir ajouter/retirer des
    # membres du groupe Admin, seule sa structure propre est figée.
    is_system_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Généré par le système"})

    # Héritage façon Odoo (res.groups.implied_ids) : appartenir à ce groupe donne aussi les droits
    # des groupes impliqués — résolu par resolve_effective_groups() (voir plus bas), pas ici.
    implied_groups: Mapped[list["ResGroup"]] = relationship(
        "ResGroup", secondary=res_group_implied,
        primaryjoin="ResGroup.id==res_group_implied.c.group_id",
        secondaryjoin="ResGroup.id==res_group_implied.c.implied_group_id",
        info={"label": "Groupes impliqués"},
    )
    users: Mapped[list["User"]] = relationship("User", secondary=res_group_users, back_populates="groups", info={"label": "Utilisateurs"})
    accesses: Mapped[list["IrModelAccess"]] = relationship("IrModelAccess", back_populates="group", info={"label": "Droits"})

    @property
    def display_name(self) -> str:
        return self.name

    @classmethod
    def create(cls, db: Session, vals: dict):
        # _system_write : voir Partition.create (models/group.py) — même convention, réservée au
        # code interne (seed_admin_access/seed_readonly_access créent leurs lignes en SQL brut,
        # donc ne l'utilisent même pas ; ce garde-fou couvre tout futur code ORM).
        is_system_write = vals.pop('_system_write', False)
        if vals.get('is_system_generated') and not is_system_write:
            raise ValueError("Le champ is_system_generated ne peut être positionné que par le système.")
        return super().create(db, vals)

    def update(self, db: Session, vals: dict):
        is_system_write = vals.pop('_system_write', False)
        if 'is_system_generated' in vals and vals['is_system_generated'] != self.is_system_generated and not is_system_write:
            raise ValueError("Le champ is_system_generated ne peut être modifié que par le système.")

        if self.is_system_generated:
            # Carve-out volontaire : seule l'appartenance (user_ids) reste modifiable sur un groupe
            # système — instance_endpoints.py::create_database en dépend déjà pour rattacher l'admin
            # désigné d'une nouvelle base au groupe Admin.
            forbidden_keys = set(vals.keys()) - {"user_ids"}
            if forbidden_keys:
                raise ValueError(f"Le groupe « {self.name} » est généré par le système : seule son appartenance (utilisateurs) peut être modifiée.")

        instance = super().update(db, vals)

        if instance.name == "Admin" and not instance.users:
            raise ValueError("Impossible de retirer le dernier utilisateur du groupe Admin.")

        return instance

    def delete(self, db: Session):
        if self.is_system_generated:
            raise ValueError(f"Le groupe « {self.name} » est généré par le système : il ne peut pas être supprimé.")
        return super().delete(db)


def _admin_group(db: Session) -> Optional["ResGroup"]:
    """Le groupe "Admin" de la base courante (voir init_db.py::seed_admin_access) — utilisé par les
    garde-fous "dernier administrateur" (ResGroup.update ci-dessus, User.update/delete,
    models/user.py)."""
    return db.query(ResGroup).filter(ResGroup.name == "Admin").first()


class IrModelAccess(Base):
    __tablename__ = "ir_model_access"
    # Voir ResGroup.__exclusive_mode_exempt__ ci-dessus.
    __exclusive_mode_exempt__ = True

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True, info={"label": "Modèle (nom de table)"})
    group_id: Mapped[int] = mapped_column(ForeignKey("res_groups.id", ondelete="CASCADE"), nullable=False, info={"label": "Groupe"})
    perm_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, info={"label": "Lecture"})
    perm_write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Écriture"})
    perm_create: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Création"})
    perm_unlink: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Suppression"})
    # Domaine Odoo sérialisé JSON (liste de tuples/opérateurs logiques) — voir base.py::_compile_domain.
    # None/"" = aucune restriction par enregistrement (accès à tout, dans la limite des perm_*).
    domain: Mapped[Optional[str]] = mapped_column(Text, nullable=True, info={"label": "Domaine (JSON)"})
    # Ligne créée par le seed (seed_admin_access/seed_readonly_access, init_db.py) : ni modifiable
    # ni supprimable (voir update/delete ci-dessous) — contrairement à ResGroup.is_system_generated,
    # aucun carve-out ici : une ligne de droit système n'a pas d'équivalent "appartenance" à faire
    # évoluer, elle est protégée dans son intégralité.
    is_system_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Généré par le système"})

    group: Mapped["ResGroup"] = relationship("ResGroup", back_populates="accesses")

    @property
    def display_name(self) -> str:
        return f"{self.model} ({self.group.name if self.group else '?'})"

    @classmethod
    def create(cls, db: Session, vals: dict):
        is_system_write = vals.pop('_system_write', False)
        if vals.get('is_system_generated') and not is_system_write:
            raise ValueError("Le champ is_system_generated ne peut être positionné que par le système.")
        return super().create(db, vals)

    def update(self, db: Session, vals: dict):
        is_system_write = vals.pop('_system_write', False)
        if 'is_system_generated' in vals and vals['is_system_generated'] != self.is_system_generated and not is_system_write:
            raise ValueError("Le champ is_system_generated ne peut être modifié que par le système.")
        if self.is_system_generated:
            raise ValueError("Ce droit est généré par le système : il ne peut pas être modifié.")
        return super().update(db, vals)

    def delete(self, db: Session):
        if self.is_system_generated:
            raise ValueError("Ce droit est généré par le système : il ne peut pas être supprimé.")
        return super().delete(db)
