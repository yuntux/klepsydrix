from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session, validates
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import Integer, ForeignKey, UniqueConstraint
from backend.app.models.base import Base, constrains


class CourseClassroomRequirement(Base):
    """
    Remplace l'ancienne table course_classrooms (M2M, PK composite qui interdisait toute
    multiplicité) — une exigence de salle d'un cours, précise ou de groupe, avec un nombre de
    salles nécessaires (quantity, toujours 1 pour une salle-feuille précise). Peut être attachée
    à un cours parent (avant même que ses enfants existent — voir _cascade_decrement_parent_group_line)
    ou à un cours enfant.
    """
    __tablename__ = "course_classroom_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True, info={"label": "Cours"})
    # Immuable après création (voir _validate_classroom_id_immutable) : seule quantity peut
    # évoluer sur une ligne existante — "résoudre" une exigence de groupe en une salle précise se
    # fait toujours en créant une NOUVELLE ligne (voir room_solver.py::_write_back_classroom_assignment),
    # jamais en réattribuant classroom_id sur la ligne existante.
    classroom_id: Mapped[int] = mapped_column(Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True, info={"label": "Salle ou groupe de salles", "readOnlyExpr": "model.id != null && !String(model.id).startsWith('new_')"})
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, info={"label": "Nombre de salles", "min": 1, "readOnlyExpr": ""})

    # Attribut Python transitoire, PAS une colonne (pas de Mapped[...]/mapped_column) : jamais
    # persisté, jamais présent sur une ligne rechargée depuis la base. Passé explicitement par
    # l'appelant (room_solver.py::_write_back_classroom_assignment) à la création d'une ligne de
    # RÉSOLUTION (une unité de besoin déjà décomptée une fois lors de la création de la ligne de
    # groupe d'origine) pour empêcher _cascade_decrement_parent_group_line de décompter cette même
    # unité une seconde fois auprès d'un ancêtre. Sans ce flag explicite, rien ne permettrait de
    # distinguer "cette ligne représente un besoin neuf" (à décompter) de "cette ligne ne fait que
    # préciser un besoin déjà décompté" (à ne pas décompter à nouveau) — les deux se traduisent,
    # côté ORM, par un CourseClassroomRequirement.create() identique.
    _skip_ancestor_decrement: bool = False

    __table_args__ = (
        UniqueConstraint("course_id", "classroom_id", name="uq_course_classroom_requirement"),
    )

    course: Mapped["Course"] = relationship("Course", back_populates="classroom_requirements")
    # viewonly : Course est le seul propriétaire au sens CRUDMixin (collection possédée sur
    # Course.classroom_requirements) — exposer cette relation en écriture depuis Classroom
    # permettrait à un Classroom.update() d'écraser les exigences de TOUS les autres cours
    # utilisant cette salle et absents de la liste soumise.
    classroom: Mapped["Classroom"] = relationship("Classroom", back_populates="classroom_requirements", viewonly=True)

    @property
    def display_name(self) -> str:
        room_name = self.classroom.name if self.classroom else str(self.classroom_id)
        return f"{room_name} ×{self.quantity}" if self.quantity > 1 else room_name

    @constrains('quantity', 'classroom_id')
    def _validate_leaf_quantity(self, db: Session):
        if not self.classroom.children_classrooms and self.quantity != 1:
            raise ValueError("Une exigence sur une salle précise (pas un groupe) ne peut porter que sur une seule salle (quantity=1).")

    @validates('classroom_id')
    def _validate_classroom_id_immutable(self, key, value):
        """
        Rejette un changement RÉEL de classroom_id sur une ligne déjà persistée — pas sa simple
        présence dans les vals soumis. GenericListModal.vue::onUpdateItem soumet TOUJOURS la ligne
        entière (tous ses champs, classroom_id inclus) à chaque édition, y compris pour un simple
        changement de `quantity` seule (bug constaté : un check sur la seule présence de la clé
        rejetait alors ce cas légitime à tort).

        `@validates` (natif SQLAlchemy), pas `@constrains` (le mécanisme propre à ce projet) :
        volontaire, pas un oubli. `@constrains` s'exécute tard (après TOUS les setattr, dans une
        boucle sur dir(instance) triée alphabétiquement) — `_cascade_decrement_parent_group_line`
        ('c' < 'v') s'exécute AVANT ce contrôle et fait sa propre requête, qui déclenche un
        autoflush : la valeur déjà modifiée est alors flushée en base avant que ce contrôle ne
        s'exécute, et plus rien ne distingue alors "valeur inchangée" de "valeur changée puis
        flushée" (vérifié empiriquement : `get_history(passive=PASSIVE_OFF)` retombait à
        has_changes()=False après cet autoflush intermédiaire, laissant passer un changement réel).
        `@validates` s'exécute de façon synchrone à l'instant du setattr lui-même, avant tout ce
        qui suit (donc avant tout risque d'autoflush) — `self.classroom_id` y vaut encore
        l'ANCIENNE valeur au moment de la comparaison.
        """
        if sa_inspect(self).transient:
            return value  # première affectation, à la création : toujours autorisée
        if self.classroom_id == value:
            return value  # valeur resoumise identique (ex: édition de `quantity` seule) : rien à rejeter
        raise ValueError("La salle ou le groupe d'une exigence ne peut plus être modifiée après création (seule la quantité l'est) — voir room_solver.py::_write_back_classroom_assignment pour le mécanisme de résolution.")

    @constrains('course_id', 'classroom_id')
    def _cascade_decrement_parent_group_line(self, db: Session):
        """
        Voir architecture.md / plan salles §1.5 : quand ce cours (typiquement un enfant) reçoit
        une nouvelle exigence de salle — précise OU de groupe, y compris un sous-groupe — qui est
        un descendant-ou-égal (closure table) d'un groupe G déjà déclaré sur son PARENT, la ligne
        de groupe du parent pour G est décrémentée d'autant (supprimée si elle atteint 0). Si
        cette exigence est elle-même une salle-feuille précise, elle est en plus recopiée sur le
        parent (comme les 6 autres relations de ressources, `Course._cascade_resources_to_parent`)
        — le parent et l'enfant partagent alors la même salle précise, ce qui est normal (même
        bloc horaire composé, pas deux réservations indépendantes — `hierarchy_overlap` les
        exclut déjà du contrôle de conflit dans le domaine COURSE_PLACEMENT).

        ⚠️ Cette cascade ne se déclenche QUE via CourseClassroomRequirement.create()/update()
        (CRUDMixin) — jamais via une écriture directe qui contournerait le chemin d'écriture
        normal (voir décision Option 1 du plan pour le write-back CLASSROOM_ASSIGNMENT).

        ⚠️ `_skip_ancestor_decrement` (voir sa définition plus haut) : quand cette ligne représente
        la RÉSOLUTION d'une unité de besoin déjà décomptée une fois (au moment de la création de
        la ligne de groupe d'origine, pas maintenant), l'étape 1 (copier la salle précise sur le
        parent) reste inconditionnelle — le parent doit toujours refléter la salle réellement
        utilisée — mais l'étape 2 (décompter l'ancêtre) doit être sautée, sous peine de compter
        deux fois la même unité de besoin (bug confirmé empiriquement, voir test_solver.py). Le
        flag est propagé tel quel à l'appel récursif de l'étape 1 : si le parent a lui-même un
        parent, la même unité ne doit pas non plus y être décomptée deux fois.
        """
        from backend.app.models.classroom import Classroom
        from backend.app.models.classroom_closure import is_descendant_or_equal

        course = self.course
        if course is None or course.parent_id is None:
            return
        parent = course.parent
        if parent is None:
            return

        is_leaf = not self.classroom.children_classrooms

        # 1. Si c'est une salle-feuille précise, la recopier sur le parent (comme les 6 autres
        # relations de ressources) — sauf si déjà présente (contrainte d'unicité course/classroom).
        if is_leaf:
            already_on_parent = db.query(CourseClassroomRequirement).filter(
                CourseClassroomRequirement.course_id == parent.id,
                CourseClassroomRequirement.classroom_id == self.classroom_id,
            ).first()
            if already_on_parent is None:
                CourseClassroomRequirement.create(db, {
                    "course_id": parent.id,
                    "classroom_id": self.classroom_id,
                    "quantity": 1,
                    "_skip_ancestor_decrement": self._skip_ancestor_decrement,
                })

        if self._skip_ancestor_decrement:
            return

        # 2. Décrémenter la ligne de groupe du parent qui couvre ce classroom_id (précis ou
        # sous-groupe), s'il y en a une.
        parent_group_lines = db.query(CourseClassroomRequirement).filter(
            CourseClassroomRequirement.course_id == parent.id,
            CourseClassroomRequirement.id != self.id,
        ).all()
        for parent_line in parent_group_lines:
            if not parent_line.classroom.children_classrooms:
                continue  # pas un groupe, rien à décrémenter
            if not is_descendant_or_equal(db, parent_line.classroom_id, self.classroom_id):
                continue
            remaining = parent_line.quantity - self.quantity
            if remaining > 0:
                parent_line.update(db, {"quantity": remaining})
            else:
                parent_line.delete(db)
            break  # l'arbre étant strict, une seule ligne de groupe du parent peut couvrir ce classroom_id
