from datetime import date, datetime, time
from typing import Optional, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy import Column, Integer, String, ForeignKey
from backend.app.models.base import Base, constrains

class Classroom(Base):
    __tablename__ = "classrooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False, info={"label": "Code de la salle", "placeholder": "ex: S101"})
    name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom de la salle", "placeholder": "ex: Salle 101"})
    # Nullable = capacité illimitée (ex: un groupe de salles "toutes équivalentes, pas de limite
    # connue") — condition posée pour l'homogénéité de groupe (_validate_capacity_homogeneity) :
    # NULL est une valeur comparable à part entière, pas une absence de contrainte.
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={"label": "Capacité de places", "min": 1, "max": 200})

    ref_classroom_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_classroom_types.id", ondelete="RESTRICT"), nullable=True, info={"label": "Type de salle"})
    # Groupe de salles auquel cette salle appartient (arbre, profondeur arbitraire — voir
    # classroom_closure.py pour la closure table qui maintient l'arbre à jour). NULL = salle
    # racine (autonome, ou groupe de plus haut niveau).
    parent_classroom_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("classrooms.id", ondelete="SET NULL"), nullable=True, info={"label": "Groupe de salle"})

    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})
    site_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, info={"label": "Site / Bâtiment"})

    # Relations de navigation
    school: Mapped[Optional["School"]] = relationship("School", back_populates="classrooms")
    site: Mapped[Optional["Site"]] = relationship("Site", back_populates="classrooms")
    ref_classroom_type: Mapped[Optional["RefClassroomType"]] = relationship("RefClassroomType")
    parent_classroom: Mapped[Optional["Classroom"]] = relationship("Classroom", remote_side=[id], foreign_keys=[parent_classroom_id], back_populates="children_classrooms")
    children_classrooms: Mapped[list["Classroom"]] = relationship("Classroom", back_populates="parent_classroom", foreign_keys=[parent_classroom_id])
    # viewonly : Course est le seul propriétaire de CourseClassroomRequirement au sens CRUDMixin
    # (voir course_classroom_requirement.py).
    classroom_requirements: Mapped[list["CourseClassroomRequirement"]] = relationship("CourseClassroomRequirement", back_populates="classroom", viewonly=True, info={"label": "Cours utilisant cette salle", "readOnly": True})

    @constrains()
    def _ensure_closure_reflexive_row(self, db: Session):
        """
        S'exécute à CHAQUE create()/update() (pas seulement quand parent_classroom_id change) :
        garantit que toute salle, même créée sans parent_classroom_id dans les vals (le cas le
        plus courant), a bien sa ligne réflexive (id, id, 0) dans classroom_closure — condition
        pour que leaf_classroom_ids_under/is_descendant_or_equal fonctionnent même pour une salle
        qui n'a jamais eu de parent ni d'enfant. Opération idempotente et bon marché (un SELECT +
        un INSERT conditionnel), volontairement inconditionnelle plutôt que scopée à un champ.
        """
        from backend.app.models.classroom_closure import ensure_reflexive_row
        ensure_reflexive_row(db, self.id)

    @constrains('parent_classroom_id')
    def _validate_and_sync_classroom_tree(self, db: Session):
        """
        Détection de cycle (topologie d'arbre stricte, jamais un graphe) + maintenance de la
        closure table (classroom_closure.py) à chaque changement de parent_classroom_id, y
        compris la première affectation et la remise à NULL (détachement).
        """
        from backend.app.models.classroom_closure import detect_cycle, reparent_subtree

        if self.parent_classroom_id is not None:
            if self.parent_classroom_id == self.id:
                raise ValueError("Une salle ne peut pas être son propre groupe parent.")
            if detect_cycle(db, self.id, self.parent_classroom_id):
                raise ValueError("Ce lien créerait un cycle dans l'arbre des groupes de salles.")

        reparent_subtree(db, self.id, self.parent_classroom_id)

        # Un groupe ne peut pas avoir de type de salle — nettoyage silencieux, jamais un rejet
        # (l'opération de rattachement d'un enfant ne doit jamais échouer pour cette raison).
        if self.parent_classroom_id is not None:
            new_parent = db.get(Classroom, self.parent_classroom_id)
            if new_parent is not None and new_parent.ref_classroom_type_id is not None:
                new_parent.update(db, {"ref_classroom_type_id": None})

    @constrains('ref_classroom_type_id')
    def _validate_group_has_no_type(self, db: Session):
        """Symétrique de ce qui précède : si cette salle a déjà des enfants (c'est un groupe) et
        qu'on tente de lui affecter un type, le type est ignoré silencieusement plutôt qu'un rejet."""
        if self.ref_classroom_type_id is not None and self.children_classrooms:
            self.update(db, {"ref_classroom_type_id": None})

    @constrains('capacity', 'parent_classroom_id')
    def _validate_capacity_homogeneity(self, db: Session):
        """Toutes les salles d'un même groupe (mêmes enfants directs d'un même parent) doivent
        avoir la même capacité, ou être toutes NULL (illimitée) — jamais un mélange."""
        if self.parent_classroom_id is None:
            return
        siblings = db.query(Classroom).filter(
            Classroom.parent_classroom_id == self.parent_classroom_id,
            Classroom.id != self.id,
        ).all()
        for sibling in siblings:
            if (sibling.capacity is None) != (self.capacity is None):
                raise ValueError("Toutes les salles d'un même groupe doivent être soit toutes à capacité illimitée, soit toutes à la même capacité numérique.")
            if sibling.capacity is not None and sibling.capacity != self.capacity:
                raise ValueError(f"Capacité incohérente dans ce groupe de salles (attendu {sibling.capacity}).")
