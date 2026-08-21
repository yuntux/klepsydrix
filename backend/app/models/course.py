from datetime import date, datetime, time
from typing import Optional, Any
import enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Column, Integer, Float, String, ForeignKey, Boolean, Text, select, Enum, Table, event, JSON, false as sa_false
from sqlalchemy.orm import relationship, Session
from sqlalchemy.ext.hybrid import hybrid_property
from backend.app.models.base import Base, exposed, constrains, onchange, requires_access


class CourseWeekType(str, enum.Enum):
    """
    Alternance de semaine d'un Course — délibérément DISTINCTE de preference.WeekType (A/B/W)
    plutôt qu'un simple ajout de Q à cette dernière : Q ("quinzaine à déterminer", voir
    attribution_week_type_auto.md) n'a de sens que pour un Course en attente de résolution
    A/B, jamais pour une préférence de ressource (ResourcePreference.week_type). Deux enums
    Python séparés, adossés à deux enums SQL déjà distincts (course_week_type_enum vs
    week_type_enum), rendent Q structurellement inatteignable côté préférences — y compris via
    le moteur de formulaire générique, qui construit ses options à partir des membres de l'enum.
    """
    A = "A"
    B = "B"
    W = "W"
    Q = "Q"


class CourseStatus(str, enum.Enum):
    """Statut de placement d'un Course sur la grille — recalculé par recompute_status(), jamais saisi à la main (voir status.info["readOnly"])."""
    UNPLACED = "UNPLACED"
    PLACED = "PLACED"


class CourseDecompositionStatus(str, enum.Enum):
    """Statut de ventilation des ressources d'un Course composé vers ses enfants — recalculé par recompute_status(), jamais saisi à la main."""
    UNVENTILATED = "UNVENTILATED"
    PARTIALLY_VENTILATED = "PARTIALLY_VENTILATED"
    FULLY_VENTILATED = "FULLY_VENTILATED"

course_teachers = Table(
    "course_teachers",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("teacher_id", Integer, ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

## course_classrooms (M2M, PK composite) supprimée — remplacée par CourseClassroomRequirement
## (course_classroom_requirement.py), une vraie entité avec quantity, cf. plan salles §1.4.

course_non_teaching_staffs = Table(
    "course_non_teaching_staffs",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("non_teaching_staff_id", Integer, ForeignKey("non_teaching_staffs.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

course_materials = Table(
    "course_materials",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("material_id", Integer, ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

course_divisions = Table(
    "course_divisions",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("division_id", Integer, ForeignKey("divisions.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

course_class_parts = Table(
    "course_class_parts",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("class_part_id", Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

course_groups = Table(
    "course_groups",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

course_periods = Table(
    "course_periods",
    Base.metadata,
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("period_id", Integer, ForeignKey("periods.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True
)

class Course(Base):
    __tablename__ = "courses"
    # "component" absent : GenericForm.vue route par défaut vers GenericWizard.vue (mécanisme
    # générique piloté par "steps", voir architecture.md) plutôt qu'un composant bespoke —
    # componentsMap reste un échappatoire pour un futur wizard qui ne rentrerait pas dans ce moule.
    __actions__ = [
        {
            # Impression PDF (voir architecture.md §22) — type "report", même patron déclaratif que
            # "wizard"/"bulk_api" : le bouton apparaît tout seul, aucune vue à modifier, comme le
            # binding_type="report" d'Odoo. Une seule action, quelle que soit la vue (liste ou
            # formulaire) : c'est le composant appelant (ReportPrintMenu, posé par GenericList.vue
            # ou GenericForm.vue) qui résout les ids ciblés selon son propre contexte — sélection
            # courante côté liste, enregistrement(s) affiché(s) côté formulaire.
            "id": "print_course_list",
            "label": "Imprimer les cours (PDF)",
            "type": "report",
            "icon": "fa-print",
            "report": "course_list",
        },
        {
            "id": "compose_course",
            "label": "Décomposer le cours",
            "type": "wizard",
            "icon": "fa-sitemap",
            "condition": "record.status !== 'PLACED'",
            "cancelRpc": "rpc_cancel_composition",
            "steps": [
                {
                    "id": "mapping",
                    "title": "1. Mapping et mode de répartition",
                    "submitLabel": "Générer l'aperçu",
                    "rpc": "rpc_preview_composition",
                    "rpcParams": {"mode": "composition_mode", "mapping": "composition_mapping"},
                    "fields": [
                        {
                            "key": "composition_mapping", "label": "Répartition (mapping)", "type": "text",
                            "widget": "list_preview", "fullWidth": True,
                            "widgetParams": {
                                "columns": [
                                    {"key": "teacher_ids", "label": "Professeurs", "width": 200, "type": "multiselect", "resource": "teachers"},
                                    {
                                        "key": "subject_id", "label": "Matière", "width": 160, "type": "select", "resource": "subjects",
                                        # Pré-remplissage depuis la matière préférée du 1er professeur choisi sur CETTE
                                        # ligne — seulement si la matière n'a pas déjà été choisie (jamais d'écrasement),
                                        # voir ListPreviewField.vue::applyPrefills. Miroir de Course.composition_mapping/
                                        # CompositionModes.default_mapping, qui fait la même chose une fois à l'ouverture.
                                        "prefillFromField": {"sourceField": "teacher_ids", "sourceItemField": "preferred_subject_id", "onlyIfEmpty": True},
                                    },
                                    {
                                        "key": "group_ids", "label": "Groupes", "width": 160, "type": "multiselect", "resource": "groups",
                                        "readOnlyExpr": "(model.class_part_ids && model.class_part_ids.length > 0) || (model.division_targets && model.division_targets.length > 0)",
                                    },
                                    {
                                        "key": "class_part_ids", "label": "Parties de classe", "width": 160, "type": "multiselect", "resource": "class_parts",
                                        "readOnlyExpr": "(model.group_ids && model.group_ids.length > 0) || (model.division_targets && model.division_targets.length > 0)",
                                    },
                                    {
                                        "key": "division_targets", "label": "Classes", "width": 260, "type": "multiselect", "resource": "divisions",
                                        "readOnlyExpr": "(model.group_ids && model.group_ids.length > 0) || (model.class_part_ids && model.class_part_ids.length > 0)",
                                        # Sous-mode par classe ciblée (voir SearchableMultiSelect.vue::itemModeOptions) :
                                        # modelValue de cette colonne devient [{id, mode}] au lieu de [id]. "CLASS_PART"
                                        # reproduit EXACTEMENT le comportement historique (une ClassPart par matière,
                                        # partagée entre lignes de matières différentes ciblant la même classe) — ce
                                        # n'est PAS le champ class_part_ids ci-dessus (choix manuel d'une ClassPart déjà
                                        # connue). Voir CompositionModes.DIVISION_TARGET_MODES (composition_mode.py).
                                        "itemModeOptions": [
                                            {"value": "CLASS_PART", "label": "Partie de classe"},
                                            {"value": "WHOLE_CLASS", "label": "Classe entière"},
                                            {"value": "HALF_GENDER", "label": "Dédoublement F-G"},
                                            {"value": "HALF_ALPHA", "label": "Dédoublement Alpha"},
                                        ],
                                    },
                                    {"key": "classroom_ids", "label": "Salles", "width": 160, "type": "multiselect", "resource": "classrooms"},
                                ],
                                "listConfig": {"editableInline": True, "disableAdd": False, "disableDelete": False, "allowMultiSelect": False},
                                # Règles de cohérence entre lignes (voir ListPreviewField.vue::applyCrossRowRules) :
                                # pour un même id de la colonne division_targets, un seul mode à la fois à travers
                                # tout le tableau (WHOLE_CLASS/CLASS_PART/dédoublement ne se mélangent jamais pour
                                # une même classe — CLASS_PART peut en revanche apparaître sur autant de lignes que
                                # voulu) ; les modes listés dans crossRowMaxRowsByMode sont en plus plafonnés en
                                # nombre de lignes (dédoublement : 2 maximum). Miroir exact du garde-fou serveur
                                # CompositionModes._validate_division_target_coherence, en correction live plutôt
                                # qu'en rejet a posteriori.
                                "crossRowExclusiveColumn": "division_targets",
                                "crossRowMaxRowsByMode": {"HALF_GENDER": 2, "HALF_ALPHA": 2},
                            },
                        },
                        {
                            "key": "composition_mode", "label": "Mode de répartition temporelle", "type": "select",
                            "resource": "composition_mode_options", "fullWidth": True,
                            "dynamicOptionsFilter": {
                                "filterQueryParam": "mapping", "sourceField": "composition_mapping",
                                "recordIdQueryParam": "course_id",
                            },
                        },
                    ]
                },
                {
                    "id": "preview",
                    "title": "2. Aperçu des cours enfants (brouillon)",
                    "submitLabel": "Valider",
                    "rpc": "rpc_save_composition",
                    # mapping/mode : toujours le brouillon ORIGINAL saisi à l'étape 1
                    # (composition_mapping/composition_mode restent dans draft, accumulé par
                    # GenericWizard.vue au fil des étapes) — jamais muté par le passage dans
                    # rpc_preview_composition, qui mute sa propre copie Python côté serveur sans
                    # jamais renvoyer cette mutation au frontend. Sert à persister
                    # composition_config (voir rpc_save_composition) pour repréciser le cours
                    # plus tard en repartant de ce qui a réellement été choisi, pas d'une version
                    # déjà résolue (division_targets -> class_part_ids).
                    "rpcParams": {"children_vals": "children_vals", "mapping": "composition_mapping", "mode": "composition_mode"},
                    "isLast": True,
                    "fields": [
                        {
                            "key": "children_vals", "label": "Cours enfants", "type": "text",
                            "widget": "list_preview", "fullWidth": True,
                            "widgetParams": {
                                "columns": [
                                    {"key": "subject_id", "label": "Matière", "width": 140, "type": "select", "resource": "subjects", "readOnly": True},
                                    {
                                        "key": "week_type", "label": "Semaine", "width": 140, "type": "select", "readOnly": False,
                                        "options": [
                                            {"value": "W", "label": "Hebdomadaire"},
                                            {"value": "Q", "label": "Quinzaine à déterminer"},
                                            {"value": "A", "label": "Semaine A"},
                                            {"value": "B", "label": "Semaine B"},
                                        ],
                                    },
                                    {"key": "duration_minutes", "label": "Durée (min)", "width": 110, "type": "number"},
                                    {"key": "parent_timeslot_offset", "label": "Décalage", "width": 100, "type": "number"},
                                    {"key": "period_ids", "label": "Périodes", "width": 160, "type": "multiselect", "resource": "periods"},
                                    {"key": "teacher_ids", "label": "Professeurs", "width": 180, "type": "multiselect", "resource": "teachers", "readOnly": True},
                                    {"key": "is_co_teaching", "label": "Co-enseignement", "width": 120, "type": "boolean", "readOnly": True},
                                    {"key": "division_ids", "label": "Classes", "width": 140, "type": "multiselect", "resource": "divisions", "readOnly": True},
                                    {"key": "class_part_ids", "label": "Parties de classe", "width": 160, "type": "multiselect", "resource": "class_parts", "readOnly": True},
                                    {"key": "group_ids", "label": "Groupes", "width": 140, "type": "multiselect", "resource": "groups", "readOnly": True},
                                    {"key": "material_ids", "label": "Matériel", "width": 140, "type": "multiselect", "resource": "materials", "readOnly": True},
                                    {"key": "non_teaching_staff_ids", "label": "Personnel non enseignant", "width": 180, "type": "multiselect", "resource": "non_teaching_staffs", "readOnly": True},
                                    {"key": "pending_summary", "label": "Ressources à créer", "width": 220, "type": "text", "readOnly": True},
                                ],
                                "listConfig": {"editableInline": True, "disableAdd": True, "disableDelete": True, "allowMultiSelect": False},
                            },
                        },
                    ]
                }
            ]
        }
    ]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, info={"label": "Cours parent"})
    
    # Pour les cours simples, un subject_id est requis. Pour les cours complexes (parents), il peut être NULL.
    subject_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=True, info={"label": "Matière"})
    
    # Placements et attributs directs
    timeslot_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("timeslots.id", ondelete="SET NULL"), nullable=True, info={"label": "Créneau de placement"})
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Épinglé"})
    
    # Offset pour les enfants de cours complexes (nombre de créneaux de décalage par rapport au
    # parent) — hidden : détail interne du wizard de décomposition (rpc_save_composition), jamais
    # pertinent à afficher ou éditer directement en liste/formulaire.
    parent_timeslot_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0, info={"label": "Décalage par rapport au parent", "hidden": True})
    
    week_type: Mapped[Any] = mapped_column(Enum(CourseWeekType, name="course_week_type_enum"), nullable=False, default=CourseWeekType.W, info={
        "label": "Semaine", "placeholder": "ex: A, B, W, Q", "type": "select",
        "options": [
            {"value": "W", "label": "Hebdomadaire"},
            {"value": "Q", "label": "Quinzaine à déterminer"},
            {"value": "A", "label": "Semaine A"},
            {"value": "B", "label": "Semaine B"},
        ],
    })
    period_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("period_types.id", ondelete="SET NULL"), nullable=True, info={"label": "Type de période"})
    is_co_teaching: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Co-enseignement"})
    
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60, info={"label": "Durée", "type": "duration"})
    # Copié depuis Service.weighting_coefficient à la génération (voir wizard_course_generation.py)
    # — jamais une FK vivante vers Service (Course n'en a et ne doit pas en avoir, cohérent avec le
    # reste de la génération, qui copie plutôt que référence). Reste à 1.0 pour un cours créé
    # manuellement, sans Service d'origine. Sert au calcul de weighted_duration_minutes ci-dessous,
    # consommé par Teacher.hsa_duration_minutes (voir teacher-assignment-proposal.md §6).
    weighting_coefficient: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, info={"label": "Pondération", "min": 0.0, "max": 5.0, "step": "0.05"})
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, info={"label": "Nom / Libellé", "placeholder": "ex: Cours de maths avancé"})
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True, info={"label": "Mémo / Note interne"})
    is_composed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Cours composé"})
    lock_structure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, info={"label": "Structure verrouillée"})
    forbid_break_overlap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Ne pas chevaucher les récréations"})
    status: Mapped[Any] = mapped_column(Enum(CourseStatus, name="course_status_enum"), nullable=False, default=CourseStatus.UNPLACED, server_default="UNPLACED", info={
        "label": "Statut de placement", "type": "select", "readOnly": True,
        "options": [
            {"value": "UNPLACED", "label": "Non placé"},
            {"value": "PLACED", "label": "Placé"},
        ],
    })
    decomposition_status: Mapped[Optional[Any]] = mapped_column(Enum(CourseDecompositionStatus, name="course_decomposition_status_enum"), nullable=True, default=CourseDecompositionStatus.UNVENTILATED, server_default="UNVENTILATED", info={
        "label": "Statut de décomposition", "type": "select", "readOnly": True,
        "options": [
            {"value": "UNVENTILATED", "label": "Non ventilé"},
            {"value": "PARTIALLY_VENTILATED", "label": "Partiellement ventilé"},
            {"value": "FULLY_VENTILATED", "label": "Totalement ventilé"},
        ],
    })
    # Recalculé dans recompute_status() en même temps que decomposition_status (voir
    # _missing_resource_ids_by_type) : {champ_ressource: [ids présents sur ce cours composé mais
    # absents de TOUS ses enfants]}, uniquement les types en défaut. None si non composé, sans
    # enfant, ou FULLY_VENTILATED. hidden: purement un détail d'implémentation du wizard de
    # décomposition (surlignage des ressources sous-ventilées côté CoursePopin/GenericWizard),
    # jamais un champ à afficher tel quel (JSON brut illisible en cellule/formulaire).
    underventilated_resource_ids: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, info={"label": "Ressources insuffisamment ventilées", "type": "json", "readOnly": True, "hidden": True})
    # {"mapping": [...], "mode": int} — dernière configuration du wizard "Décomposer le cours"
    # effectivement validée (voir rpc_save_composition, composition_mapping/composition_mode
    # ci-dessous). None tant que le cours n'a jamais été décomposé via ce wizard. Même patron que
    # underventilated_resource_ids (JSON brut, aucune validation de schéma au niveau colonne — la
    # forme est garantie par le seul point d'écriture, rpc_save_composition). hidden : même raison
    # que underventilated_resource_ids ci-dessus.
    composition_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, info={"label": "Configuration de décomposition", "type": "json", "readOnly": True, "hidden": True})

    mission_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_pacte_missions.id", ondelete="SET NULL"), nullable=True, info={"label": "Mission"})
    # Modalité de cours (CODE_MOD_COURS du flux STS). Défaut 1 = « CG », cours général : la
    # modalité est seedée en PREMIER dans init_db.py précisément pour que cet identifiant soit
    # stable. « CG » est aussi la valeur de repli d'usage : un cours de modalité inconnue se
    # remonte en cours général. ondelete=RESTRICT : une modalité utilisée par un cours ne doit
    # pas pouvoir disparaître, la remontée STS en dépend.
    modality_id: Mapped[int] = mapped_column(Integer, ForeignKey("modalities.id", ondelete="RESTRICT"), nullable=False, default=1, server_default="1", info={"label": "Modalité"})
    # Alternance STS (calendrier nommé de semaines) — champ CALCULÉ ET STOCKÉ (§15.F), jamais
    # saisi : il découle du couple (week_type, périodes) du cours, voir _sync_alternation.
    # Le solveur l'ignore totalement : il raisonne sur week_type, jamais sur des semaines
    # calendaires. ondelete=SET NULL : perdre l'alternance ne doit jamais emporter le cours.
    alternation_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("alternations.id", ondelete="SET NULL"), nullable=True, info={"label": "Alternance", "readOnly": True})
    # Exclusion de la remontée STS portée par le cours lui-même — le niveau le plus fin des trois.
    # Par défaut tout cours est remonté : c'est à l'utilisateur de désigner ceux qui ne doivent pas
    # l'être (réunions, faux cours créés pour l'affichage...). Recopié du Service d'origine à la
    # génération, puis modifiable cours par cours.
    is_excluded_from_sts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Exclure de la remontée STS"})
    election_method_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_election_methods.id", ondelete="SET NULL"), nullable=True, info={"label": "Mode d'élection"})
    family_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("families.id", ondelete="SET NULL"), nullable=True, info={"label": "Famille"})
    school_id: Mapped[int] = mapped_column(Integer, ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, info={"label": "Établissement"})

    # Relations de navigation hiérarchique
    parent: Mapped[Optional["Course"]] = relationship("Course", back_populates="children", remote_side=[id])
    # Pas de cascade="delete-orphan" ici : la suppression en cascade des Course enfants est
    # désormais pilotée par CRUDMixin._cascade_delete_dependents() à partir du ondelete=CASCADE
    # de Course.parent_id (voir base.py) — déclarer aussi une cascade ORM ferait doublon.
    children: Mapped[list["Course"]] = relationship("Course", back_populates="parent", info={"label": "Cours enfants"})

    # Relations de navigation Mto1
    subject_relation: Mapped[Optional["Subject"]] = relationship("Subject", back_populates="courses")
    timeslot: Mapped[Optional["Timeslot"]] = relationship("Timeslot")
    period_type: Mapped[Optional["PeriodType"]] = relationship("PeriodType")
    mission: Mapped[Optional["RefPacteMission"]] = relationship("RefPacteMission", back_populates="courses")
    modality: Mapped[Optional["Modality"]] = relationship("Modality", back_populates="courses")
    alternation: Mapped[Optional["Alternation"]] = relationship("Alternation", back_populates="courses")
    teacher_weightings: Mapped[list["CourseTeacherWeighting"]] = relationship(
        "CourseTeacherWeighting", back_populates="course", passive_deletes="all",
        info={"label": "Pondérations par intervenant", "help": "À ne renseigner que pour les intervenants dont la pondération diffère de celle du cours."},
    )
    election_method: Mapped[Optional["RefElectionMethod"]] = relationship("RefElectionMethod")
    family: Mapped[Optional["Family"]] = relationship("Family", back_populates="courses")
    school: Mapped[Optional["School"]] = relationship("School")
    
    # Ressources N..N pures
    teachers: Mapped[list["Teacher"]] = relationship("Teacher", secondary=course_teachers, back_populates="courses", info={"label": "Enseignants"})
    non_teaching_staffs: Mapped[list["NonTeachingStaff"]] = relationship("NonTeachingStaff", secondary=course_non_teaching_staffs, back_populates="courses", info={"label": "Personnels non-enseignants"})
    classroom_requirements: Mapped[list["CourseClassroomRequirement"]] = relationship(
        "CourseClassroomRequirement", back_populates="course",
        cascade="all, delete-orphan", passive_deletes=True,
        info={"label": "Salles requises"}
    )
    materials: Mapped[list["Material"]] = relationship("Material", secondary=course_materials, info={"label": "Matériels"})
    divisions: Mapped[list["Division"]] = relationship("Division", secondary=course_divisions, back_populates="courses", info={"label": "Classes / Divisions"})
    periods: Mapped[list["Period"]] = relationship("Period", secondary=course_periods, info={"label": "Périodes"})
    class_parts: Mapped[list["ClassPart"]] = relationship("ClassPart", secondary=course_class_parts, info={"label": "Parties de classe"})
    groups: Mapped[list["Group"]] = relationship("Group", secondary=course_groups, back_populates="courses", info={"label": "Groupes"})

    @property
    def has_conflict(self) -> bool:
        """Indique si le cours présente un conflit de ressources (calculé à la demande, séparé du statut matérialisé)."""
        from sqlalchemy.orm import object_session
        db = object_session(self)
        if not db or not self.timeslot_id:
            return False

        try:
            self.validate_placement_conflicts(db)
            return False
        except ValueError:
            return True

    @exposed(info={"label": "Durée pondérée", "type": "duration", "readOnly": True})
    @property
    def weighted_duration_minutes(self) -> int:
        return round(self.duration_minutes * self.weighting_coefficient)

    def _resolve_students(self) -> list:
        """
        Élèves du cours — calculé à la demande, jamais stocké : union des élèves des parties de
        classe et des divisions entières associées au cours (deux façons distinctes de rattacher
        un cours à des élèves, voir Course.divisions/Course.class_parts). Confort d'affichage
        (roster du cours) uniquement — le moteur de droits (voir architecture.md) traverse
        class_parts/divisions directement, il ne dépend pas de ce champ. Factorisé entre
        student_ids (juste les ids) et student_previews (nom/prénom/division, onglet "Élèves" du
        formulaire) : même requête, deux formes de sortie.
        """
        from sqlalchemy import or_
        from sqlalchemy.orm import object_session
        from backend.app.models.student import Student
        from backend.app.models.group import ClassPart

        db = object_session(self)
        if not db:
            return []
        class_part_ids = [cp.id for cp in self.class_parts]
        division_ids = [d.id for d in self.divisions]
        if not class_part_ids and not division_ids:
            return []
        conditions = []
        if class_part_ids:
            conditions.append(Student.class_parts.any(ClassPart.id.in_(class_part_ids)))
        if division_ids:
            conditions.append(Student.division_id.in_(division_ids))
        return list(db.execute(select(Student).where(or_(*conditions)).distinct()).scalars().all())

    @exposed
    @property
    def student_ids(self) -> list[int]:
        """Voir _resolve_students — ne garde que les ids (roster léger, utilisé par les tests)."""
        return [s.id for s in self._resolve_students()]

    @exposed(info={
        "label": "Élèves", "readOnly": True, "fullWidth": True,
        "widget": "list_preview",
        "widgetParams": {
            "columns": [
                {"key": "last_name", "label": "Nom", "width": "34%"},
                {"key": "first_name", "label": "Prénom", "width": "33%"},
                {"key": "division_name", "label": "Division", "width": "33%"},
            ],
            "listConfig": {"editableInline": False, "disableAdd": True, "disableEditModal": True, "allowMultiSelect": False},
        },
    })
    @property
    def student_previews(self) -> list[dict]:
        """Aperçu en lecture seule des élèves du cours (nom, prénom, division) — onglet "Élèves" du formulaire, voir _resolve_students."""
        return [
            {"id": s.id, "last_name": s.last_name, "first_name": s.first_name, "division_name": s.division.name if s.division else None}
            for s in self._resolve_students()
        ]

    @exposed(info={"label": "Répartition initiale", "readOnly": True})
    @property
    def composition_mapping(self) -> list[dict]:
        """
        Mapping proposé à l'ouverture du wizard "Décomposer le cours" (voir __actions__
        ci-dessous) — calculé à la demande, jamais stocké lui-même (seul composition_config l'est,
        voir plus haut). Priorité à la dernière configuration réellement validée
        (composition_config["mapping"], posée par rpc_save_composition — permet de "repréciser" le
        cours plus tard en repartant de ce qui a déjà été choisi) ; repli sur
        CompositionModes.default_mapping (composition_mode.py) si le cours n'a jamais été décomposé
        via ce wizard. Le nom de ce champ est délibérément identique à la clé du champ
        `list_preview` de l'étape "mapping" du wizard : GenericWizard.vue initialise son brouillon
        par un simple spread de l'enregistrement (`draft = {...props.model}`), donc cette valeur y
        est déjà présente à l'ouverture, sans code de plomberie wizard supplémentaire.
        """
        if self.composition_config and self.composition_config.get("mapping"):
            return self.composition_config["mapping"]
        from backend.app.models.composition_mode import CompositionModes
        return CompositionModes.default_mapping(self)

    @exposed(info={"label": "Mode de répartition (dernier utilisé)", "readOnly": True})
    @property
    def composition_mode(self) -> Optional[int]:
        """
        Symétrique de composition_mapping pour le mode temporel (1-9) : dernière valeur validée
        (composition_config["mode"]), None si le cours n'a jamais été décomposé via ce wizard —
        contrairement au mapping, il n'existe pas de "mode par défaut" à calculer, la grille de
        modes disponibles (CompositionModeOption) reste vide tant qu'aucune ligne de mapping n'est
        renseignée de toute façon.
        """
        if self.composition_config:
            return self.composition_config.get("mode")
        return None

    # Relations de ressources (hors matière) prises en compte pour la ventilation composé/enfants
    # — associées au champ _ids correspondant, seul nom que le front connaît (voir
    # Course.underventilated_resource_ids et _RESOURCE_FIELD_BY_RELATION un peu plus bas, qui
    # sert un usage différent — cascade parent/enfant — mais couvre les 7 mêmes relations).
    _VENTILATION_RELATIONS = (
        ('teachers', 'teacher_ids'),
        ('non_teaching_staffs', 'non_teaching_staff_ids'),
        ('divisions', 'division_ids'),
        ('groups', 'group_ids'),
        ('materials', 'material_ids'),
        ('class_parts', 'class_part_ids'),
    )
    # classroom_requirements n'est PAS dans ce tuple : c'est la seule relation de ressources
    # quantité-consciente (une même salle/groupe peut être nécessaire plusieurs fois), la
    # comparaison générique par différence d'ensembles d'ids serait incorrecte pour elle. Voir
    # CourseClassroomRequirement._cascade_decrement_parent_group_line pour son propre mécanisme
    # de cascade/ventilation (plan salles §1.5). L'affichage rouge de la carte cours pour les
    # salles reste à câbler séparément (plan salles, risque #7) — pas encore fait ici.

    def _missing_resource_ids_by_type(self, children_list) -> dict:
        """
        Pour chaque type de ressource (hors matière), IDs présents sur ce cours composé mais
        absents de TOUS les cours enfants de la liste — uniquement les types en défaut.
        """
        missing = {}
        for relation, field in self._VENTILATION_RELATIONS:
            parent_ids = {x.id for x in getattr(self, relation)}
            if not parent_ids:
                continue
            child_ids = set()
            for child in children_list:
                child_ids.update(x.id for x in getattr(child, relation))
            gap = parent_ids - child_ids
            if gap:
                missing[field] = sorted(gap)
        return missing

    def resources_fully_ventilated_list(self, children_list) -> bool:
        """Vérifie si toutes les ressources du cours composé sont attribuées à au moins un cours enfant de la liste."""
        if not self.is_composed:
            return True
        return not self._missing_resource_ids_by_type(children_list)

    def resources_fully_ventilated(self, exclude_child_id=None) -> bool:
        """Vérifie si toutes les ressources du cours composé sont attribuées à au moins un cours enfant."""
        children = [c for c in self.children if c.id != exclude_child_id]
        return self.resources_fully_ventilated_list(children)

    def recompute_status(self, exclude_child_id=None) -> str:
        """Calcule et met à jour le statut et l'état de décomposition du cours en base."""
        from sqlalchemy.orm import object_session
        db = object_session(self)
        
        # Autoriser la mise à jour interne de l'instance
        self._via_crud_mixin_update = True
        
        # 1. Statut de planification de base (status) : basé uniquement sur timeslot_id
        if not self.timeslot_id:
            self.status = CourseStatus.UNPLACED
        else:
            self.status = CourseStatus.PLACED

        # 2. Statut de décomposition (decomposition_status) : uniquement pour les cours composés
        if not self.is_composed:
            self.decomposition_status = None
            self.underventilated_resource_ids = None
        else:
            # Récupérer les enfants par requête directe (pas via self.children) ET les nouveaux
            # objets pas encore flushés. self.children est une collection ORM back_populates :
            # une fois chargée, elle reste en mémoire telle quelle pour le reste de la session,
            # y compris après la suppression d'un frère faite "de l'autre côté" par une requête
            # directe (voir Course.rpc_save_composition, qui boucle sur plusieurs child.delete()
            # d'affilée) — un accès ultérieur à un enfant déjà supprimé-et-flushé dans cette même
            # collection lève "Instance has been deleted". Une requête fraîche évite ce piège.
            children = set()
            if db:
                children.update(db.query(Course).filter(Course.parent_id == self.id).all())
                for obj in db.new:
                    if isinstance(obj, Course) and obj.parent_id is not None and obj.parent_id == self.id:
                        children.add(obj)
                for obj in db.deleted:
                    if isinstance(obj, Course) and obj in children:
                        children.remove(obj)
            elif self.children:
                children.update(self.children)
            
            # Appliquer l'exclusion si demandée
            if exclude_child_id:
                children = {c for c in children if c.id != exclude_child_id}
                
            if not children:
                self.decomposition_status = CourseDecompositionStatus.UNVENTILATED
                self.underventilated_resource_ids = None
            else:
                # 4. Calcul de la ventilation — uniquement l'affectation des ressources du
                # parent aux enfants, indépendamment de leur état de placement sur la grille
                # (status). Un cours composé peut donc être FULLY_VENTILATED avec des enfants
                # encore UNPLACED : ce sont deux diagnostics distincts (répartition structurelle
                # vs. planification), volontairement découplés.
                missing = self._missing_resource_ids_by_type(children)
                self.decomposition_status = CourseDecompositionStatus.PARTIALLY_VENTILATED if missing else CourseDecompositionStatus.FULLY_VENTILATED
                self.underventilated_resource_ids = missing or None

        # Si c'est un enfant, recalculer le statut de son parent
        if self.parent_id and db:
            parent = db.get(self.__class__, self.parent_id)
            if parent:
                parent._via_crud_mixin_update = True
                parent.recompute_status()
                
        return self.status

    @constrains()
    def validate_periods_coherence(self, db):
        if not self.period_type_id:
            if self.periods:
                raise ValueError("Un cours annuel (sans type de période défini) ne peut pas être associé à des périodes.")
        else:
            for period in self.periods:
                if period.period_type_id != self.period_type_id:
                    raise ValueError(
                        f"La période '{period.name}' (type {period.period_type_id}) ne correspond pas "
                        f"au type de période '{self.period_type_id}' du cours."
                    )

    def weighting_for(self, teacher_id: int) -> float:
        """
        Pondération applicable à un intervenant : la sienne si une exception est saisie, sinon
        celle du cours. C'est le seul point de lecture — personne ne doit interroger
        `teacher_weightings` directement, sous peine d'oublier le repli.
        """
        for ligne in self.teacher_weightings:
            if ligne.teacher_id == teacher_id:
                return ligne.weighting_coefficient
        return self.weighting_coefficient

    @exposed(info={"label": "Pondérations hétérogènes", "readOnly": True})
    @property
    def has_heterogeneous_weighting(self) -> bool:
        """
        Vrai si les intervenants de ce cours n'ont pas tous la même pondération. STS-web n'en
        accepte qu'une par service : c'est l'audit d'export qui doit le signaler, plutôt que de
        laisser un arbitrage silencieux se produire.
        """
        valeurs = {self.weighting_for(t.id) for t in self.teachers}
        return len(valeurs) > 1

    @property
    def is_in_sts_scope(self) -> bool:
        """
        Périmètre de la remontée : les **trois niveaux d'exclusion** — matière, classe,
        service/cours — plus la pondération nulle. Aucun des trois n'est redondant : ils répondent
        à trois gestes différents, exclure un enseignement, exclure une classe, exclure un cours.

        La pondération à zéro compte comme une exclusion parce que STS-web l'ignore de toute façon
        (« STSWEB ne prend pas en compte les cours dont la pondération est à zéro ») : autant que
        l'audit et l'export le disent avant, plutôt que de laisser le cours disparaître en silence
        à l'arrivée.

        Le périmètre est séparé du verdict (`is_exported_to_sts`) pour une seule raison : l'audit a
        besoin de désigner les cours qui *devraient* partir mais qu'un `week_type` en Q retient.
        Sans cette distinction, ils sortiraient à la fois de l'export et de l'audit — donc sans
        que personne ne l'apprenne.
        """
        if self.is_excluded_from_sts:
            return False
        if not self.weighting_coefficient:
            return False
        if self.subject_relation is not None and self.subject_relation.is_excluded_from_sts:
            return False
        if any(d.is_excluded_from_sts for d in self.divisions):
            return False
        return True

    @exposed(info={"label": "Remonté vers STS", "readOnly": True})
    @property
    def is_exported_to_sts(self) -> bool:
        """
        Verdict final : ce cours part-il dans le fichier de remontée ?

        C'est le périmètre ci-dessus, moins les cours en **Q**. Un cours en quinzaine non tranchée
        est écarté pour une raison structurelle et non réglementaire : il n'a pas d'alternance
        (voir `_sync_alternation`), et une séance sans `CODE_ALTERNANCE` est ignorée à la lecture.
        Il n'y a pas de calendrier « une semaine sur deux, on ne sait pas laquelle » à écrire.
        """
        if not self.is_in_sts_scope:
            return False
        week_type = self.week_type.value if hasattr(self.week_type, 'value') else self.week_type
        return week_type != CourseWeekType.Q.value

    @constrains('week_type', 'period_ids', 'period_type_id', 'alternation_id')
    def _sync_alternation(self, db):
        """
        Alternance du cours, CALCULÉE ET STOCKÉE (§15.F) : elle découle du couple
        (`week_type`, périodes) et n'est jamais saisie.

        `week_type` vaut ici A, B, W ou **Q** — quinzaine dont le côté n'est pas encore tranché
        (voir CourseWeekType). Un cours en Q n'a pas d'alternance : il n'existe pas de calendrier
        « une semaine sur deux, on ne sait pas laquelle ». L'alternance apparaîtra d'elle-même
        quand la résolution automatique aura fixé A ou B, cette contrainte étant réévaluée à
        chaque écriture de `week_type`.

        `alternation_id` figure exprès parmi les champs déclencheurs : écrire ce champ directement
        ne le fixe pas, cela relance le calcul qui l'écrase. C'est ce qui rend un cours en Q
        **impossible à rattacher** à une alternance, y compris par l'API générique, sans avoir à
        lever une erreur sur un champ que personne n'est censé saisir.

        Le solveur ne lit jamais ce champ ; il travaille sur `week_type`. C'est bien l'inverse :
        c'est la sortie du solveur qui alimente l'alternance, jamais l'alternance qui contraint
        le solveur.
        """
        from backend.app.models.alternation import Alternation

        week_type = self.week_type.value if hasattr(self.week_type, 'value') else self.week_type
        if week_type == CourseWeekType.Q.value:
            self.alternation_id = None
            return
        self.alternation_id = Alternation.search_or_create(
            db, week_type, [p.id for p in self.periods]
        ).id

    @onchange('children_ids')
    @constrains('children_ids')
    def _compute_is_composed(self, db=None):
        """Marque automatiquement le cours comme composé s'il a des cours enfants — indépendamment
        des ressources qui lui sont liées (nombre de profs ou autre) : un cours multi-ressource
        n'est pas nécessairement composé, et un cours composé ne l'est jamais par ses ressources."""
        self.is_composed = bool(getattr(self, 'children', None))

    @constrains('week_type', 'parent_id')
    def _sync_parent_week_type(self, db, exclude_child_id=None):
        """Si un enfant change d'alternance ou est supprimé, on recalcule celle de son parent."""
        if not self.parent_id:
            return

        parent = db.get(self.__class__, self.parent_id)
        if not parent:
            return

        # Requête directe plutôt que parent.children (voir recompute_status ci-dessus, même piège
        # de collection ORM obsolète après une suppression faite "de l'autre côté").
        children = [c for c in db.query(self.__class__).filter(self.__class__.parent_id == parent.id).all() if c.id != exclude_child_id]
        if not children:
            return
            
        types = {c.week_type.value for c in children if c.week_type}

        # Un vrai conflit A/B (au moins un enfant W, ou à la fois un enfant A et un enfant B)
        # remonte en W. Sinon, si tous les enfants partagent exactement A ou exactement B, le
        # parent prend cette valeur. Dans tous les autres cas — tous Q, ou un mélange de A+Q,
        # ou un mélange de B+Q — le parent est Q : le solveur pourra alors lui affecter A ou B,
        # et cette lettre sera reportée à tous les enfants (y compris ceux déjà résolus dans
        # l'autre sens) à l'issue de la résolution.
        if "W" in types or ("A" in types and "B" in types):
            parent.week_type = CourseWeekType.W
        elif types == {"A"}:
            parent.week_type = CourseWeekType.A
        elif types == {"B"}:
            parent.week_type = CourseWeekType.B
        else:
            parent.week_type = CourseWeekType.Q
        db.add(parent)

    @constrains('duration_minutes')
    def validate_duration_multiple(self, db):
        from backend.app.core.time_utils import validate_multiple_of_standard_timeslot
        validate_multiple_of_standard_timeslot(db, self.duration_minutes, "La durée du cours")

    @constrains('duration_minutes', 'parent_id', 'timeslot_id')
    def validate_child_constraints(self, db):
        """Vérifie qu'un cours enfant respecte les limites de temps, de ressources et de profondeur."""
        for child in self.children:
            child.validate_child_constraints(db)
            
        if not self.parent:
            return

        # 0. Contrainte de profondeur (2 niveaux max)
        if self.parent.parent_id is not None:
            raise ValueError("Un cours ne peut pas avoir comme parent un cours qui est lui-même enfant (2 niveaux maximum).")
        if self.children:
            raise ValueError("Un cours complexe (ayant déjà des enfants) ne peut pas devenir l'enfant d'un autre cours.")

        # 1. Contraintes temporelles
        # Si le cours a un parent, son créneau effectif est déterminé par le créneau du parent et l'offset
        # (évite les conflits transitoires lors de la propagation du parent vers l'enfant).
        effective_ts = self.timeslot
        if self.parent and self.parent.timeslot:
            from backend.app.models.timeslot import Timeslot
            ts_id = self.parent.timeslot.get_offset_timeslot(db, self.parent_timeslot_offset)
            effective_ts = db.get(Timeslot, ts_id) if ts_id else None

        if effective_ts and self.parent and self.parent.timeslot:
            # Même jour obligatoire
            if effective_ts.day_of_week != self.parent.timeslot.day_of_week:
                raise ValueError("Le cours enfant doit être le même jour que son parent.")
            
            # Heure de début
            if effective_ts.minutes_from_midnight < self.parent.timeslot.minutes_from_midnight:
                raise ValueError("Le début d'un cours enfant ne peut pas être antérieur au début du cours parent.")
            
            # Heure de fin
            child_end = effective_ts.minutes_from_midnight + self.duration_minutes
            parent_end = self.parent.timeslot.minutes_from_midnight + self.parent.duration_minutes
            if child_end > parent_end:
                raise ValueError("La fin d'un cours enfant ne peut pas être ultérieure à la fin du cours parent.")

        # La contrainte de confinement (l'enfant ne peut pas avoir une ressource absente du
        # parent) n'est plus une rejection : elle est maintenue automatiquement par la cascade
        # ressources enfant -> parent, voir Course._cascade_resources_to_parent.

    @constrains('parent_id', 'subject_id')
    def validate_child_requires_subject(self, db):
        """Un cours qui a un parent doit obligatoirement avoir sa propre matière — contrairement
        au parent lui-même, qui peut rester sans matière propre (ex: "Pôle Sciences")."""
        if self.parent_id is not None and self.subject_id is None:
            raise ValueError("Un cours enfant doit obligatoirement avoir une matière.")

    @constrains('teacher_ids', 'non_teaching_staff_ids', 'classroom_requirement_ids', 'division_ids', 'group_ids', 'material_ids', 'class_part_ids')
    def validate_has_at_least_one_resource(self, db):
        """
        Un cours doit toujours conserver au moins une ressource, tous types confondus (profs,
        personnel, salles, classes, groupes, matériel, parties de classe) — ne se déclenche que
        si l'appelant touche explicitement l'un de ces champs (voir @constrains), donc sans
        effet rétroactif sur un cours existant modifié sans toucher à ses ressources, ni sur une
        création qui ne fixe aucun de ces champs (cours "coquille" avant première affectation).
        """
        total = sum(len(getattr(self, rel)) for rel in self._RESOURCE_RELATIONS) + len(self.classroom_requirements)
        if total == 0:
            raise ValueError("Impossible de retirer la dernière ressource d'un cours : au moins un professeur, personnel non enseignant, salle, classe, groupe, matériel ou partie de classe doit rester.")

    @constrains('subject_id', 'teacher_ids', 'division_ids', 'group_ids', 'class_part_ids', 'is_composed')
    def compute_name(self, db):
        """Met à jour dynamiquement le nom du cours en fonction de ses attributs clés."""
        # 1. Base : La matière
        parts = []
        if getattr(self, 'subject_relation', None):
            parts.append(self.subject_relation.name)
        elif getattr(self, 'subject_id', None):
            from backend.app.models.subject import Subject
            subj = db.get(Subject, self.subject_id)
            if subj:
                parts.append(subj.name)
                
        if not parts:
            parts.append("Cours")
            
        if self.is_composed:
            self.name = f"Composé : {' - '.join(parts)}"
            return
            
        # 2. Audience : Divisions et Groupes
        audiences = []
        if getattr(self, 'divisions', None):
            audiences.extend([d.name for d in self.divisions if hasattr(d, 'name')])
        if getattr(self, 'groups', None):
            audiences.extend([g.name for g in self.groups if hasattr(g, 'name')])
            
        if audiences:
            parts.append(", ".join(audiences))
            
        # 3. Intervenants : Professeurs
        profs = []
        if getattr(self, 'teachers', None):
            profs.extend([t.last_name for t in self.teachers if hasattr(t, 'last_name')])
            
        if profs:
            parts.append(", ".join(profs))
            
        self.name = " - ".join(parts)

    def transform_to_simple_courses(self, db):
        """Transforme ce cours complexe en N cours simples en libérant ses enfants et en se supprimant."""
        if not self.is_composed:
            raise ValueError("Ce cours n'est pas composé.")
        
        for child in self.children:
            child.update(db, {'parent_id': None})
            
        self.delete(db)

    @classmethod
    def group_into_complex_course(cls, db, course_ids: list[int]):
        """Regroupe plusieurs cours simples non placés en un seul cours complexe parent."""
        courses = db.query(cls).filter(cls.id.in_(course_ids)).all()
        if not courses:
            raise ValueError("Aucun cours fourni.")
        
        for c in courses:
            if c.parent_id is not None:
                raise ValueError(f"Le cours {c.id} est déjà un cours enfant.")
            if c.timeslot_id is not None:
                raise ValueError(f"Le cours {c.id} est déjà placé sur la grille, veuillez le dépositionner d'abord.")

        first_course = courses[0]

        # Calcul de l'union de toutes les ressources des enfants
        def union_ids(attr):
            seen = set()
            result = []
            for c in courses:
                for item in getattr(c, attr):
                    if item.id not in seen:
                        seen.add(item.id)
                        result.append(item.id)
            return result

        # Cas particulier : classroom_requirements porte une quantity (voir
        # course_classroom_requirement.py), pas une simple présence — on prend le MAX de quantity
        # par classroom_id plutôt qu'une simple union d'ids.
        def union_classroom_requirements():
            by_classroom_id = {}
            for c in courses:
                for req in c.classroom_requirements:
                    by_classroom_id[req.classroom_id] = max(by_classroom_id.get(req.classroom_id, 0), req.quantity)
            return [{"classroom_id": cid, "quantity": qty} for cid, qty in by_classroom_id.items()]

        # Création du cours parent via CRUDMixin.create() pour passer par tous les hooks
        parent = cls.create(db, {
            'is_composed': True,
            'subject_id': first_course.subject_id,
            'school_id': first_course.school_id,
            'duration_minutes': max(c.duration_minutes for c in courses),
            'week_type': first_course.week_type,
            'teacher_ids': union_ids('teachers'),
            'non_teaching_staff_ids': union_ids('non_teaching_staffs'),
            'classroom_requirement_ids': union_classroom_requirements(),
            'division_ids': union_ids('divisions'),
            'group_ids': union_ids('groups'),
            'material_ids': union_ids('materials'),
            'class_part_ids': union_ids('class_parts'),
        })

        # Rattachement des enfants au parent via update() pour passer par les hooks
        for c in courses:
            c.update(db, {'parent_id': parent.id})

        return parent



    @constrains('is_pinned', 'timeslot_id')
    def validate_pinned_requires_timeslot(self, db):
        """
        Un cours épinglé (is_pinned=True) doit être placé (timeslot_id renseigné) : sinon, rien
        de concret n'est protégé, et — combiné à la garde de validate_placement_conflicts qui
        interdit timeslot_id + week_type=Q — cette règle garantit qu'un cours épinglé n'est
        jamais Q (voir attribution_week_type_auto.md). Couvre aussi bien le fait d'épingler un
        cours non placé que de retirer le créneau d'un cours qui reste épinglé.
        """
        if self.is_pinned and self.timeslot_id is None:
            raise ValueError("Impossible d'épingler un cours qui n'est pas placé sur un créneau.")

    @constrains('timeslot_id', 'duration_minutes', 'week_type', 'period_id', 'parent_id', 'teacher_ids', 'classroom_requirement_ids', 'division_ids', 'non_teaching_staff_ids', 'forbid_break_overlap')
    def validate_placement_conflicts(self, db):
        target_ts_id = self.timeslot_id
        if target_ts_id is None:
            return

        # Un cours en semaine Q (quinzaine à déterminer) ne peut jamais être placé sur la grille
        # — l'utilisateur (placement manuel) ou l'algorithme (placement automatique) doit d'abord
        # avoir choisi A ou B (voir attribution_week_type_auto.md). Garantie structurelle : ce
        # @constrains se déclenche sur tout create()/update() touchant timeslot_id OU week_type,
        # donc couvre aussi bien "placer un cours déjà Q" que "repasser en Q un cours déjà placé".
        if self.week_type == CourseWeekType.Q:
            raise ValueError("Impossible de placer un cours dont la semaine (A ou B) n'a pas encore été déterminée (quinzaine Q).")

        from backend.app.models.timeslot import Timeslot
        from backend.app.models.teacher import Teacher
        from backend.app.models.classroom import Classroom
        from backend.app.models.course_classroom_requirement import CourseClassroomRequirement
        from backend.app.models.division import Division
        from backend.app.models.non_teaching_staff import NonTeachingStaff

        target_ts = db.query(Timeslot).filter(Timeslot.id == target_ts_id).first()
        if not target_ts:
            raise ValueError("Créneau invalide")

        target_start = target_ts.minutes_from_midnight
        target_end = target_start + self.duration_minutes

        # Vérification du débordement en fin de journée — lue directement sur la grille
        # (GridDaySettings, source d'autorité de l'heure de fermeture) plutôt que re-dérivée du
        # MAX des Timeslot déjà existants pour ce jour (qui manquerait la vérification si aucun
        # créneau n'était encore posé ce jour-là).
        from backend.app.models.grid_day_settings import GridDaySettings
        day_settings = db.query(GridDaySettings).filter(GridDaySettings.day_of_week == target_ts.day_of_week).first()
        if day_settings and day_settings.hour_day_end_minutes_after_midnight is not None:
            if target_end > day_settings.hour_day_end_minutes_after_midnight:
                raise ValueError("Le cours déborde de la grille horaire de la journée.")

        # Option "Ne pas chevaucher les récréations" : la récréation n'est stockée qu'avec une
        # minute de début (pas de durée en base, voir SystemSetting), donc le chevauchement
        # interdit est le fait de contenir strictement cet instant (bornes strictes : un cours qui
        # démarre ou finit pile sur cette minute est autorisé).
        if self.forbid_break_overlap:
            from backend.app.models.system_setting import SystemSetting, SystemSettingKey
            for key, label in (
                (SystemSettingKey.HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT, "récréation du matin"),
                (SystemSettingKey.HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT, "récréation de l'après-midi"),
            ):
                raw = SystemSetting.get_system_setting_value(db, key.value)
                if raw and raw.isdigit():
                    break_minutes = int(raw)
                    if target_start < break_minutes < target_end:
                        raise ValueError(f"Le cours chevauche la {label} (option « Ne pas chevaucher les récréations » activée).")

        target_week_type = getattr(self, 'week_type', 'W')

        
        def get_conflict_query(resource_filter):
            query = db.query(Course).join(Timeslot).filter(
                Course.id != self.id,
                resource_filter,
                Timeslot.day_of_week == target_ts.day_of_week,
                Timeslot.minutes_from_midnight < target_end,
                target_start < (Timeslot.minutes_from_midnight + Course.duration_minutes)
            )
            
            # BR-001: Règle Globale d'Exclusivité des Ressources
            
            # Règle 1 : Orthogonalité Structurelle (Inclusion)
            from sqlalchemy import or_
            target_parent_id = getattr(self, 'parent_id', None)
            if target_parent_id:
                query = query.filter(
                    Course.id != target_parent_id,
                    or_(Course.parent_id == None, Course.parent_id != target_parent_id)
                )
            else:
                query = query.filter(
                    or_(Course.parent_id == None, Course.parent_id != self.id)
                )
                
            # Règle 2 : Orthogonalité Hebdomadaire (Alternance)
            if target_week_type == 'A':
                query = query.filter(Course.week_type.in_(['A', 'W']))
            elif target_week_type == 'B':
                query = query.filter(Course.week_type.in_(['B', 'W']))
                
            # Règle 3 : Orthogonalité Périodique (Périodes Multiples)
            if self.period_type_id and self.periods:
                from backend.app.models.period import Period
                target_period_ids = [p.id for p in self.periods]
                query = query.filter(
                    or_(
                        Course.period_type_id == None,
                        Course.period_type_id != self.period_type_id,
                        Course.periods.any(Period.id.in_(target_period_ids))
                    )
                )

            return query

        t_ids = [t.id for t in self.teachers]
        if t_ids:
            if get_conflict_query(Course.teachers.any(Teacher.id.in_(t_ids))).first():
                raise ValueError("Conflit : L'enseignant est déjà occupé sur ce créneau (chevauchement)")

        s_ids = [s.id for s in self.non_teaching_staffs]
        if s_ids:
            if get_conflict_query(Course.non_teaching_staffs.any(NonTeachingStaff.id.in_(s_ids))).first():
                raise ValueError("Conflit : Le membre du personnel est déjà occupé sur ce créneau (chevauchement)")

        # Uniquement les exigences sur salle-feuille précise (pas d'enfant dans l'arbre) : une
        # exigence de groupe n'a pas d'équivalent « conflit immédiat » à la saisie manuelle, sa
        # faisabilité relève du solveur (COURSE_PLACEMENT/CLASSROOM_ASSIGNMENT), pas de ce contrôle.
        cr_ids = [r.classroom_id for r in self.classroom_requirements if not r.classroom.children_classrooms]
        if cr_ids:
            if get_conflict_query(Course.classroom_requirements.any(CourseClassroomRequirement.classroom_id.in_(cr_ids))).first():
                raise ValueError("Conflit : La salle est déjà occupée sur ce créneau (chevauchement)")

        d_ids = [d.id for d in self.divisions]
        if d_ids:
            if get_conflict_query(Course.divisions.any(Division.id.in_(d_ids))).first():
                raise ValueError("Conflit : La division est déjà occupée sur ce créneau (chevauchement)")

    @classmethod
    def _sync_vals_from_parent(cls, db, vals: dict, instance=None):
        if 'parent_id' in vals and not vals['parent_id']:
            vals['parent_timeslot_offset'] = 0
            return
            
        parent_id = vals.get('parent_id', getattr(instance, 'parent_id', None))
        if parent := (db.get(cls, parent_id) if parent_id else None):
            from backend.app.models.timeslot import Timeslot
            
            # Si l'utilisateur ou le solveur force le timeslot_id de l'enfant, on recalcule l'offset
            if 'timeslot_id' in vals and vals['timeslot_id'] is not None:
                if not parent.timeslot_id:
                    raise ValueError("Impossible d'assigner un créneau directement à un cours enfant si son cours parent n'est pas encore planifié.")
                
                child_ts = db.get(Timeslot, vals['timeslot_id'])
                parent_ts = db.get(Timeslot, parent.timeslot_id)
                if child_ts and parent_ts:
                    if child_ts.day_of_week != parent_ts.day_of_week:
                        raise ValueError("Le cours enfant doit être placé le même jour que son parent.")
                    if child_ts.minutes_from_midnight < parent_ts.minutes_from_midnight:
                        raise ValueError("Le cours enfant ne peut pas commencer avant son parent.")
                    
                    # Inverse de Timeslot.get_offset_timeslot : le nombre de créneaux qui séparent
                    # le parent de l'enfant.
                    vals['parent_timeslot_offset'] = parent_ts.count_timeslots_between(db, child_ts)

            # Sync descendante (écrasement du timeslot de l'enfant)
            offset = vals.get('parent_timeslot_offset', getattr(instance, 'parent_timeslot_offset', 0))
            vals['is_pinned'] = parent.is_pinned
            vals['timeslot_id'] = None
            
            if parent.timeslot_id:
                if parent_ts := db.get(Timeslot, parent.timeslot_id):
                    vals['timeslot_id'] = parent_ts.get_offset_timeslot(db, offset)

    # Ressources (hors matière, qui suit ses propres règles) partagées entre un cours et son
    # parent — voir _cascade_resources_to_parent / _cascade_resource_removal_to_children.
    # classroom_requirements EXCLUE (voir _VENTILATION_RELATIONS ci-dessus) : sa propre cascade
    # quantité-consciente vit dans CourseClassroomRequirement._cascade_decrement_parent_group_line.
    _RESOURCE_RELATIONS = ('teachers', 'non_teaching_staffs', 'divisions', 'groups', 'materials', 'class_parts')
    _RESOURCE_FIELD_BY_RELATION = {
        'teachers': 'teacher_ids',
        'non_teaching_staffs': 'non_teaching_staff_ids',
        'divisions': 'division_ids',
        'groups': 'group_ids',
        'materials': 'material_ids',
        'class_parts': 'class_part_ids',
    }

    def _resource_ids_snapshot(self) -> dict:
        return {rel: {r.id for r in getattr(self, rel)} for rel in self._RESOURCE_RELATIONS}

    def _cascade_resources_to_parent(self, db: Session) -> None:
        """
        Ajouter une ressource (hors matière) à un cours qui a un parent l'ajoute aussi au
        parent si celui-ci ne l'avait pas déjà — jamais l'inverse (ajouter une ressource au
        parent n'a pas d'impact sur les enfants, voir spec.md). Idempotent et basé sur l'état
        COURANT de `self` (pas un diff avant/après) : couvre aussi bien l'ajout d'une nouvelle
        ressource que le rattachement de `self` à un nouveau parent (ses ressources existantes
        doivent alors rejoindre ce parent).
        """
        if not self.parent_id:
            return
        parent = db.get(self.__class__, self.parent_id)
        if not parent:
            return

        self_snapshot = self._resource_ids_snapshot()
        parent_vals = {}
        for rel, self_ids in self_snapshot.items():
            parent_ids = {r.id for r in getattr(parent, rel)}
            missing = self_ids - parent_ids
            if missing:
                parent_vals[self._RESOURCE_FIELD_BY_RELATION[rel]] = list(parent_ids | missing)
        if parent_vals:
            parent.update(db, parent_vals)

    def _cascade_resource_removal_to_children(self, db: Session, before: dict) -> None:
        """
        Retirer une ressource d'un cours la retire de TOUS ses enfants — jamais l'inverse
        (retirer une ressource d'un enfant n'a pas d'impact sur le parent, voir spec.md).
        `before` est l'état de `self` juste avant l'appel à super().update() ; seules les
        ressources RÉELLEMENT retirées par cet appel sont propagées.
        """
        # Requête directe plutôt que self.children (voir recompute_status/_sync_parent_week_type,
        # même piège de collection ORM obsolète après une suppression faite "de l'autre côté").
        children = db.query(self.__class__).filter(self.__class__.parent_id == self.id).all()
        if not children:
            return

        after_snapshot = self._resource_ids_snapshot()
        removed_by_relation = {
            rel: before[rel] - after_snapshot[rel]
            for rel in self._RESOURCE_RELATIONS
            if before[rel] - after_snapshot[rel]
        }
        if not removed_by_relation:
            return

        for child in children:
            child_vals = {}
            for rel, removed_ids in removed_by_relation.items():
                child_ids = {r.id for r in getattr(child, rel)}
                remaining = child_ids - removed_ids
                if remaining != child_ids:
                    child_vals[self._RESOURCE_FIELD_BY_RELATION[rel]] = list(remaining)
            if child_vals:
                child.update(db, child_vals)

    @staticmethod
    def _apply_group_class_part_cascade(db: Session, vals: dict, current_group_ids: set[int], current_class_part_ids: set[int]) -> None:
        """
        Un Group "est composé de" ClassPart : l'ajout d'un Group à un Course doit donc y
        ajouter toutes ses ClassPart (mais l'inverse est faux, ajouter une ClassPart n'a
        aucun effet sur les Group) ; le retrait d'un Group retire ses ClassPart du cours ;
        le retrait d'une ClassPart retire tout Group qui en est composé, SANS que ce
        retrait de Group ne retire à son tour ses AUTRES ClassPart (un seul niveau de
        cascade, jamais de réaction en chaîne — voir spec.md, section Group/ClassPart).
        Mute `vals` en place ('group_ids'/'class_part_ids') avant l'appel à
        super().create()/update(), pour que le remplacement de collection (base.py) fasse
        le travail en un seul passage atomique.
        """
        touches_groups = 'group_ids' in vals
        touches_class_parts = 'class_part_ids' in vals
        if not touches_groups and not touches_class_parts:
            return

        from backend.app.models.group import Group

        requested_group_ids = set(vals['group_ids']) if touches_groups else set(current_group_ids)
        requested_class_part_ids = set(vals['class_part_ids']) if touches_class_parts else set(current_class_part_ids)

        explicitly_added_groups = (requested_group_ids - current_group_ids) if touches_groups else set()
        explicitly_removed_groups = (current_group_ids - requested_group_ids) if touches_groups else set()
        explicitly_removed_class_parts = (current_class_part_ids - requested_class_part_ids) if touches_class_parts else set()

        relevant_group_ids = requested_group_ids | explicitly_removed_groups
        groups_class_parts: dict[int, set[int]] = {}
        if relevant_group_ids:
            groups = db.execute(select(Group).filter(Group.id.in_(relevant_group_ids))).scalars().all()
            groups_class_parts = {g.id: {cp.id for cp in g.class_parts} for g in groups}

        # Règle 1 (ajout) / règle 3 (retrait), avec une protection : une ClassPart n'est
        # retirée par le retrait de son Group que si aucun AUTRE Group restant sur le cours
        # n'en a encore besoin (un Group présent doit toujours voir toutes ses ClassPart
        # présentes, invariant posé par la règle 1).
        surviving_group_ids = requested_group_ids
        protected_class_part_ids = set().union(*(groups_class_parts.get(gid, set()) for gid in surviving_group_ids))
        added_via_groups = set().union(*(groups_class_parts.get(gid, set()) for gid in explicitly_added_groups))
        removed_via_groups = set().union(*(groups_class_parts.get(gid, set()) for gid in explicitly_removed_groups))
        removed_via_groups -= protected_class_part_ids

        final_class_part_ids = (requested_class_part_ids | added_via_groups) - removed_via_groups

        # Règle 4 : ClassPart retirée -> retire tout Group composé de cette ClassPart. On
        # cascade uniquement depuis le retrait explicitement demandé par l'appelant (jamais
        # depuis une ClassPart retirée ci-dessus via la règle 3), pour ne pas déclencher de
        # réaction en chaîne.
        groups_removed_via_rule4 = {
            gid for gid in surviving_group_ids
            if groups_class_parts.get(gid, set()) & explicitly_removed_class_parts
        }
        final_group_ids = surviving_group_ids - groups_removed_via_rule4

        vals['group_ids'] = list(final_group_ids)
        vals['class_part_ids'] = list(final_class_part_ids)

    @classmethod
    def create(cls, db: Session, vals: dict):
        # 1. Synchronisation avec le parent (si applicable)
        cls._sync_vals_from_parent(db, vals)

        # Cascade Group <-> ClassPart (voir _apply_group_class_part_cascade) : un Course
        # créé avec group_ids doit recevoir les class_part_ids de ces Group dès la création.
        cls._apply_group_class_part_cascade(db, vals, set(), set())

        # 2. Sauvegarde
        instance = super().create(db, vals)

        # Recalculer le statut du nouveau cours
        instance.recompute_status()

        # Cascade ressources -> parent (voir _cascade_resources_to_parent) : les ressources du
        # nouvel enfant doivent déjà toutes être présentes sur le parent.
        instance._cascade_resources_to_parent(db)

        if instance.parent_id:
            parent = db.get(cls, instance.parent_id)
            if parent:
                parent.recompute_status()

        return instance

    def update(self, db: Session, vals: dict):
        # Un cours épinglé (is_pinned=True, et le restant après cet appel) ne peut pas être
        # déplacé manuellement — créneau, salle ou semaine — miroir de la garde déjà appliquée
        # par le solveur (@PlanningPin sur PlanningCourse.is_pinned, qui gèle déjà timeslot et
        # classroom pour le placement automatique) : rien ne l'empêchait côté placement manuel
        # jusqu'ici (voir attribution_week_type_auto.md, Échange 4). Déverrouiller ET déplacer
        # dans le même appel reste autorisé (is_pinned=False dans les mêmes vals désactive la
        # garde) ; seuls les VALEURS EFFECTIVEMENT CHANGÉES déclenchent le refus, pour ne pas
        # bloquer le simple renvoi du timeslot_id courant (ex: bascule du pin via CourseCard.vue).
        new_is_pinned = vals.get('is_pinned', self.is_pinned)
        if self.is_pinned and new_is_pinned:
            if 'timeslot_id' in vals and vals['timeslot_id'] != self.timeslot_id:
                raise ValueError("Impossible de déplacer un cours épinglé : déverrouillez-le d'abord.")
            if 'classroom_requirement_ids' in vals:
                raise ValueError("Impossible de changer la salle d'un cours épinglé : déverrouillez-le d'abord.")
            if 'week_type' in vals and str(vals['week_type']) != str(self.week_type.value):
                raise ValueError("Impossible de changer la semaine d'un cours épinglé : déverrouillez-le d'abord.")

        # Ceinture et bretelles pour le split de colonnes A/B du placement manuel (voir
        # attribution_week_type_auto.md, Échanges 3-4) : un cours de type W ne doit jamais
        # basculer vers A/B "lors du placement" (cet appel posant un VRAI timeslot_id — pas le
        # mettant à None — EN MÊME TEMPS que week_type) — le frontend ne doit déjà jamais envoyer
        # ce cas de figure (les zones de dépose scindées sont désactivées pour un cours W), cette
        # garde protège contre tout autre client de l'API (appel direct, futur multi-section).
        # Dépositionner (timeslot_id=None) en changeant la semaine dans le même appel reste
        # autorisé — ce n'est pas un placement (voir test_solver_group_link_and_week_alternation,
        # qui dépositionne + résout la semaine avant de relancer le solveur).
        if 'week_type' in vals and vals.get('timeslot_id') is not None:
            old_week_type = self.week_type.value if hasattr(self.week_type, 'value') else self.week_type
            new_week_type = str(vals['week_type'])
            if old_week_type == 'W' and new_week_type in ('A', 'B'):
                raise ValueError("Un cours en semaine 'Toutes les semaines' (W) ne peut pas devenir Semaine A ou B lors d'un placement.")

        # 1. Synchronisation avec le parent (si applicable)
        self.__class__._sync_vals_from_parent(db, vals, instance=self)

        old_parent_id = self.parent_id

        # Capturé avant sauvegarde si la répartition change : une partie de classe/un groupe
        # retiré ici peut devenir orphelin (voir backend/app/models/group.py, cleanup_orphaned_resources).
        track_resource_cleanup = 'class_part_ids' in vals or 'group_ids' in vals
        before_class_part_ids = {cp.id for cp in self.class_parts} if track_resource_cleanup else set()
        before_group_ids = {g.id for g in self.groups} if track_resource_cleanup else set()

        # Cascade Group <-> ClassPart (voir _apply_group_class_part_cascade) : mute vals
        # avant l'appel à super().update() pour que le remplacement de collection ci-dessous
        # applique déjà le résultat cascadé en un seul passage.
        self.__class__._apply_group_class_part_cascade(db, vals, before_group_ids, before_class_part_ids)

        # Capturé avant sauvegarde pour la cascade ressources <-> parent/enfants ci-dessous
        # (voir _cascade_resources_to_parent / _cascade_resource_removal_to_children).
        touches_any_resource = any(f in vals for f in self._RESOURCE_FIELD_BY_RELATION.values())
        before_resources = self._resource_ids_snapshot() if touches_any_resource else None
        parent_id_changed = 'parent_id' in vals and vals['parent_id'] != old_parent_id

        # 3. Sauvegarde
        res = super().update(db, vals)

        if track_resource_cleanup:
            from backend.app.models.group import cleanup_orphaned_resources
            removed_class_part_ids = before_class_part_ids - {cp.id for cp in self.class_parts}
            removed_group_ids = before_group_ids - {g.id for g in self.groups}
            cleanup_orphaned_resources(db, list(removed_class_part_ids), list(removed_group_ids))

        # Cascade ressources -> parent (ajout) et parent -> enfants (retrait) — voir spec.md,
        # section Course, « Cascade de membership des ressources parent/enfant ».
        if self.parent_id and (touches_any_resource or parent_id_changed):
            self._cascade_resources_to_parent(db)
        if touches_any_resource:
            self._cascade_resource_removal_to_children(db, before_resources)

        # Recalculer son propre statut
        self.recompute_status()

        # Faire remonter au parent
        if old_parent_id and old_parent_id != self.parent_id:
            old_parent = db.get(self.__class__, old_parent_id)
            if old_parent:
                old_parent.recompute_status(exclude_child_id=self.id)
        if self.parent_id:
            parent = db.get(self.__class__, self.parent_id)
            if parent:
                parent.recompute_status()

        # 4. Si on a bougé, on propage le mouvement aux enfants en forçant leur recalcul
        if 'timeslot_id' in vals or 'is_pinned' in vals:
            for child in self.children:
                child.update(db, {})

        return res

    def compose_by_mode(self, db: Session, mode: int, mapping: list[dict] = None) -> dict:
        """Méthode RPC legacy conservée pour compatibilité."""
        from backend.app.models.composition_mode import CompositionModes
        children = CompositionModes.apply(db, self, mode, mapping, preview=False)
        return {
            "status": "ok",
            "parent_id": self.id,
            "mode": mode,
            "children_ids": [c.id for c in children],
            "count": len(children),
        }

    @requires_access("write")
    def rpc_preview_composition(self, db: Session, mode: int, mapping: list[dict]) -> dict:
        """Génère l'aperçu des enfants sans les sauvegarder."""
        from backend.app.models.composition_mode import CompositionModes
        children_vals = CompositionModes.apply(db, self, mode, mapping, preview=True)
        return {"status": "ok", "children_vals": children_vals}

    @requires_access("write")
    def rpc_cancel_composition(self, db: Session) -> dict:
        """
        Appelée quand l'utilisateur quitte l'assistant sans valider. Ne fait plus rien : depuis que
        "Générer l'aperçu" (rpc_preview_composition) ne crée plus la moindre ressource réelle
        (Partition/ClassPart/Group restent de simples jetons virtuels tant que "Valider" n'a pas été
        cliqué, voir CompositionModes._resolve_dynamic_part_class/_resolve_dynamic_groups et
        materialize_pending_resources), il n'y a structurellement plus rien à nettoyer — élimine la
        classe de bug qui existait ici auparavant (fuite de ressources orphelines quand le cours
        parent n'était pas encore composé, is_composed=False, avant ce changement).
        """
        return {"status": "ok"}

    @requires_access("write")
    def rpc_save_composition(self, db: Session, children_vals: list[dict], mapping: list[dict] = None, mode: int = None) -> dict:
        """
        Sauvegarde définitivement les enfants modifiés par l'utilisateur. Résout d'abord pour de
        vrai (materialize_pending_resources) toute ressource (Partition/ClassPart/Group) restée en
        attente depuis l'aperçu — c'est le SEUL moment où ces ressources sont réellement créées.

        mapping/mode (optionnels, envoyés par le wizard — voir __actions__ ci-dessus, rpcParams de
        l'étape "preview") : persistés sur composition_config pour pré-remplir le wizard à sa
        prochaine ouverture et permettre de "repréciser" le cours plus tard (voir
        Course.composition_mapping/composition_mode). Absents pour un appel direct (tests, chemin
        legacy) : composition_config n'est alors simplement pas mis à jour.
        """
        from backend.app.models.composition_mode import CompositionModes
        children_vals = CompositionModes.materialize_pending_resources(db, self, children_vals)
        # 1. Supprimer les anciens enfants proprement sans déclencher de synchronisation intermédiaire sur le parent
        # Pas de détachement préalable (child.parent_id = None) : ce serait une mutation directe
        # hors CRUDMixin, or Course.delete() fait un premier db.flush() (nettoyage
        # ResourcePreference) AVANT d'appeler super().delete() — donc avant que
        # _via_crud_mixin_delete/_via_crud_mixin_update soient positionnés. Cet enfant resterait
        # "sale" au moment de ce flush, et le before_update générique le rejetterait ("Mise à jour
        # directe interdite"). Inutile de toute façon : l'enfant va être supprimé, nul besoin de
        # vider sa FK avant. Garder parent_id intact permet aussi à Course.delete() de retrouver le
        # parent pour recompute_status()/_sync_parent_week_type().
        # _skip_resource_cleanup=True : voir CompositionModes.apply, même piège — le nettoyage est
        # différé après la recréation des enfants (juste en dessous), pour ne pas supprimer pour de
        # vrai une partie de classe/un groupe que children_vals s'apprête à réutiliser.
        children_to_delete = db.query(Course).filter(Course.parent_id == self.id).all()
        former_class_part_ids = set()
        former_group_ids = set()
        for child in children_to_delete:
            former_class_part_ids.update(cp.id for cp in child.class_parts)
            former_group_ids.update(g.id for g in child.groups)
            child.delete(db, _skip_resource_cleanup=True)

        # 2. Créer les nouveaux enfants de manière isolée pour éviter de perturber le parent prématurément
        children = []
        for vals in children_vals:
            vals_copy = dict(vals)
            # Ne pas lier au parent tout de suite pour éviter les flushs conflictuels
            vals_copy.pop('parent_id', None)
            # Mais il faut s'assurer qu'ils aient le bon school_id (et subject_id) qui seraient normalement copiés du parent
            vals_copy.setdefault('school_id', self.school_id)
            vals_copy.setdefault('subject_id', self.subject_id)

            children.append(Course.create(db, vals_copy))

        from backend.app.models.group import cleanup_orphaned_resources
        cleanup_orphaned_resources(db, list(former_class_part_ids), list(former_group_ids))

        # 3. Rattacher tous les enfants au parent via la méthode officielle update()
        # Cela déclenchera correctement les calculs métier (@onchange, etc). composition_config
        # embarqué dans le même appel (pas un update() séparé) : mapping/mode ne sont significatifs
        # que si la sauvegarde des enfants réussit, les deux doivent progresser ensemble.
        update_vals = {'children_ids': [c.id for c in children]}
        if mapping is not None and mode is not None:
            update_vals['composition_config'] = {"mapping": mapping, "mode": mode}
        self.update(db, update_vals)

        return {
            "status": "ok",
            "parent_id": self.id,
            "children_ids": [c.id for c in children],
            "count": len(children),
        }

    def delete(self, db: Session, _skip_resource_cleanup: bool = False):
        """
        _skip_resource_cleanup : à True quand l'appelant supprime ce cours pour le recréer aussitôt
        avec (potentiellement) les mêmes ressources (voir CompositionModes.apply et
        rpc_save_composition) — sans ça, le nettoyage réactif ci-dessous supprimerait pour de vrai
        une partie de classe/un groupe encore réutilisé par le cours qui n'a pas encore été recréé
        au moment de cet appel. L'appelant est alors responsable d'appeler lui-même
        cleanup_orphaned_resources (voir backend/app/models/group.py) une fois la recréation terminée.
        """
        from sqlalchemy import delete
        from backend.app.models.preference import ResourcePreference
        db.execute(delete(ResourcePreference).filter_by(
            resource_type="Course",
            resource_id=self.id
        ))
        db.flush()

        # Capturé avant suppression : une fois le cours supprimé, ces parties de classe/groupes
        # peuvent devenir orphelins (voir backend/app/models/group.py, cleanup_orphaned_resources).
        former_class_part_ids = [cp.id for cp in self.class_parts]
        former_group_ids = [g.id for g in self.groups]

        parent_id = self.parent_id
        res = super().delete(db)
        if parent_id:
            parent = db.get(self.__class__, parent_id)
            if parent:
                parent._via_crud_mixin_update = True
                parent.recompute_status(exclude_child_id=self.id)
            self._sync_parent_week_type(db, exclude_child_id=self.id)

        if not _skip_resource_cleanup:
            from backend.app.models.group import cleanup_orphaned_resources
            cleanup_orphaned_resources(db, former_class_part_ids, former_group_ids)
        return res
