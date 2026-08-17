from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
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
    # jamais en réattribuant classroom_id sur la ligne existante. La contrainte réelle est portée
    # par _validate_classroom_id_immutable, pas par ce schéma — la présentation (lecture seule dans
    # la popin d'édition une fois la ligne créée) est une politique d'UI déclarée explicitement où
    # le widget est utilisé (voir CoursePopin.vue::classroomRequirementWidgetParams), pas ici.
    classroom_id: Mapped[int] = mapped_column(Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True, info={"label": "Salle ou groupe de salles"})
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, info={"label": "Nombre de salles", "min": 1, "max": 20})

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

    # Verrou local pour _validate_classroom_id_immutable — voir cette méthode pour le pourquoi
    # (_via_crud_mixin_create seul ne suffit pas : il reste True sur l'objet Python après la
    # création, tant que ce même objet vit dans la session — la carte d'identité SQLAlchemy peut
    # le rendre à un appelant plus tard dans la même session).
    _classroom_id_write_consumed: bool = False

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

    @constrains('classroom_id')
    def _validate_classroom_id_immutable(self, db: Session):
        """
        `_via_crud_mixin_create` n'est posé (à True) que par CRUDMixin.create() — jamais par
        update() — et c'est un attribut Python pur, jamais rechargé depuis la base : une ligne
        obtenue via update() dans une session DIFFÉRENTE de celle qui l'a créée ne l'a donc jamais
        (le cas courant). get_history() a été envisagé pour cette vérification mais écarté :
        testé empiriquement, il ne remonte l'ancienne valeur de façon fiable qu'à travers une
        frontière de session — au sein de la MÊME session, sur le même objet Python, il ne la
        retrouve pas.

        ⚠️ `_via_crud_mixin_create` seul ne suffit pourtant pas : il reste à True sur l'instance
        pour le reste de sa vie en mémoire une fois posé — si cette MÊME instance Python est
        récupérée une seconde fois plus tard dans la MÊME session (carte d'identité SQLAlchemy,
        ex: `_apply_owned_collection_commands` qui requête puis appelle `.update()`), il vaudrait
        encore True et laisserait passer une mutation illégitime. `_classroom_id_write_consumed`
        ferme ce trou : une fois la première (et seule légitime) affectation consommée, tout appel
        suivant sur ce même objet est rejeté, quel que soit l'état de `_via_crud_mixin_create`.
        """
        if getattr(self, '_via_crud_mixin_create', False) and not self._classroom_id_write_consumed:
            self._classroom_id_write_consumed = True
            return
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
