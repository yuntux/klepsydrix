from datetime import date
from typing import Optional
from sqlalchemy import Integer, String, Boolean, Date, ForeignKey, Enum, false as sa_false
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import Session
from backend.app.models.gender import Gender, gender_field_info
from backend.app.models.base import Base, constrains, exposed
from backend.app.models.user import HasUserAccount


class Student(HasUserAccount, Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Prénom"})
    last_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom"})
    gender: Mapped[Optional[str]] = mapped_column(Enum(Gender, name="gender_enum"), nullable=True, info=gender_field_info())
    division_id: Mapped[int] = mapped_column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False, info={"label": "Division"})
    mef_id: Mapped[int] = mapped_column(Integer, ForeignKey("mefs.id", ondelete="CASCADE"), nullable=False, info={"label": "MEF"})
    tutor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, info={"label": "Tuteur"})
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, unique=True, info={"label": "Compte utilisateur"})

    # Identifiants SIECLE (ElevesAvecAdresses/ELEVE) : posés par l'import, jamais saisis à la main
    # — d'où readOnly. `national_id` (ID_NATIONAL) sert de clé d'appariement à l'import ; `ine_bea`
    # et `elenoet` n'ont pas cette garantie d'unicité (voir FORMATS_JUSTIFICATION.md) et ne sont
    # conservés qu'à titre informatif.
    national_id: Mapped[Optional[str]] = mapped_column(String(20), unique=True, index=True, nullable=True, info={"label": "Identifiant national (INE)", "readOnly": True})
    ine_bea: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "INE BEA", "readOnly": True})
    elenoet: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Numéro interne (ELENOET)", "readOnly": True})
    # `@ELEVE_ID` du fichier — un QUATRIÈME identifiant, distinct des trois ci-dessus : c'est la clé
    # interne à CET EXPORT SIECLE (pas une clé nationale stable comme national_id), utilisée dans le
    # fichier pour croiser STRUCTURES/OPTIONS/RESPONSABLE entre eux. Rien ne garantit qu'elle reste
    # la même d'un export à l'autre ; on ne l'utilise donc jamais comme clé d'appariement, mais elle
    # doit être conservée pour retrouver, plus tard, à quel élève un futur export SIECLE (ex. le
    # rattachement groupe/élève) doit se référer.
    siecle_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, info={"label": "Identifiant SIECLE (export)", "readOnly": True})

    # État civil, même patron que Teacher (NOM_USAGE -> last_name, NOM_DE_FAMILLE -> birth_last_name)
    birth_last_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Nom de naissance"})
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date de naissance"})
    birth_city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_cities.id", ondelete="SET NULL"), nullable=True, info={"label": "Ville de naissance"})

    doublement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Redoublant"})
    regime_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_regimes.id", ondelete="SET NULL"), nullable=True, info={"label": "Régime"})

    # Critères de répartition pour le wizard « Affectation des élèves aux classes » (Pré-rentrée,
    # voir wizard_student_class_assignment.py) — non renseigné (NULL) tant qu'aucune évaluation
    # n'a été saisie, plutôt qu'une valeur sentinelle dans le domaine 1-10.
    attendance_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={
        "label": "Assiduité", "help": "1 = très absentéiste, 10 = jamais absent.", "min": 1, "max": 10, "step": "1",
    })
    academic_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={
        "label": "Résultats scolaires", "help": "1 = résultats faibles, 10 = excellents résultats.", "min": 1, "max": 10, "step": "1",
    })
    behavior_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, info={
        "label": "Comportement", "help": "1 = comportement difficile, 10 = comportement exemplaire.", "min": 1, "max": 10, "step": "1",
    })

    # Scolarité : DATE_ENTREE/DATE_SORTIE/CODE_MOTIF_SORTIE. `exit_reason_id` n'a de sens que si une
    # sortie est actée (readOnlyExpr côté IHM) — voir _check_exit_date_after_entry_date.
    entry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date d'entrée"})
    exit_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date de sortie"})
    exit_reason_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("ref_exit_reasons.id", ondelete="SET NULL"), nullable=True,
        info={"label": "Motif de sortie", "readOnlyExpr": "!model.exit_date"},
    )

    # Scolarité l'an dernier (SCOLARITE_AN_DERNIER) : CODE_STRUCTURE n'a pas de référentiel propre
    # (c'est un libellé de classe dans un autre établissement, jamais réutilisé ailleurs) et reste
    # en texte libre ; l'établissement d'origine, lui, est un référentiel partagé (RefExternalSchool).
    last_year_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Classe l'an dernier"})
    last_year_school_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_external_schools.id", ondelete="SET NULL"), nullable=True, info={"label": "Établissement l'an dernier"})

    # Relations de navigation
    division: Mapped[Optional["Division"]] = relationship("Division", back_populates="students")
    mef: Mapped[Optional["Mef"]] = relationship("Mef")
    tutor: Mapped[Optional["Teacher"]] = relationship("Teacher", foreign_keys=[tutor_id])
    user: Mapped[Optional["User"]] = relationship("User", back_populates="student", foreign_keys=[user_id])
    birth_city: Mapped[Optional["RefCity"]] = relationship("RefCity", foreign_keys=[birth_city_id])
    regime: Mapped[Optional["RefRegime"]] = relationship("RefRegime")
    exit_reason: Mapped[Optional["RefExitReason"]] = relationship("RefExitReason")
    last_year_school: Mapped[Optional["RefExternalSchool"]] = relationship("RefExternalSchool")
    # Parties de classe ACTUELLES (lien ouvert, end_date NULL) — relation SQL en lecture seule
    # (viewonly), filtrée via StudentClassPartLink, mais avec le MÊME nom et la MÊME forme que
    # l'ancien Many-to-Many `student_class_parts` qu'elle remplace : tout le reste de l'application
    # (solveur, roster de cours, moteur de droits — voir access_control.py, le chemin pointé
    # `class_parts.students.user_id` est l'exemple canonique de son propre docstring) continue de
    # lire `Student.class_parts`/`ClassPart.students` sans rien savoir de l'historique. L'édition,
    # elle, passe exclusivement par `class_part_links` ci-dessous.
    class_parts: Mapped[list["ClassPart"]] = relationship(
        "ClassPart",
        secondary="student_class_part_links",
        primaryjoin="and_(Student.id == StudentClassPartLink.student_id, StudentClassPartLink.end_date.is_(None))",
        secondaryjoin="StudentClassPartLink.class_part_id == ClassPart.id",
        viewonly=True,
        info={"label": "Parties de classe", "readOnly": True},
    )
    # Historique complet et éditable (voir StudentClassPartLink) : plusieurs lignes possibles pour
    # le même ClassPart, un élève pouvant le quitter puis y revenir.
    class_part_links: Mapped[list["StudentClassPartLink"]] = relationship(
        "StudentClassPartLink", back_populates="student", passive_deletes="all", order_by="StudentClassPartLink.begin_date",
        info={
            "label": "Parties de classe",
            "widget": "many2many_ordered_list",
            "widgetParams": {
                "pickResource": "class_parts",
                "pickField": "class_part_id",
                "parentField": "student_id",
                "columns": [
                    {"key": "class_part_id", "label": "Partie de classe", "editable": True},
                    {"key": "begin_date", "label": "Date de début", "editable": True},
                    {"key": "end_date", "label": "Date de fin", "editable": True},
                ],
            },
        },
    )
    specialty_choices: Mapped[list["StudentSpecialtyChoice"]] = relationship(
        "StudentSpecialtyChoice", back_populates="student", passive_deletes="all", order_by="StudentSpecialtyChoice.rank",
        info={
            "label": "Vœux de spécialité et options",
            "widget": "many2many_ordered_list",
            "widgetParams": {
                "pickResource": "subjects",
                "pickField": "subject_id",
                "parentField": "student_id",
                "columns": [
                    {"key": "subject_id", "label": "Matière", "editable": True},
                    {"key": "election_method_id", "label": "Modalité d'élection", "resource": "ref_election_methods", "editable": True},
                ],
            },
        },
    )
    accompaniment_projects: Mapped[list["StudentAccompanimentProject"]] = relationship(
        "StudentAccompanimentProject", back_populates="student", passive_deletes="all", order_by="StudentAccompanimentProject.start_date",
        info={
            "label": "Projets d'accompagnement",
            "widget": "many2many_ordered_list",
            "widgetParams": {
                "pickResource": "ref_accompaniment_project_types",
                "pickField": "project_type_id",
                "parentField": "student_id",
                "columns": [
                    {"key": "project_type_id", "label": "Dispositif", "editable": True},
                    {"key": "start_date", "label": "Date de début", "editable": True},
                    {"key": "end_date", "label": "Date de fin", "editable": True},
                    {"key": "notes", "label": "Notes", "editable": True},
                ],
            },
        },
    )
    # Côté élève : liste éditable des responsables rattachés (remplace les anciens parent1_id/
    # parent2_id, plafonnés à deux — voir StudentParentLink). Côté parent (Parent.student_links),
    # la même table est exposée en lecture seule : un responsable ne se rattache pas lui-même à un
    # élève depuis sa propre fiche.
    parent_links: Mapped[list["StudentParentLink"]] = relationship(
        "StudentParentLink", back_populates="student", passive_deletes="all",
        info={
            "label": "Responsables",
            "widget": "many2many_ordered_list",
            "widgetParams": {
                "pickResource": "parents",
                "pickField": "parent_id",
                "parentField": "student_id",
                "columns": [
                    {"key": "parent_id", "label": "Responsable", "editable": True},
                    {"key": "relative_link_id", "label": "Lien de parenté", "resource": "ref_relative_links", "editable": True},
                    {"key": "legal_guardian_id", "label": "Responsabilité légale", "resource": "ref_legal_guardians", "editable": True},
                    {"key": "responsibility_level", "label": "Niveau de responsabilité", "editable": True},
                    {"key": "pays_school_fees", "label": "Paie les frais scolaires", "editable": True},
                    {"key": "is_financially_responsible", "label": "Responsable financier", "editable": True},
                    {"key": "receives_financial_aid", "label": "Perçoit les aides financières", "editable": True},
                    {"key": "is_contact", "label": "Contact", "editable": True},
                ],
            },
        },
    )

    @constrains()
    def _check_student_mef_matches_division(self, db: Session):
        from backend.app.models.mef import MefDivision
        linked = db.query(MefDivision).filter(
            MefDivision.division_id == self.division_id,
            MefDivision.mef_id == self.mef_id
        ).first()
        if not linked:
            raise ValueError(f"Le MEF de l'élève {self.first_name} {self.last_name} doit être l'un des MEF liés à sa division.")

    @constrains("entry_date", "exit_date")
    def _check_exit_date_after_entry_date(self, db: Session):
        if self.entry_date and self.exit_date and self.exit_date < self.entry_date:
            raise ValueError("La date de sortie doit être postérieure ou égale à la date d'entrée.")

    @constrains("attendance_score", "academic_score", "behavior_score")
    def _check_scores_within_range(self, db: Session):
        for field, label in (
            ("attendance_score", "Assiduité"), ("academic_score", "Résultats scolaires"), ("behavior_score", "Comportement"),
        ):
            value = getattr(self, field)
            if value is not None and not (1 <= value <= 10):
                raise ValueError(f"Le score « {label} » doit être compris entre 1 et 10 (ou vide si non évalué).")

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @exposed
    @property
    def criterion_city_id(self) -> Optional[int]:
        """
        Ville utilisée comme critère de répartition par le wizard d'affectation aux classes :
        celle du responsable légal 1, à défaut du responsable légal 2, à défaut du premier
        responsable rattaché — jamais stockée, calculée à la demande depuis les responsables déjà
        liés (voir StudentParentLink.legal_guardian, RefLegalGuardian : codes SIECLE RESP_LEGAL
        "1"/"2"/"0"=Autre).
        """
        def rank(link: "StudentParentLink") -> int:
            code = link.legal_guardian.code if link.legal_guardian else None
            return {"1": 0, "2": 1}.get(code, 2)
        for link in sorted(self.parent_links, key=rank):
            if link.parent and link.parent.address_city_id:
                return link.parent.address_city_id
        return None


class StudentSpecialtyChoice(Base):
    """
    Enseignement électif d'un élève : matière (`subject_id`) classée par rang de préférence, avec
    sa modalité d'élection (SIECLE `OPTIONS_ELEVE` : NUM_OPTION -> rank, CODE_MATIERE -> subject_id,
    CODE_MODALITE_ELECT -> election_method_id). Ne porte PAS que les spécialités de la réforme du
    lycée malgré son nom — historique, gardé pour ne pas renommer une table déjà en usage — mais
    aussi bien une LV2 de collège qu'une option facultative : SIECLE élit des options à tous les
    niveaux, pas seulement en série générale de lycée.

    Le plafond de rangs (RefGrade.specialty_choice_limit, via Mef.ref_grade) ne s'applique donc
    qu'aux matières RÉELLEMENT marquées Subject.is_specialty=True (voir
    _check_specialty_count_within_grade_limit) : une LV2 ou une option facultative ne consomme pas
    ce quota.
    """
    __tablename__ = "student_specialty_choices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, info={"label": "Élève"})
    subject_id: Mapped[int] = mapped_column(Integer, ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, info={"label": "Matière"})
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=1, info={"label": "Rang", "min": 1, "max": 10})
    election_method_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_election_methods.id", ondelete="SET NULL"), nullable=True, info={"label": "Modalité d'élection"})

    student: Mapped["Student"] = relationship("Student", back_populates="specialty_choices")
    subject: Mapped["Subject"] = relationship("Subject")
    election_method: Mapped[Optional["RefElectionMethod"]] = relationship("RefElectionMethod")

    @constrains()
    def _check_specialty_count_within_grade_limit(self, db: Session):
        from backend.app.models.subject import Subject
        subject = db.get(Subject, self.subject_id)
        if not subject or not subject.is_specialty:
            return  # pas une matière de spécialité : aucun plafond à vérifier
        limit = self.student.mef.ref_grade.specialty_choice_limit if self.student and self.student.mef and self.student.mef.ref_grade else None
        if not limit:
            raise ValueError("Le niveau de cet élève n'est pas configuré pour les enseignements de spécialité (RefGrade.specialty_choice_limit non défini).")
        count = db.query(StudentSpecialtyChoice).join(Subject).filter(
            StudentSpecialtyChoice.student_id == self.student_id,
            Subject.is_specialty.is_(True),
            StudentSpecialtyChoice.id != (self.id or 0),
        ).count() + 1
        if count > limit:
            raise ValueError(f"L'élève a déjà {limit} vœu(x) de spécialité, le plafond pour son niveau.")

    @constrains()
    def _check_unique_student_subject(self, db: Session):
        duplicate = db.query(StudentSpecialtyChoice).filter(
            StudentSpecialtyChoice.student_id == self.student_id,
            StudentSpecialtyChoice.subject_id == self.subject_id,
            StudentSpecialtyChoice.id != self.id,
        ).first()
        if duplicate:
            raise ValueError("Cet élève a déjà un vœu pour cette spécialité.")


class StudentAccompanimentProject(Base):
    """
    Dispositif d'accompagnement personnalisé d'un élève (PPRE, PAP, PPS, PAI, ULIS...) — utilisé
    comme critère de répartition par le wizard d'affectation aux classes (Pré-rentrée), au même
    titre que les scores d'assiduité/résultats/comportement. Un élève suivi par plusieurs
    dispositifs à la fois est représenté par plusieurs lignes, pas par un champ multi-valué —
    même logique que StudentSpecialtyChoice ci-dessus.
    """
    __tablename__ = "student_accompaniment_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, info={"label": "Élève"})
    project_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("ref_accompaniment_project_types.id", ondelete="RESTRICT"), nullable=False, info={"label": "Dispositif"})
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date de début"})
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date de fin"})
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, info={"label": "Notes"})

    student: Mapped["Student"] = relationship("Student", back_populates="accompaniment_projects")
    project_type: Mapped["RefAccompanimentProjectType"] = relationship("RefAccompanimentProjectType")

    @constrains()
    def _check_end_date_after_start_date(self, db: Session):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("La date de fin doit être postérieure ou égale à la date de début.")


class StudentParentLink(Base):
    """
    Rattachement d'un responsable (`Parent`) à un élève (SIECLE `RESPONSABLES/RESPONSABLE`),
    remplace les anciens `Student.parent1_id`/`parent2_id` — plafonnés à deux responsables sans
    distinction de rôle au-delà de l'ordre. Un élève peut désormais avoir un nombre quelconque de
    responsables (parents séparés, tuteur tiers, assistante familiale...), chacun avec son propre
    lien de parenté et ses propres droits.
    """
    __tablename__ = "student_parent_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, info={"label": "Élève"})
    parent_id: Mapped[int] = mapped_column(Integer, ForeignKey("parents.id", ondelete="CASCADE"), nullable=False, info={"label": "Responsable"})
    # SIECLE CODE_PARENTE : nomenclature non fermée, complétée dynamiquement à l'import.
    relative_link_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_relative_links.id", ondelete="SET NULL"), nullable=True, info={"label": "Lien de parenté"})
    # SIECLE RESP_LEGAL : 0=Autre, 1=Responsable légal 1, 2=Responsable légal 2 (nomenclature seedée).
    legal_guardian_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ref_legal_guardians.id", ondelete="SET NULL"), nullable=True, info={"label": "Responsabilité légale"})
    # SIECLE NIVEAU_RESPONSABILITE : domaine non établi (voir FORMATS_JUSTIFICATION.md côté GEPI),
    # conservé en texte libre plutôt que forcé dans une énumération inventée.
    responsibility_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, info={"label": "Niveau de responsabilité"})
    pays_school_fees: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Paie les frais scolaires"})
    is_financially_responsible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Responsable financier"})
    receives_financial_aid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Perçoit les aides financières"})
    is_contact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false(), info={"label": "Contact"})

    student: Mapped["Student"] = relationship("Student", back_populates="parent_links")
    parent: Mapped["Parent"] = relationship("Parent", back_populates="student_links")
    relative_link: Mapped[Optional["RefRelativeLink"]] = relationship("RefRelativeLink")
    legal_guardian: Mapped[Optional["RefLegalGuardian"]] = relationship("RefLegalGuardian")

    @constrains()
    def _check_unique_student_parent(self, db: Session):
        duplicate = db.query(StudentParentLink).filter(
            StudentParentLink.student_id == self.student_id,
            StudentParentLink.parent_id == self.parent_id,
            StudentParentLink.id != (self.id or 0),
        ).first()
        if duplicate:
            raise ValueError("Ce responsable est déjà rattaché à cet élève.")


class StudentClassPartLink(Base):
    """
    Rattachement d'un élève à une partie de classe (`ClassPart`), avec sa période d'appartenance —
    remplace l'ancienne table de jointure `student_class_parts` (Many-to-Many sans date), qui ne
    pouvait représenter qu'un état courant, jamais un historique.

    Un élève peut quitter une partie de classe puis y revenir plus tard (ex. suspension d'option
    un trimestre, retour ensuite) : plusieurs lignes pour le MÊME couple (student_id, class_part_id)
    sont donc légitimes, tant que leurs `begin_date` diffèrent — d'où l'unicité sur le triplet
    (class_part_id, student_id, begin_date) plutôt que sur le seul couple. `end_date` est NULL tant
    que le rattachement est en cours ; c'est ce NULL qui définit l'appartenance ACTUELLE (voir
    Student.class_parts, viewonly filtré sur ce critère), pas la présence de la ligne elle-même.
    """
    __tablename__ = "student_class_part_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    class_part_id: Mapped[int] = mapped_column(Integer, ForeignKey("class_parts.id", ondelete="CASCADE"), nullable=False, info={"label": "Partie de classe"})
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, info={"label": "Élève"})
    begin_date: Mapped[date] = mapped_column(Date, nullable=False, info={"label": "Date de début"})
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, info={"label": "Date de fin"})

    class_part: Mapped["ClassPart"] = relationship("ClassPart", back_populates="student_links")
    student: Mapped["Student"] = relationship("Student", back_populates="class_part_links")

    @constrains()
    def _check_exit_date_after_begin_date(self, db: Session):
        if self.end_date and self.end_date < self.begin_date:
            raise ValueError("La date de fin doit être postérieure ou égale à la date de début.")

    @constrains()
    def _check_unique_triplet(self, db: Session):
        """Unicité (class_part_id, student_id, begin_date) — vérifiée en Python plutôt que par une
        contrainte SQL pour produire un message exploitable (même patron que
        StudentParentLink._check_unique_student_parent), pas une IntegrityError brute."""
        duplicate = db.query(StudentClassPartLink).filter(
            StudentClassPartLink.class_part_id == self.class_part_id,
            StudentClassPartLink.student_id == self.student_id,
            StudentClassPartLink.begin_date == self.begin_date,
            StudentClassPartLink.id != (self.id or 0),
        ).first()
        if duplicate:
            raise ValueError(
                "Cet élève a déjà un rattachement à cette partie de classe commençant à la même date."
            )

    @constrains("class_part_id", "student_id", "end_date")
    def _check_no_two_open_links(self, db: Session):
        """Au plus UN rattachement ouvert (end_date NULL) à la fois pour un même couple élève /
        partie de classe — sans quoi « appartenance actuelle » (end_date IS NULL) cesserait de
        désigner une période unique, et Student.class_parts pourrait lister deux fois la même
        partie de classe."""
        if self.end_date is not None:
            return
        duplicate = db.query(StudentClassPartLink).filter(
            StudentClassPartLink.class_part_id == self.class_part_id,
            StudentClassPartLink.student_id == self.student_id,
            StudentClassPartLink.end_date.is_(None),
            StudentClassPartLink.id != (self.id or 0),
        ).first()
        if duplicate:
            raise ValueError(
                "Cet élève a déjà un rattachement ouvert (sans date de fin) à cette partie de "
                "classe — clôturez-le (renseignez sa date de fin) avant d'en ouvrir un nouveau."
            )

    @constrains("class_part_id", "student_id", "end_date")
    def _check_coherence_when_active(self, db: Session):
        """
        Cohérence entre l'élève et sa partie de classe — vérifiée UNIQUEMENT quand CE lien est
        actif (end_date NULL) : c'est le seul état qui doit rester cohérent, un lien clos est de
        l'historique et peut légitimement référencer une division que l'élève a quittée depuis (ce
        modèle ne date pas les changements de Student.division_id lui-même). Portée ici, sur
        StudentClassPartLink, et non sur Student : c'est la création/modification d'un LIEN qui
        doit être bloquée, pas celle de l'élève — lui n'est pour rien dans cette écriture-ci.
        """
        if self.end_date is not None:
            return
        from backend.app.models.group import ClassPart
        student = self.student or db.get(Student, self.student_id)
        class_part = self.class_part or db.get(ClassPart, self.class_part_id)
        if not (student and class_part):
            return

        if class_part.division_id != student.division_id:
            raise ValueError(
                f"L'élève {student.first_name} {student.last_name} ne peut pas appartenir à la "
                f"partie de classe {class_part.name} car elle depend d'une autre division."
            )

        autres_actifs = db.query(StudentClassPartLink).filter(
            StudentClassPartLink.student_id == self.student_id,
            StudentClassPartLink.end_date.is_(None),
            StudentClassPartLink.id != (self.id or 0),
        ).all()
        for autre in autres_actifs:
            autre_part = autre.class_part or db.get(ClassPart, autre.class_part_id)
            if autre_part and autre_part.partition_id == class_part.partition_id:
                raise ValueError(
                    f"L'élève {student.first_name} {student.last_name} ne peut pas appartenir à "
                    f"deux parties de la même partition."
                )
