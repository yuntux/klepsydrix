from datetime import date, datetime, time
from typing import Optional, Any
import enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint, CheckConstraint, Table, Enum
from sqlalchemy.orm import relationship, Session
from backend.app.models.base import Base, constrains, related_field

# Table de jointure Many-to-Many pour Group <-> ClassPart
group_class_parts = Table(
    "group_class_parts",
    Base.metadata,
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    Column("class_part_id", Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), primary_key=True)
)

class PartitionSpecialType(str, enum.Enum):
    """
    Type de partition auto-générée dont la structure (nombre et rôle de ses ClassPart) est fixée
    et gérée exclusivement par le système (voir find_or_create_partition) — jamais par l'IHM.
    """
    HALF_ALPHA = "HALF_ALPHA"
    HALF_GENDER = "HALF_GENDER"

class Partition(Base):
    __tablename__ = "partitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False, info={"label": "Code de la partition", "placeholder": "ex: PART1"})
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom de la partition", "placeholder": "ex: Groupes de Langue"})
    division_id: Mapped[int] = mapped_column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False, info={"readOnly": True})
    is_system_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Générée par le système"})
    special_type: Mapped[Optional[PartitionSpecialType]] = mapped_column(Enum(PartitionSpecialType, name="partition_special_type_enum"), nullable=True, default=None, info={"label": "Type spécial", "readOnly": True})

    # Relations de navigation
    division: Mapped[Optional["Division"]] = relationship("Division", back_populates="partitions")
    class_parts: Mapped[list["ClassPart"]] = relationship("ClassPart", back_populates="partition", passive_deletes="all", info={"label": "Parties de classe"})

    @property
    def display_name(self) -> str:
        division_name = self.division.name if self.division else str(self.division_id)
        return f"{division_name} - {self.name}"

    @classmethod
    def create(cls, db: Session, vals: dict):
        # _system_write : seul find_or_create_partition (ou un autre point d'entrée interne) doit
        # pouvoir passer ce sentinel — un payload API externe passe par clean_payload(), qui ne
        # transmet que les vraies colonnes/relations du modèle et filtre donc silencieusement toute
        # clé inconnue comme celle-ci (voir base.py, clean_payload).
        is_system_write = vals.pop('_system_write', False)
        if vals.get('special_type') is not None and not is_system_write:
            raise ValueError("Le champ special_type ne peut être attribué que par le système, jamais depuis l'IHM.")
        return super().create(db, vals)

    def update(self, db: Session, vals: dict):
        if 'division_id' in vals and vals['division_id'] != self.division_id:
            raise ValueError("Il est strictement interdit de modifier la division d'une partition après sa création.")

        is_system_write = vals.pop('_system_write', False)
        if 'special_type' in vals and vals['special_type'] != self.special_type and not is_system_write:
            raise ValueError("Le champ special_type ne peut être modifié que par le système, jamais depuis l'IHM.")

        if self.special_type is not None:
            if ('name' in vals and vals['name'] != self.name) or ('code' in vals and vals['code'] != self.code):
                raise ValueError("Une partition spéciale (special_type) ne peut pas être renommée : sa structure est gérée par le système.")
            if 'class_part_ids' in vals:
                raise ValueError("Impossible d'ajouter ou de retirer manuellement une partie d'une partition spéciale (special_type) : sa structure est gérée par le système.")

        return super().update(db, vals)

class ClassPart(Base):
    __tablename__ = "class_parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    partition_id: Mapped[int] = mapped_column(Integer, ForeignKey("partitions.id", ondelete="CASCADE"), nullable=False, info={"readOnly": True})
    division_id = related_field("partition", "division_id", info={"label": "Division", "readOnly": True})
    name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom de la partie", "placeholder": "ex: Espagnol"})
    subject_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True, info={"label": "Matière"})
    student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Nombre d'élèves", "min": 0, "max": 100})
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#CCCCCC", info={"label": "Couleur", "type": "color", "placeholder": "ex: #2ECC71"})
    is_system_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Générée par le système"})

    # Relations de navigation
    partition: Mapped[Optional["Partition"]] = relationship("Partition", back_populates="class_parts")
    subject: Mapped[Optional["Subject"]] = relationship("Subject")
    groups: Mapped[list["Group"]] = relationship("Group", secondary=group_class_parts, back_populates="class_parts", info={"label": "Groupes"})
    students: Mapped[list["Student"]] = relationship("Student", secondary="student_class_parts", back_populates="class_parts", passive_deletes="all", info={"label": "Élèves"})

    @property
    def display_name(self) -> str:
        if self.partition and self.partition.division:
            prefix = self.partition.division.display_name
        elif self.partition:
            prefix = str(self.partition.division_id)
        else:
            prefix = str(self.partition_id)
        return f"{prefix} - {self.name}"

    @classmethod
    def create(cls, db: Session, vals: dict):
        # _system_write : voir Partition.create, même convention (bypass réservé au code interne,
        # inatteignable depuis un payload API externe filtré par clean_payload).
        is_system_write = vals.pop('_system_write', False)
        partition_id = vals.get('partition_id')
        if partition_id and not is_system_write:
            partition = db.get(Partition, partition_id)
            if partition and partition.special_type is not None:
                raise ValueError("Impossible d'ajouter manuellement une partie à une partition spéciale (special_type) : sa structure est gérée par le système.")

        instance = super().create(db, vals)
        instance._auto_generate_links(db)
        return instance

    def update(self, db: Session, vals: dict):
        if 'partition_id' in vals and vals['partition_id'] != self.partition_id:
            raise ValueError("Il est strictement interdit de modifier l'attribut 'partition_id' d'une partie de classe après sa création.")
        return super().update(db, vals)

    def delete(self, db: Session):
        from backend.app.models.course import Course
        # Course.is_composed == False : un cours composé PARENT peut référencer cette partie de
        # classe en transit (cascade de ressources enfant -> parent, voir Course._cascade_
        # resources_to_parent) sans que ce soit un usage réel à protéger — seul un cours "réel"
        # (simple ou enfant, jamais un conteneur composé) compte, même exclusion que
        # _class_part_in_use ci-dessous, pour la même raison.
        direct_courses = db.query(Course).filter(
            Course.class_parts.any(ClassPart.id == self.id), Course.is_composed == False
        ).all()
        group_ids = [g.id for g in self.groups]
        via_group_courses = []
        if group_ids:
            via_group_courses = db.query(Course).filter(
                Course.groups.any(Group.id.in_(group_ids)), Course.is_composed == False
            ).all()
        linked_courses = {c.id: c for c in direct_courses + via_group_courses}
        if linked_courses:
            names = sorted(c.name or f"Cours #{c.id}" for c in linked_courses.values())
            raise ValueError(
                f"Impossible de supprimer cette partie de classe : elle est rattachée à "
                f"{len(linked_courses)} cours ({', '.join(names)})."
            )

        # Le retrait manuel d'une partie d'une partition spéciale est interdit, SAUF quand la
        # partition elle-même est en cours de suppression (composition : voir Partition, la
        # cascade FK ondelete=CASCADE via _cascade_delete_dependents pose déjà ce flag avant
        # d'appeler .delete() sur chacune de ses parties).
        if self.partition and self.partition.special_type is not None and not getattr(self.partition, '_via_crud_mixin_delete', False):
            raise ValueError("Impossible de retirer manuellement une partie d'une partition spéciale (special_type) : sa structure est gérée par le système.")

        return super().delete(db)

    def _auto_generate_links(self, db: Session):
        from sqlalchemy import select
        # 1. Obtenir la partition de cette partie de classe
        partition = db.get(Partition, self.partition_id)
        if not partition:
            return
        
        division_id = partition.division_id
        
        # 2. Trouver toutes les autres partitions de la même division
        other_partitions = db.execute(
            select(Partition).filter(
                Partition.division_id == division_id,
                Partition.id != self.partition_id
            )
        ).scalars().all()
        
        if not other_partitions:
            return
            
        other_partition_ids = [p.id for p in other_partitions]
        
        # 3. Trouver toutes les parties de classe associées à ces autres partitions
        other_class_parts = db.execute(
            select(ClassPart).filter(
                ClassPart.partition_id.in_(other_partition_ids)
            )
        ).scalars().all()
        
        for other_cp in other_class_parts:
            # Assurer l'ordre des IDs pour respecter la contrainte check_class_part_order
            cp_a_id = min(self.id, other_cp.id)
            cp_b_id = max(self.id, other_cp.id)
            
            # Créer le lien automatique
            ClassPartLink.create(db, {
                "class_part_a_id": cp_a_id,
                "class_part_b_id": cp_b_id,
                "is_system_generated": True
            })


class ClassPartLink(Base):
    __tablename__ = "class_part_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    class_part_a_id: Mapped[int] = mapped_column(Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), nullable=False, info={"label": "Partie de classe A"})
    class_part_b_id: Mapped[int] = mapped_column(Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), nullable=False, info={"label": "Partie de classe B"})
    is_system_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, info={"label": "Généré par le système"})

    # Relations de navigation
    class_part_a: Mapped[Optional["ClassPart"]] = relationship("ClassPart", foreign_keys=[class_part_a_id])
    class_part_b: Mapped[Optional["ClassPart"]] = relationship("ClassPart", foreign_keys=[class_part_b_id])

    __table_args__ = (
        UniqueConstraint("class_part_a_id", "class_part_b_id", name="uq_class_part_pair"),
        CheckConstraint("class_part_a_id < class_part_b_id", name="check_class_part_order"),
    )

    @constrains("class_part_a_id", "class_part_b_id")
    def _check_partition_overlap(self, db: Session):
        if self.class_part_a_id and self.class_part_b_id:
            cp_a = db.get(ClassPart, self.class_part_a_id)
            cp_b = db.get(ClassPart, self.class_part_b_id)
            if cp_a and cp_b and cp_a.partition_id == cp_b.partition_id:
                raise ValueError("Impossible de lier deux parties d'une même partition, elles sont disjointes par nature.")

    def update(self, db: Session, vals: dict):
        raise ValueError("Il est strictement interdit de modifier un lien entre parties de classe après sa création. Supprimez-le et recréez-le si nécessaire.")

    def delete(self, db: Session):
        from sqlalchemy import select
        from backend.app.models.student import student_class_parts
        # 1. Vérifier s'il y a des élèves communs entre les deux parties
        stmt_a = select(student_class_parts.c.student_id).filter(student_class_parts.c.class_part_id == self.class_part_a_id)
        stmt_b = select(student_class_parts.c.student_id).filter(student_class_parts.c.class_part_id == self.class_part_b_id)
        
        common_students = db.execute(
            select(student_class_parts.c.student_id)
            .filter(student_class_parts.c.student_id.in_(stmt_a))
            .filter(student_class_parts.c.student_id.in_(stmt_b))
        ).scalars().all()
        
        if common_students:
            raise ValueError("Impossible de supprimer ce lien d'incompatibilité car des élèves appartiennent simultanément aux deux parties de classe.")
            
        return super().delete(db)

class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, info={"label": "Nom du groupe", "placeholder": "ex: Groupe 1"})
    student_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Nombre d'élèves", "min": 0, "max": 100})
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#CCCCCC", info={"label": "Couleur", "type": "color", "placeholder": "ex: #F59E0B"})
    is_variable_size: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Taille variable"})
    is_system_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Généré par le système"})

    # Relations de navigation
    class_parts: Mapped[list["ClassPart"]] = relationship("ClassPart", secondary=group_class_parts, back_populates="groups", info={"label": "Parties de classe"})
    courses: Mapped[list["Course"]] = relationship("Course", secondary="course_groups", back_populates="groups", info={"label": "Cours"})

    def get_linked_groups(self, db: Session) -> list["Group"]:
        from sqlalchemy import select, or_
        cp_ids = [cp.id for cp in self.class_parts]
        if not cp_ids:
            return []

        # Trouver tous les liens d'incompatibilité associés à ces parties de classe
        links = db.execute(
            select(ClassPartLink).filter(
                or_(
                    ClassPartLink.class_part_a_id.in_(cp_ids),
                    ClassPartLink.class_part_b_id.in_(cp_ids)
                )
            )
        ).scalars().all()

        linked_cp_ids = set()
        for l in links:
            if l.class_part_a_id in cp_ids:
                linked_cp_ids.add(l.class_part_b_id)
            if l.class_part_b_id in cp_ids:
                linked_cp_ids.add(l.class_part_a_id)

        if not linked_cp_ids:
            return []

        # Récupérer les autres groupes contenant ces parties de classe liées
        stmt_groups = select(Group).join(group_class_parts).filter(
            group_class_parts.c.class_part_id.in_(linked_cp_ids),
            Group.id != self.id
        ).distinct()

        return list(db.execute(stmt_groups).scalars().all())


# ---------------------------------------------------------------------- #
#   Génération de noms et résolution de Partition/Group dynamiques       #
#   (déplacé depuis CompositionModes — utile en dehors du seul workflow  #
#   de décomposition de cours, voir composition_mode.py)                 #
# ---------------------------------------------------------------------- #

def next_number_suffix(db: Session, existing_count: int, setting_key: str) -> str:
    from backend.app.models.system_setting import SystemSetting, NUMBER_FORMAT_ALPHABETIC
    number_format = SystemSetting.get_system_setting_value(db, setting_key) or "numerique"
    n = existing_count + 1
    if number_format != NUMBER_FORMAT_ALPHABETIC:
        return str(n)
    # 1 -> A, 2 -> B, ..., 26 -> Z, 27 -> AA, ... (comme la numérotation des colonnes d'un tableur)
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def compute_group_name(db: Session, division_id, subject_id, class_part_ids: list) -> str:
    """
    Nom d'un groupe auto-généré, piloté par le paramétrage système GROUP_NAME_* : concaténation
    de la première lettre du code classe (si activé et déterminable — un groupe peut mêler des
    parties de plusieurs divisions, auquel cas division_id vaut None et ce segment est omis), du
    séparateur, du code matière (si activé), puis d'un numéro/lettre rendant le nom unique parmi
    les groupes déjà en base dont le nom commence par ce même préfixe.
    """
    from backend.app.models.system_setting import SystemSetting
    from backend.app.models.division import Division
    from backend.app.models.subject import Subject

    has_div_code = SystemSetting.get_system_setting_value(db, "GROUP_NAME_HAS_DIV_CODE") == "true"
    has_subject_code = SystemSetting.get_system_setting_value(db, "GROUP_NAME_HAS_SUBJECT_CODE") == "true"
    separator = SystemSetting.get_system_setting_value(db, "GROUP_NAME_SEPARATOR") or "G"

    prefix = ""
    if has_div_code and division_id:
        division = db.get(Division, division_id)
        if division and division.code:
            prefix += division.code[0]
    prefix += separator
    if has_subject_code and subject_id:
        subject = db.get(Subject, subject_id)
        if subject:
            prefix += subject.code

    existing_count = db.query(Group).filter(Group.name.like(f"{prefix}%")).count()
    return prefix + next_number_suffix(db, existing_count, "GROUP_NAME_NUMBER_FORMAT")


def compute_class_part_name(db: Session, division_id, subject_id) -> str:
    """Miroir de compute_group_name, piloté par le paramétrage système DIVISION_PART_NAME_*."""
    from backend.app.models.system_setting import SystemSetting
    from backend.app.models.division import Division
    from backend.app.models.subject import Subject

    has_div_code = SystemSetting.get_system_setting_value(db, "DIVISION_PART_NAME_HAS_DIV_CODE") == "true"
    has_subject_code = SystemSetting.get_system_setting_value(db, "DIVISION_PART_NAME_HAS_SUBJECT_CODE") == "true"
    separator = SystemSetting.get_system_setting_value(db, "DIVISION_PART_NAME_SEPARATOR") or "P"

    prefix = ""
    if has_div_code and division_id:
        division = db.get(Division, division_id)
        if division:
            prefix += division.code[0]
    if has_subject_code and subject_id:
        subject = db.get(Subject, subject_id)
        if subject:
            prefix += subject.code
    prefix += separator

    existing_count = db.query(ClassPart).filter(ClassPart.name.like(f"{prefix}%")).count()
    return prefix + next_number_suffix(db, existing_count, "DIVISION_PART_NAME_NUMBER_FORMAT")


def find_or_create_partition(
    db: Session,
    division_id: int,
    name: str,
    subject_ids: list = None,
    special_type: "PartitionSpecialType" = None,
    part_count: int = None,
) -> Partition:
    """
    Trouve ou crée, pour une Division donnée, la Partition résultant d'exactement UNE des trois
    stratégies mutuellement exclusives ci-dessous :

    - `subject_ids` : réutilise la première Partition de cette Division dont les ClassPart
      couvrent AU MOINS ces matières (des matières supplémentaires sur la partition existante
      sont tolérées) ; sinon en crée une nouvelle (code/name=`name`), avec une ClassPart par
      matière de la liste (is_system_generated=True).
    - `special_type` : réutilise la Partition de cette Division déjà typée avec ce special_type ;
      sinon en crée une nouvelle avec deux ClassPart fixes (is_system_generated=True) : 'Garçons'
      et 'Filles' pour HALF_GENDER (label 'Fille/Garçon'), 'P1' et 'P2' pour HALF_ALPHA (label
      'Dédoublement'). `name` est ignoré dans ce cas, le nom est déterminé par `special_type`.
    - `part_count` : réutilise la Partition de cette Division qui possède exactement ce nombre de
      ClassPart ; sinon en crée une nouvelle (code/name=`name`) avec N ClassPart
      (is_system_generated=True), N = `part_count`.

    Une Partition issue de `special_type` ou `part_count` porte elle-même is_system_generated=True
    (générée entièrement par le système) ; une Partition issue de `subject_ids` aussi, seul son
    label reste au choix de l'appelant via `name`.
    """
    from backend.app.models.division import Division

    strategies_set = [subject_ids is not None, special_type is not None, part_count is not None]
    if sum(strategies_set) != 1:
        raise ValueError("find_or_create_partition attend exactement un des trois paramètres subject_ids, special_type ou part_count.")

    if subject_ids is not None:
        wanted_subject_ids = set(subject_ids)
        for partition in db.query(Partition).filter(Partition.division_id == division_id).all():
            existing_subject_ids = {cp.subject_id for cp in partition.class_parts if cp.subject_id is not None}
            if wanted_subject_ids.issubset(existing_subject_ids):
                return partition

        partition = Partition.create(db, {"code": name, "name": name, "division_id": division_id, "is_system_generated": True})
        for subject_id in subject_ids:
            ClassPart.create(db, {
                "partition_id": partition.id,
                "name": compute_class_part_name(db, division_id, subject_id),
                "subject_id": subject_id,
                "is_system_generated": True,
                "_system_write": True,
            })
        return partition

    if special_type is not None:
        existing = db.query(Partition).filter(Partition.division_id == division_id, Partition.special_type == special_type).first()
        if existing:
            return existing

        if special_type == PartitionSpecialType.HALF_GENDER:
            label, part_names = "Fille/Garçon", ["Garçons", "Filles"]
        else:
            label, part_names = "Dédoublement", ["P1", "P2"]

        partition = Partition.create(db, {
            "code": label, "name": label, "division_id": division_id,
            "is_system_generated": True, "special_type": special_type, "_system_write": True,
        })
        for part_name in part_names:
            ClassPart.create(db, {
                "partition_id": partition.id, "name": part_name,
                "is_system_generated": True, "_system_write": True,
            })
        return partition

    for partition in db.query(Partition).filter(Partition.division_id == division_id).all():
        if len(partition.class_parts) == part_count:
            return partition

    partition = Partition.create(db, {"code": name, "name": name, "division_id": division_id, "is_system_generated": True})
    for _ in range(part_count):
        ClassPart.create(db, {
            "partition_id": partition.id,
            "name": compute_class_part_name(db, division_id, None),
            "is_system_generated": True,
            "_system_write": True,
        })
    return partition


def find_or_create_group(db: Session, class_part_ids: list, subject_id) -> Group:
    """
    Trouve ou crée le Group composé EXACTEMENT de ces ClassPart (même ensemble, peu importe
    l'ordre passé en paramètre) — jamais un Group qui en contiendrait un sous-ensemble ou un
    sur-ensemble.
    """
    target_ids = set(class_part_ids)
    for group in db.query(Group).all():
        if {cp.id for cp in group.class_parts} == target_ids:
            return group

    class_parts = [db.get(ClassPart, cid) for cid in target_ids]
    division_ids = {cp.division_id for cp in class_parts if cp}
    common_division_id = next(iter(division_ids)) if len(division_ids) == 1 else None
    return Group.create(db, {
        "name": compute_group_name(db, common_division_id, subject_id, list(target_ids)),
        "class_part_ids": list(target_ids),
        "is_system_generated": True,
    })


# ---------------------------------------------------------------------- #
#   Nettoyage des ressources auto-générées devenues inutilisées          #
#   (créées par CompositionModes lors de la composition de cours, voir   #
#   composition_mode.py — colocalisé ici avec ClassPart/Group/Partition  #
#   puisque ce nettoyage ne dépend que de leur propre état, pas des      #
#   modes de composition eux-mêmes)                                      #
# ---------------------------------------------------------------------- #

def _class_part_in_use(db: Session, class_part: "ClassPart") -> bool:
    """Utilisée par un cours "réel" (non composé) : directement, ou via un groupe."""
    from backend.app.models.course import Course
    direct = db.query(Course).filter(
        Course.class_parts.any(ClassPart.id == class_part.id), Course.is_composed == False
    ).first()
    if direct:
        return True
    group_ids = [g.id for g in class_part.groups]
    if not group_ids:
        return False
    via_group = db.query(Course).filter(
        Course.groups.any(Group.id.in_(group_ids)), Course.is_composed == False
    ).first()
    return via_group is not None


def cleanup_orphaned_class_part(db: Session, class_part_id: int):
    """
    Supprime une partie de classe auto-générée dès lors qu'elle n'a plus d'élève et n'est
    utilisée par aucun cours (directement ou via un groupe) — et propage le nettoyage au
    groupe/à la partition qui n'auraient alors plus rien à contenir.
    """
    class_part = db.get(ClassPart, class_part_id)
    if not class_part or not class_part.is_system_generated:
        return
    if class_part.students:
        return
    if _class_part_in_use(db, class_part):
        return
    if class_part.partition and class_part.partition.special_type is not None:
        # La structure d'une partition spéciale (nombre et rôle de ses parties) est fixe : ce
        # nettoyage opportuniste ne doit pas la faire dériver, même si une de ses parties n'est
        # momentanément plus utilisée (voir ClassPart.delete, même invariant).
        return

    partition_id = class_part.partition_id
    affected_group_ids = [g.id for g in class_part.groups]
    class_part.delete(db)
    # Un cours (typiquement le parent composé) peut encore référencer cette partie de classe dans
    # sa collection ORM en mémoire (suppression faite "de l'autre côté", même piège que documenté
    # sur Course._sync_parent_week_type) : sans ça, un session.add() ultérieur sur ce cours
    # tenterait de re-rattacher un objet supprimé.
    db.expire_all()

    for group_id in affected_group_ids:
        cleanup_orphaned_group(db, group_id)
    cleanup_orphaned_partition(db, partition_id)


def cleanup_orphaned_group(db: Session, group_id: int):
    """Supprime un groupe auto-généré dès lors qu'il n'a plus aucune partie de classe liée."""
    group = db.get(Group, group_id)
    if not group or not group.is_system_generated:
        return
    if not group.class_parts:
        group.delete(db)
        db.expire_all()


def cleanup_orphaned_partition(db: Session, partition_id: int):
    """Supprime une partition auto-générée dès lors qu'elle n'a plus aucune partie de classe liée."""
    partition = db.get(Partition, partition_id)
    if not partition or not partition.is_system_generated:
        return
    if not partition.class_parts:
        partition.delete(db)
        db.expire_all()


def cleanup_orphaned_resources(db: Session, class_part_ids: list = None, group_ids: list = None):
    """
    Point d'entrée du nettoyage : à appeler sur les parties de classe/groupes qu'un cours vient de
    cesser de référencer (mise à jour, suppression, ou abandon d'un brouillon de composition — voir
    Course.update/delete et Course.rpc_cancel_composition). Sans effet sur une ressource créée
    manuellement (is_system_generated=False).

    Un cours composé référence en général un groupe, pas ses parties de classe directement
    (CompositionModes._resolve_dynamic_groups les retire de la ligne au profit du groupe) : sans
    élargir aux parties de classe membres des groupes ci-dessous, elles resteraient injoignables
    depuis ce point d'entrée alors qu'elles peuvent, elles aussi, être devenues inutilisées.
    """
    all_class_part_ids = set(class_part_ids or [])
    for group_id in (group_ids or []):
        group = db.get(Group, group_id)
        if group:
            all_class_part_ids.update(cp.id for cp in group.class_parts)

    for class_part_id in all_class_part_ids:
        cleanup_orphaned_class_part(db, class_part_id)
    for group_id in (group_ids or []):
        cleanup_orphaned_group(db, group_id)

