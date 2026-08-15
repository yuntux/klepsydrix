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
from sqlalchemy import Table, Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
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

    group: Mapped["ResGroup"] = relationship("ResGroup", back_populates="accesses")

    @property
    def display_name(self) -> str:
        return f"{self.model} ({self.group.name if self.group else '?'})"
