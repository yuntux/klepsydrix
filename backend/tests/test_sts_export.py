"""
Tests de l'audit et de la génération du flux STS montant (lot D).

L'audit est la vraie fonctionnalité : le fichier, lui, est partiel par construction (trois des
quatre familles de données de STS-web ont des balises inconnues).
"""
import base64
import datetime
import pytest
from sqlalchemy.orm import sessionmaker
from xml.etree import ElementTree as ET

from backend.app.models.base import Base
from backend.app.models import (
    School, SystemSetting, Discipline, Subject, Mef, Division, Teacher, Modality,
    Holidays, WeekCalendar, Alternation, Timeslot, Course, Group, Partition, ClassPart,
    RefElectionMethod, RefWeightingCoefficient,
)
from backend.app.models.mef import MefDivision
from backend.app.models.teacher import TeacherDiscipline
from backend.app.models.week_calendar import generate_week_calendar
from backend.app.core import sts_audit
from backend.app.core.sts_export import (
    StsExportError, build_emp_sts, export_filename, validate_against_schema,
)
from backend.app.models.wizard_sts_export import WizardStsExport
from backend.tests.db_test_utils import make_test_engine

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def _seed_compliant(db, model, **vals):
    """
    Insère une ligne de référence CONFORME (`is_sts_compliant=True`) en contournant
    StsComplianceMixin — exactement comme le fait le seed brut de init_db.py (un INSERT qui ne
    passe pas par create(), voir receive_before_insert). L'API refuse explicitement ce booléen à
    la création (voir StsComplianceMixin.create) : c'est le seul moyen de l'atteindre en test.
    """
    instance = model(**vals, is_sts_compliant=True)
    instance._via_crud_mixin_create = True
    db.add(instance)
    db.flush()
    return instance


def _weighting_id(db, value):
    """
    Id de la ligne de référence portant cette valeur, créée au besoin — NON conforme par défaut
    (`RefWeightingCoefficient.create`, l'API ordinaire), à la différence des six valeurs seedées
    par la fixture ci-dessous. Utiliser `_seed_compliant` directement quand un test a précisément
    besoin d'une valeur conforme inédite.
    """
    existing = db.query(RefWeightingCoefficient).filter(RefWeightingCoefficient.weighting_coefficient == value).first()
    return existing.id if existing else RefWeightingCoefficient.create(db, {"weighting_coefficient": value}).id


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        SystemSetting.create(db, {"key": "STANDARD_TIMESLOT_DURATION", "value": "30"})
        SystemSetting.create(db, {"key": "SCHOOL_YEAR", "value": "2026"})
        # CG (id=1) et 1.00/0.25/0.5/0.75/1.25/1.5 : mêmes valeurs, même ORDRE (donc mêmes id) que
        # le seed réel de init_db.py — pour que les défauts de Course (modality_id=1,
        # weighting_coefficient_id=1) tombent sur des lignes CONFORMES.
        _seed_compliant(db, Modality, code="CG", name="COURS", long_name="COURS GENERAL")
        for valeur in (1.00, 0.25, 0.5, 0.75, 1.25, 1.5):
            _seed_compliant(db, RefWeightingCoefficient, weighting_coefficient=valeur)
        School.create(db, {
            "uai": "0750001A", "name": "Collège",
            "student_start_date": datetime.date(2026, 9, 2),
            "student_end_date": datetime.date(2027, 7, 4),
        })
        generate_week_calendar(db)
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _contexte(db, **overrides):
    """Un cours complet et sain : classe rattachée à un MEF, matière codée, prof EPP, créneau."""
    school = db.query(School).first()
    discipline = Discipline.create(db, {"code": "L0100", "name": "Maths"})
    subject = Subject.create(db, {
        "code": "MATHS", "code_nomenclature": "006600", "short_name": "Maths",
        "name": "Mathématiques", "discipline_id": discipline.id,
    })
    from backend.app.models.ref_grade import RefGrade
    grade = RefGrade.create(db, {"name": "6EME"})
    mef = Mef.create(db, {"school_id": school.id, "code_national": "10010012110", "name": "6EME", "ref_grade_id": grade.id})
    division = Division.create(db, {"school_id": school.id, "code": "6A", "name": "6ème A", "student_count": 25})
    MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id})
    teacher = Teacher.create(db, {"code": "T1", "last_name": "DURAND", "school_id": school.id, "epp_id": "8949"})
    TeacherDiscipline.create(db, {"teacher_id": teacher.id, "discipline_id": discipline.id})
    timeslot = Timeslot.create(db, {"day_of_week": 1, "minutes_from_midnight": 480})
    vals = {
        "school_id": school.id, "subject_id": subject.id, "duration_minutes": 60,
        "week_type": "W", "timeslot_id": timeslot.id,
        "teacher_ids": [teacher.id], "division_ids": [division.id],
    }
    vals.update(overrides)
    course = Course.create(db, vals)
    return {"school": school, "subject": subject, "division": division, "teacher": teacher, "course": course, "mef": mef}


def _groupe(db, division, subject, name="6GALL"):
    """Groupe rattaché à une division par une partie de classe — le seul chemin dont dispose le
    modèle pour dire à quelle division un groupe emprunte ses élèves."""
    partition = Partition.create(db, {
        "code": f"{division.code}-LV", "name": "Langues", "division_id": division.id,
    })
    partie = ClassPart.create(db, {
        "partition_id": partition.id, "name": "Allemand", "subject_id": subject.id,
        "student_count": 12,
    })
    return Group.create(db, {
        "name": name, "long_name": "6ème Allemand LV1", "student_count": 12,
        "class_part_ids": [partie.id],
    })


def _codes(anomalies):
    return {a["code"] for a in anomalies}


class TestAuditBloquant:
    def test_base_saine_sans_anomalie(self, db_session):
        ctx = _contexte(db_session)
        assert sts_audit.audit(db_session, ctx["school"]) == []

    def test_cours_non_place(self, db_session):
        ctx = _contexte(db_session, timeslot_id=None)
        anomalies = sts_audit.audit(db_session, ctx["school"])
        assert "COURSE_NOT_PLACED" in _codes(anomalies)
        assert sts_audit.has_blocking(anomalies)

    def test_cours_sans_public(self, db_session):
        ctx = _contexte(db_session)
        ctx["course"].update(db_session, {"division_ids": []})
        assert "COURSE_NO_AUDIENCE" in _codes(sts_audit.audit(db_session, ctx["school"]))

    def test_enseignant_sans_epp(self, db_session):
        ctx = _contexte(db_session)
        ctx["teacher"].update(db_session, {"epp_id": None})
        assert "TEACHER_NO_EPP" in _codes(sts_audit.audit(db_session, ctx["school"]))

    def test_co_enseignement_non_declare(self, db_session):
        ctx = _contexte(db_session)
        autre = Teacher.create(db_session, {"code": "T2", "last_name": "PETIT", "school_id": ctx["school"].id, "epp_id": "8950"})
        TeacherDiscipline.create(db_session, {"teacher_id": autre.id, "discipline_id": db_session.query(Discipline).first().id})
        ctx["course"].update(db_session, {"teacher_ids": [ctx["teacher"].id, autre.id]})
        assert "CO_TEACHING_NOT_DECLARED" in _codes(sts_audit.audit(db_session, ctx["school"]))

    def test_classe_sans_mef(self, db_session):
        ctx = _contexte(db_session)
        Division.create(db_session, {"school_id": ctx["school"].id, "code": "6Z", "name": "Orpheline"})
        assert "DIVISION_NO_MEF" in _codes(sts_audit.audit(db_session, ctx["school"]))

    def test_calendrier_des_semaines_vide(self, db_session):
        """Sans calendrier, chaque cours partirait avec un SEMAINES vide — accepté par la
        validation, et faux."""
        ctx = _contexte(db_session)
        for semaine in db_session.query(WeekCalendar).all():
            semaine.delete(db_session)
        anomalies = sts_audit.audit(db_session, ctx["school"])
        assert "NO_WEEK_CALENDAR" in _codes(anomalies)
        assert sts_audit.has_blocking(anomalies)

    def test_alternance_ne_couvrant_aucune_semaine(self, db_session):
        """Une alternance restreinte à une période hors année scolaire ne couvre aucune semaine."""
        from backend.app.models import Period, PeriodType
        ctx = _contexte(db_session)
        type_id = PeriodType.create(db_session, {"name": "Trimestre"}).id
        periode = Period.create(db_session, {
            "period_type_id": type_id, "school_id": ctx["school"].id,
            "code": "T9", "name": "Hors année",
            "start_date": datetime.date(2030, 1, 1), "end_date": datetime.date(2030, 2, 1),
        })
        ctx["course"].update(db_session, {"period_type_id": type_id, "period_ids": [periode.id]})
        anomalies = sts_audit.audit(db_session, ctx["school"])
        assert "ALTERNATION_NO_WEEK" in _codes(anomalies)

    def test_une_quinzaine_non_tranchee_ne_peut_pas_etre_placee(self, db_session):
        """Le modèle interdit déjà de placer un cours en Q : l'audit n'a donc pas à guetter
        l'absence d'alternance sur un cours placé, ce cas n'existe pas."""
        with pytest.raises(ValueError, match="quinzaine"):
            _contexte(db_session, week_type="Q")


class TestExclusionsTroisNiveaux:
    def test_exclusion_par_la_matiere(self, db_session):
        ctx = _contexte(db_session)
        ctx["subject"].update(db_session, {"is_excluded_from_sts": True})
        assert ctx["course"].is_exported_to_sts is False

    def test_exclusion_par_la_classe(self, db_session):
        ctx = _contexte(db_session)
        ctx["division"].update(db_session, {"is_excluded_from_sts": True})
        assert ctx["course"].is_exported_to_sts is False

    def test_exclusion_par_le_cours(self, db_session):
        ctx = _contexte(db_session)
        ctx["course"].update(db_session, {"is_excluded_from_sts": True})
        assert ctx["course"].is_exported_to_sts is False

    def test_ponderation_nulle_vaut_exclusion(self, db_session):
        """STS-web ignore les cours de pondération 0 : autant le dire avant plutôt que de laisser
        le cours disparaître en silence à l'arrivée."""
        ctx = _contexte(db_session)
        zero_id = _weighting_id(db_session, 0)
        ctx["course"].update(db_session, {"weighting_coefficient_id": zero_id})
        assert ctx["course"].is_exported_to_sts is False

    def test_un_cours_exclu_n_est_ni_audite_ni_exporte(self, db_session):
        ctx = _contexte(db_session, timeslot_id=None)
        ctx["course"].update(db_session, {"is_excluded_from_sts": True})
        assert sts_audit.audit(db_session, ctx["school"]) == []
        assert "<COURS>" not in build_emp_sts(db_session, ctx["school"])


class TestPonderationParIntervenant:
    def test_repli_sur_la_ponderation_du_cours(self, db_session):
        ctx = _contexte(db_session)
        id_1_25 = _weighting_id(db_session, 1.25)
        ctx["course"].update(db_session, {"weighting_coefficient_id": id_1_25})
        assert ctx["course"].weighting_for(ctx["teacher"].id) == 1.25
        assert ctx["course"].has_heterogeneous_weighting is False

    def test_exception_par_intervenant(self, db_session):
        from backend.app.models.course_teacher import CourseTeacherWeighting
        ctx = _contexte(db_session)
        id_1_25 = _weighting_id(db_session, 1.25)
        autre = Teacher.create(db_session, {"code": "T2", "last_name": "PETIT", "school_id": ctx["school"].id, "epp_id": "8950"})
        TeacherDiscipline.create(db_session, {"teacher_id": autre.id, "discipline_id": db_session.query(Discipline).first().id})
        ctx["course"].update(db_session, {"teacher_ids": [ctx["teacher"].id, autre.id], "is_co_teaching": True})
        CourseTeacherWeighting.create(db_session, {
            "course_id": ctx["course"].id, "teacher_id": autre.id, "weighting_coefficient_id": id_1_25,
        })
        assert ctx["course"].weighting_for(autre.id) == 1.25
        assert ctx["course"].weighting_for(ctx["teacher"].id) == 1.0
        assert ctx["course"].has_heterogeneous_weighting is True

    def test_heterogeneite_signalee_en_avertissement(self, db_session):
        from backend.app.models.course_teacher import CourseTeacherWeighting
        ctx = _contexte(db_session)
        id_1_25 = _weighting_id(db_session, 1.25)
        autre = Teacher.create(db_session, {"code": "T2", "last_name": "PETIT", "school_id": ctx["school"].id, "epp_id": "8950"})
        TeacherDiscipline.create(db_session, {"teacher_id": autre.id, "discipline_id": db_session.query(Discipline).first().id})
        ctx["course"].update(db_session, {"teacher_ids": [ctx["teacher"].id, autre.id], "is_co_teaching": True})
        CourseTeacherWeighting.create(db_session, {
            "course_id": ctx["course"].id, "teacher_id": autre.id, "weighting_coefficient_id": id_1_25,
        })
        anomalies = sts_audit.audit(db_session, ctx["school"])
        heterogene = [a for a in anomalies if a["code"] == "HETEROGENEOUS_WEIGHTING"]
        assert heterogene and heterogene[0]["severity"] == sts_audit.WARNING
        assert not sts_audit.has_blocking(anomalies)

    def test_ponderer_un_enseignant_absent_du_cours_refuse(self, db_session):
        from backend.app.models.course_teacher import CourseTeacherWeighting
        ctx = _contexte(db_session)
        id_1_25 = _weighting_id(db_session, 1.25)
        etranger = Teacher.create(db_session, {"code": "T9", "last_name": "AILLEURS", "school_id": ctx["school"].id})
        TeacherDiscipline.create(db_session, {"teacher_id": etranger.id, "discipline_id": db_session.query(Discipline).first().id})
        with pytest.raises(ValueError, match="n'intervient pas sur ce cours"):
            CourseTeacherWeighting.create(db_session, {
                "course_id": ctx["course"].id, "teacher_id": etranger.id, "weighting_coefficient_id": id_1_25,
            })


class TestGenerationDuFichier:
    def test_racine_et_structure(self, db_session):
        ctx = _contexte(db_session)
        racine = ET.fromstring(build_emp_sts(db_session, ctx["school"]))
        assert racine.tag == "EDT_STS"
        division = racine.find("DONNEES/STRUCTURE/DIVISIONS/DIVISION")
        assert division.get("CODE") == "6A"
        # L'ordre est celui du fichier descendant, et le schéma l'impose.
        assert [enfant.tag for enfant in division] == ["SERVICES", "MEFS_APPARTENANCE"]
        assert division.find("MEFS_APPARTENANCE/MEF").get("CODE") == "10010012110"

    def test_service_enseignant_et_seance(self, db_session):
        ctx = _contexte(db_session)
        racine = ET.fromstring(build_emp_sts(db_session, ctx["school"]))
        service = racine.find(".//SERVICE")
        assert service.get("CODE_MATIERE") == "006600"
        assert service.get("CODE_MOD_COURS") == "CG"
        enseignant = service.find("ENSEIGNANTS/ENSEIGNANT")
        assert enseignant.get("ID") == "8949"
        assert enseignant.get("TYPE") == "epp"
        cours = enseignant.find("COURS_RATTACHES/COURS")
        assert cours.findtext("JOUR") == "1"
        assert cours.findtext("HEURE_DEBUT") == "0800"
        assert cours.findtext("DUREE") == "0100"
        assert cours.findtext("CODE_ALTERNANCE") == "W"

    def test_les_alternances_employees_portent_leurs_semaines(self, db_session):
        ctx = _contexte(db_session)
        racine = ET.fromstring(build_emp_sts(db_session, ctx["school"]))
        alternances = racine.findall("ALTERNANCES/ALTERNANCE")
        assert len(alternances) == 1, "seules les alternances employees sont ecrites"
        semaines = alternances[0].findall("SEMAINES/DATE_DEBUT_SEMAINE")
        assert len(semaines) == db_session.query(WeekCalendar).count()

    def test_type_local_pour_un_enseignant_non_epp(self, db_session):
        ctx = _contexte(db_session)
        ctx["teacher"].update(db_session, {"is_epp": False})
        racine = ET.fromstring(build_emp_sts(db_session, ctx["school"]))
        assert racine.find(".//ENSEIGNANT").get("TYPE") == "local"

    def test_nom_de_fichier(self, db_session):
        assert export_filename(db_session.query(School).first(), 2026) == "emp_sts_0750001A_2026.xml"

    def test_un_groupe_porte_ses_divisions_d_appartenance(self, db_session):
        ctx = _contexte(db_session)
        groupe = _groupe(db_session, ctx["division"], ctx["subject"])
        ctx["course"].update(db_session, {"division_ids": [], "group_ids": [groupe.id]})
        racine = ET.fromstring(build_emp_sts(db_session, ctx["school"]))
        element = racine.find("DONNEES/STRUCTURE/GROUPES/GROUPE")
        assert element.get("CODE") == "6GALL"
        assert [e.tag for e in element] == ["LIBELLE_LONG", "DIVISIONS_APPARTENANCE", "SERVICES"]
        assert element.findtext("LIBELLE_LONG") == "6ème Allemand LV1"
        assert element.find("DIVISIONS_APPARTENANCE/DIVISION_APPARTENANCE").get("CODE") == "6A"
        # Un cours de groupe ne se range pas AUSSI sous sa division : ce serait le compter deux fois.
        assert racine.find("DONNEES/STRUCTURE/DIVISIONS") is None

    def test_un_enseignant_sans_epp_n_est_pas_ecrit(self, db_session):
        """L'audit le refuse déjà ; l'export ne doit pas non plus écrire un ID vide, que le schéma
        rejetterait. Ne restant aucun enseignant, la structure entière disparaît."""
        ctx = _contexte(db_session)
        ctx["teacher"].update(db_session, {"epp_id": None})
        racine = ET.fromstring(build_emp_sts(db_session, ctx["school"]))
        assert racine.find(".//ENSEIGNANT") is None
        assert racine.find("DONNEES/STRUCTURE/DIVISIONS") is None


class TestValidationParLeSchema:
    """Le document est soumis au XSD reconstitué avant d'être rendu : dernier filet de sécurité."""

    def test_un_document_conforme_passe(self, db_session):
        ctx = _contexte(db_session)
        contenu = build_emp_sts(db_session, ctx["school"])
        validate_against_schema(contenu)  # ne lève pas

    def test_un_export_vide_reste_conforme(self, db_session):
        """Base sans aucun cours : DONNEES/STRUCTURE reste obligatoire, mais vide."""
        school = db_session.query(School).first()
        racine = ET.fromstring(build_emp_sts(db_session, school))
        assert racine.find("DONNEES/STRUCTURE") is not None
        assert racine.find("ALTERNANCES") is None

    def test_un_document_non_conforme_est_refuse(self, db_session):
        with pytest.raises(StsExportError, match="ne respecte pas le schéma"):
            validate_against_schema('<?xml version="1.0" encoding="UTF-8"?><EDT_STS/>')

    def test_l_echappement_est_assure_par_l_arbre(self, db_session):
        """Un libellé contenant & ou < ne doit pas casser le document — c'est précisément ce que la
        construction par arbre garantit et que la concaténation de chaînes ne garantissait pas."""
        ctx = _contexte(db_session)
        alternance = ctx["course"].alternation
        alternance.update(db_session, {"name": "Semaines A & B <toutes>"})
        racine = ET.fromstring(build_emp_sts(db_session, ctx["school"]))
        assert racine.findtext("ALTERNANCES/ALTERNANCE/LIBELLE_LONG") == "Semaines A & B <toutes>"


class TestQuinzaineNonTranchee:
    """Un cours en Q n'engendre pas d'alternance, ne peut pas s'y rattacher, et ne part pas."""

    def test_pas_d_alternance(self, db_session):
        ctx = _contexte(db_session, week_type="Q", timeslot_id=None)
        assert ctx["course"].alternation_id is None

    def test_rattachement_impossible(self, db_session):
        """Écrire alternation_id ne le fixe pas : le champ est calculé et stocké, l'écriture
        relance le calcul qui l'écrase."""
        ctx = _contexte(db_session, week_type="Q", timeslot_id=None)
        alternance = Alternation.search_or_create(db_session, "W", [])
        ctx["course"].update(db_session, {"alternation_id": alternance.id})
        assert ctx["course"].alternation_id is None

    def test_non_exporte(self, db_session):
        ctx = _contexte(db_session, week_type="Q", timeslot_id=None)
        assert ctx["course"].is_in_sts_scope is True
        assert ctx["course"].is_exported_to_sts is False
        assert "<COURS>" not in build_emp_sts(db_session, ctx["school"])

    def test_signale_bloquant_plutot_qu_ecarte_en_silence(self, db_session):
        """Écarté de l'export, le cours l'est aussi de tous les autres contrôles : sans cette
        ligne d'audit, il quitterait la remontée sans que rien ne le dise."""
        ctx = _contexte(db_session, week_type="Q", timeslot_id=None)
        anomalies = sts_audit.audit(db_session, ctx["school"])
        assert "COURSE_UNDECIDED_FORTNIGHT" in _codes(anomalies)
        assert sts_audit.has_blocking(anomalies)

    def test_un_cours_q_exclu_ne_dit_plus_rien(self, db_session):
        ctx = _contexte(db_session, week_type="Q", timeslot_id=None)
        ctx["course"].update(db_session, {"is_excluded_from_sts": True})
        assert sts_audit.audit(db_session, ctx["school"]) == []


class TestAuditFormatsAttendus:
    def test_epp_non_numerique(self, db_session):
        ctx = _contexte(db_session)
        ctx["teacher"].update(db_session, {"epp_id": "AB12"})
        anomalies = [a for a in sts_audit.audit(db_session, ctx["school"]) if a["code"] == "TEACHER_NO_EPP"]
        assert anomalies and "n'est pas numérique" in anomalies[0]["message"]

    def test_code_matiere_mal_forme(self, db_session):
        ctx = _contexte(db_session)
        ctx["subject"].update(db_session, {"code_nomenclature": "66"})
        assert "SUBJECT_NO_NATIONAL_CODE" in _codes(sts_audit.audit(db_session, ctx["school"]))

    def test_groupe_sans_division_d_appartenance(self, db_session):
        ctx = _contexte(db_session)
        groupe = Group.create(db_session, {"name": "6GORPH", "student_count": 12})
        ctx["course"].update(db_session, {"division_ids": [], "group_ids": [groupe.id]})
        assert "GROUP_NO_DIVISION" in _codes(sts_audit.audit(db_session, ctx["school"]))


class TestWizard:
    def _wizard(self):
        return WizardStsExport(id=1)

    def test_avertissement_experimental(self, db_session):
        html = WizardStsExport.read(db_session)[0].info_html
        assert "expérimental" in html.lower()
        assert "partiel par construction" in html

    def test_etablissement_obligatoire(self, db_session):
        with pytest.raises(ValueError, match="Choisissez l'établissement"):
            self._wizard().rpc_audit(db_session)

    def test_audit_puis_export(self, db_session):
        ctx = _contexte(db_session)
        res = self._wizard().rpc_audit(db_session, school_id=ctx["school"].id)
        assert res["anomaly_rows"] == []
        assert "aucune anomalie" in res["audit_html"]
        res = self._wizard().rpc_export(db_session, school_id=ctx["school"].id)
        contenu = base64.b64decode(res["export_file"]["data_base64"]).decode("utf-8")
        assert res["export_file"]["filename"] == "emp_sts_0750001A_2026.xml"
        assert ET.fromstring(contenu).tag == "EDT_STS"
        assert "répondez NON" in res["result_html"]

    def test_une_anomalie_bloquante_interdit_la_generation(self, db_session):
        ctx = _contexte(db_session, timeslot_id=None)
        with pytest.raises(ValueError, match="bloquante"):
            self._wizard().rpc_export(db_session, school_id=ctx["school"].id)

    def test_un_avertissement_laisse_passer(self, db_session):
        from backend.app.models.course_teacher import CourseTeacherWeighting
        ctx = _contexte(db_session)
        id_1_25 = _weighting_id(db_session, 1.25)
        autre = Teacher.create(db_session, {"code": "T2", "last_name": "PETIT", "school_id": ctx["school"].id, "epp_id": "8950"})
        TeacherDiscipline.create(db_session, {"teacher_id": autre.id, "discipline_id": db_session.query(Discipline).first().id})
        ctx["course"].update(db_session, {"teacher_ids": [ctx["teacher"].id, autre.id], "is_co_teaching": True})
        CourseTeacherWeighting.create(db_session, {
            "course_id": ctx["course"].id, "teacher_id": autre.id, "weighting_coefficient_id": id_1_25,
        })
        res = self._wizard().rpc_export(db_session, school_id=ctx["school"].id)
        assert res["export_file"]["data_base64"]
        assert "avertissement" in res["result_html"]

    def test_l_audit_est_rejoue_a_l_export(self, db_session):
        """Entre l'audit et la génération, l'utilisateur a pu corriger — ou aggraver."""
        ctx = _contexte(db_session)
        self._wizard().rpc_audit(db_session, school_id=ctx["school"].id)
        ctx["course"].update(db_session, {"timeslot_id": None})
        with pytest.raises(ValueError, match="bloquante"):
            self._wizard().rpc_export(db_session, school_id=ctx["school"].id)


class TestStsComplianceMixin:
    """
    `is_sts_compliant` — partagé par Modality, RefElectionMethod et RefWeightingCoefficient — ne
    doit jamais être atteignable via l'API, ni à la création ni en modification, et une ligne
    conforme ne doit jamais pouvoir être supprimée. Testé une seule fois sur Modality : les trois
    modèles partagent le même mixin, sans logique propre à chacun.
    """

    def test_creation_refuse_is_sts_compliant_a_vrai(self, db_session):
        with pytest.raises(ValueError, match="is_sts_compliant ne peut pas être fixé"):
            Modality.create(db_session, {
                "code": "XX", "name": "X", "long_name": "X", "is_sts_compliant": True,
            })

    def test_creation_accepte_labsence_ou_le_faux(self, db_session):
        # Ni la clé absente, ni explicitement fausse, ne doivent être bloquées — seule une
        # tentative de la faire passer à vrai l'est.
        m1 = Modality.create(db_session, {"code": "X1", "name": "X1", "long_name": "X1"})
        m2 = Modality.create(db_session, {"code": "X2", "name": "X2", "long_name": "X2", "is_sts_compliant": False})
        assert m1.is_sts_compliant is False
        assert m2.is_sts_compliant is False

    def test_modification_refuse_un_changement_reel(self, db_session):
        modalite = Modality.create(db_session, {"code": "X3", "name": "X3", "long_name": "X3"})
        with pytest.raises(ValueError, match="jamais modifiable"):
            modalite.update(db_session, {"is_sts_compliant": True})

    def test_modification_accepte_une_valeur_identique(self, db_session):
        """
        Le piège que ce test verrouille : un formulaire réémet l'enregistrement complet à chaque
        sauvegarde, y compris les champs en lecture seule non touchés — bloquer TOUTE présence de
        la clé aurait rendu ces lignes de référence impossibles à modifier, ne serait-ce que pour
        renommer un libellé.
        """
        modalite = Modality.create(db_session, {"code": "X4", "name": "X4", "long_name": "X4"})
        modalite.update(db_session, {"name": "X4bis", "is_sts_compliant": False})
        assert modalite.name == "X4bis"
        assert modalite.is_sts_compliant is False

    def test_conforme_ne_peut_pas_etre_supprimee(self, db_session):
        conforme = _seed_compliant(db_session, Modality, code="X5", name="X5", long_name="X5")
        with pytest.raises(ValueError, match="nomenclature officielle STS-web"):
            conforme.delete(db_session)

    def test_non_conforme_reste_supprimable(self, db_session):
        modalite = Modality.create(db_session, {"code": "X6", "name": "X6", "long_name": "X6"})
        assert modalite.delete(db_session) is True


class TestNonConformiteNestPasUneExclusionVoulue:
    """
    Cœur de la correction demandée : un cours qui échoue sur un critère TECHNIQUE (pondération,
    modalité, mode d'élection) sans avoir été explicitement exclu par l'utilisateur doit être
    signalé par une anomalie BLOQUANTE — jamais disparaître de l'audit en silence, ce qui était le
    comportement antérieur pour la pondération nulle.
    """

    def test_is_in_sts_scope_ignore_desormais_la_ponderation(self, db_session):
        """is_in_sts_scope ne couvre plus que les trois exclusions délibérées : une pondération
        nulle n'en fait plus partie, contrairement à avant cette correction."""
        ctx = _contexte(db_session)
        zero_id = _weighting_id(db_session, 0)
        ctx["course"].update(db_session, {"weighting_coefficient_id": zero_id})
        assert ctx["course"].is_in_sts_scope is True
        assert ctx["course"].is_exported_to_sts is False

    def test_ponderation_nulle_non_exclue_est_bloquante(self, db_session):
        ctx = _contexte(db_session)
        zero_id = _weighting_id(db_session, 0)
        ctx["course"].update(db_session, {"weighting_coefficient_id": zero_id})
        anomalies = sts_audit.audit(db_session, ctx["school"])
        assert "COURSE_WEIGHTING_NOT_COMPLIANT" in _codes(anomalies)
        assert sts_audit.has_blocking(anomalies)

    def test_ponderation_nulle_mais_exclue_ne_dit_plus_rien(self, db_session):
        """Une exclusion VOULUE (is_excluded_from_sts) reste silencieuse — c'est tout l'intérêt de
        la distinguer d'un défaut technique non voulu."""
        ctx = _contexte(db_session)
        zero_id = _weighting_id(db_session, 0)
        ctx["course"].update(db_session, {"weighting_coefficient_id": zero_id, "is_excluded_from_sts": True})
        assert sts_audit.audit(db_session, ctx["school"]) == []

    def test_ponderation_hors_nomenclature_est_bloquante(self, db_session):
        ctx = _contexte(db_session)
        exotique_id = _weighting_id(db_session, 3.7)
        ctx["course"].update(db_session, {"weighting_coefficient_id": exotique_id})
        anomalies = sts_audit.audit(db_session, ctx["school"])
        fautif = [a for a in anomalies if a["code"] == "COURSE_WEIGHTING_NOT_COMPLIANT"]
        assert fautif and "3.7" in fautif[0]["message"]
        assert sts_audit.has_blocking(anomalies)

    def test_modalite_non_conforme_est_bloquante(self, db_session):
        ctx = _contexte(db_session)
        modalite = Modality.create(db_session, {"code": "TD", "name": "TD", "long_name": "TRAVAUX DIRIGES"})
        ctx["course"].update(db_session, {"modality_id": modalite.id})
        anomalies = sts_audit.audit(db_session, ctx["school"])
        fautif = [a for a in anomalies if a["code"] == "COURSE_MODALITY_NOT_COMPLIANT"]
        assert fautif and "TD" in fautif[0]["message"]
        assert sts_audit.has_blocking(anomalies)

    def test_modalite_conforme_ne_dit_rien(self, db_session):
        ctx = _contexte(db_session)
        modalite = _seed_compliant(db_session, Modality, code="TD", name="TD", long_name="TRAVAUX DIRIGES")
        ctx["course"].update(db_session, {"modality_id": modalite.id})
        assert "COURSE_MODALITY_NOT_COMPLIANT" not in _codes(sts_audit.audit(db_session, ctx["school"]))

    def test_mode_election_non_conforme_est_bloquant(self, db_session):
        ctx = _contexte(db_session)
        methode = RefElectionMethod.create(db_session, {"code": "S", "name": "TRONC COMM", "export_code": "TC"})
        ctx["course"].update(db_session, {"election_method_id": methode.id})
        anomalies = sts_audit.audit(db_session, ctx["school"])
        fautif = [a for a in anomalies if a["code"] == "COURSE_ELECTION_METHOD_NOT_COMPLIANT"]
        assert fautif and "S" in fautif[0]["message"]
        assert sts_audit.has_blocking(anomalies)

    def test_aucun_mode_election_ne_declenche_rien(self, db_session):
        """election_method_id est facultatif : un cours qui n'en porte aucun n'a rien à
        contrôler."""
        ctx = _contexte(db_session)
        assert ctx["course"].election_method_id is None
        assert "COURSE_ELECTION_METHOD_NOT_COMPLIANT" not in _codes(sts_audit.audit(db_session, ctx["school"]))

    def test_non_conformite_bloque_la_generation_du_fichier(self, db_session):
        ctx = _contexte(db_session)
        exotique_id = _weighting_id(db_session, 3.7)
        ctx["course"].update(db_session, {"weighting_coefficient_id": exotique_id})
        with pytest.raises(ValueError, match="bloquante"):
            WizardStsExport(id=1).rpc_export(db_session, school_id=ctx["school"].id)
