"""
Tests de l'export élèves/groupes vers SIECLE (backend/app/core/eleves_export.py et
backend/app/models/wizard_eleves_export.py).
"""
from datetime import date
import pytest
from sqlalchemy.orm import sessionmaker
from xml.etree import ElementTree as ET

from backend.app.models.base import Base
from backend.app.models import (
    School, Division, Mef, MefDivision, RefGrade, SystemSetting, Student,
)
from backend.app.models.group import Partition, ClassPart, Group
from backend.app.models.student import StudentClassPartLink
from backend.app.core.eleves_export import (
    build_import_eleves, export_filename, eligible_and_excluded_students, ElevesExportError,
    validate_against_schema,
)
from backend.app.models.wizard_eleves_export import WizardElevesExport
from backend.tests.db_test_utils import make_test_engine

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        SystemSetting.create(db, {"key": "STANDARD_TIMESLOT_DURATION", "value": "30"})
        SystemSetting.create(db, {"key": "SCHOOL_YEAR", "value": "2026"})
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _scaffold(db, with_end_date=True):
    school = School.create(db, {
        "uai": "0750001A", "name": "Collège Test",
        "student_start_date": date(2026, 9, 2),
        **({"student_end_date": date(2027, 7, 4)} if with_end_date else {}),
    })
    ref_grade = RefGrade.create(db, {"name": "6EME"})
    mef = Mef.create(db, {
        "school_id": school.id, "code_national": "MEF_TEST", "name": "MEF", "ref_grade_id": ref_grade.id,
        "max_students_per_class": 30, "forecast_student_count": 30,
    })
    division = Division.create(db, {"code": "6A", "name": "6ème A", "school_id": school.id})
    MefDivision.create(db, {"mef_id": mef.id, "division_id": division.id, "forecast_student_count": 30})
    partition = Partition.create(db, {"code": "6A-LV", "name": "Langues", "division_id": division.id})
    class_part = ClassPart.create(db, {"partition_id": partition.id, "name": "Allemand"})
    group = Group.create(db, {"name": "6LV1.ALL", "class_part_ids": [class_part.id]})
    return {"school": school, "division": division, "mef": mef, "class_part": class_part, "group": group}


def _make_student(db, ctx, **overrides):
    vals = {
        "first_name": "Jean", "last_name": "Martin", "division_id": ctx["division"].id, "mef_id": ctx["mef"].id,
        "siecle_id": "10001", "birth_date": date(2015, 4, 15),
    }
    vals.update(overrides)
    return Student.create(db, vals)


class TestEligibilite:
    def test_eleve_sans_siecle_id_exclu(self, db_session):
        ctx = _scaffold(db_session)
        _make_student(db_session, ctx, siecle_id=None)
        eligibles, exclus = eligible_and_excluded_students(db_session, ctx["school"])
        assert eligibles == []
        assert len(exclus) == 1
        assert "SIECLE" in exclus[0][1]

    def test_eleve_sans_date_naissance_exclu(self, db_session):
        ctx = _scaffold(db_session)
        _make_student(db_session, ctx, birth_date=None)
        eligibles, exclus = eligible_and_excluded_students(db_session, ctx["school"])
        assert eligibles == []
        assert "naissance" in exclus[0][1]

    def test_eleve_eligible_compte_ses_groupes_actifs(self, db_session):
        ctx = _scaffold(db_session)
        student = _make_student(db_session, ctx)
        StudentClassPartLink.create(db_session, {
            "student_id": student.id, "class_part_id": ctx["class_part"].id, "begin_date": date(2026, 9, 10),
        })
        eligibles, exclus = eligible_and_excluded_students(db_session, ctx["school"])
        assert exclus == []
        assert len(eligibles) == 1
        assert eligibles[0][1] == 1  # nombre de groupes


class TestBuildImportEleves:
    def test_bloque_si_date_de_sortie_absente(self, db_session):
        ctx = _scaffold(db_session, with_end_date=False)
        with pytest.raises(ElevesExportError, match="date de sortie"):
            build_import_eleves(db_session, ctx["school"], date(2026, 10, 1), 1)

    def test_fichier_valide_le_schema(self, db_session):
        ctx = _scaffold(db_session)
        student = _make_student(db_session, ctx)
        StudentClassPartLink.create(db_session, {
            "student_id": student.id, "class_part_id": ctx["class_part"].id, "begin_date": date(2026, 9, 10),
        })
        contenu = build_import_eleves(db_session, ctx["school"], date(2026, 10, 1), 42)
        validate_against_schema(contenu)  # ne lève pas

    def test_en_tete(self, db_session):
        ctx = _scaffold(db_session)
        contenu = build_import_eleves(db_session, ctx["school"], date(2026, 10, 1), 7)
        racine = ET.fromstring(contenu)
        assert racine.tag == "IMPORT_ELEVES"
        assert racine.get("VERSION") == "1.3"
        parametres = racine.find("PARAMETRES")
        assert parametres.find("UAJ").text == "0750001A"
        assert parametres.find("ANNEE_SCOLAIRE").text == "2026"
        assert parametres.find("DATE_IMPORT").text == "01/10/2026"
        assert parametres.find("NUM_ENVOI").text == "7"
        assert parametres.find("LOGICIEL").text == "KLEPSYDRIX"

    def test_code_groupe_est_le_vrai_code_sts_pas_un_id_interne(self, db_session):
        """Écart assumé par rapport à GEPI, voir schemas/import_eleves.xsd : CODE_GROUPE = Group.name."""
        ctx = _scaffold(db_session)
        student = _make_student(db_session, ctx)
        StudentClassPartLink.create(db_session, {
            "student_id": student.id, "class_part_id": ctx["class_part"].id, "begin_date": date(2026, 9, 10),
        })
        contenu = build_import_eleves(db_session, ctx["school"], date(2026, 10, 1), 1)
        racine = ET.fromstring(contenu)
        groupe = racine.find(".//ELEVE/GROUPES/GROUPE")
        assert groupe.find("CODE_GROUPE").text == "6LV1.ALL"

    def test_date_debut_groupe_est_la_vraie_date_du_lien(self, db_session):
        """Second écart assumé par rapport à GEPI : DATE_DEBUT_GROUPE = begin_date réel, pas une
        borne globale d'établissement."""
        ctx = _scaffold(db_session)
        student = _make_student(db_session, ctx)
        StudentClassPartLink.create(db_session, {
            "student_id": student.id, "class_part_id": ctx["class_part"].id, "begin_date": date(2026, 11, 15),
        })
        contenu = build_import_eleves(db_session, ctx["school"], date(2026, 12, 1), 1)
        racine = ET.fromstring(contenu)
        groupe = racine.find(".//ELEVE/GROUPES/GROUPE")
        assert groupe.find("DATE_DEBUT_GROUPE").text == "2026-11-15"
        # DATE_FIN_GROUPE, elle, retombe sur la borne d'établissement : seuls les rattachements
        # ACTIFS sont exportés, leur date de fin réelle n'est par construction pas encore connue.
        assert groupe.find("DATE_FIN_GROUPE").text == "2027-07-04"

    def test_lien_clos_absent_du_fichier(self, db_session):
        ctx = _scaffold(db_session)
        student = _make_student(db_session, ctx)
        StudentClassPartLink.create(db_session, {
            "student_id": student.id, "class_part_id": ctx["class_part"].id,
            "begin_date": date(2026, 9, 10), "end_date": date(2026, 10, 1),
        })
        contenu = build_import_eleves(db_session, ctx["school"], date(2026, 10, 5), 1)
        racine = ET.fromstring(contenu)
        eleve = racine.find(".//ELEVE")
        assert eleve.find("GROUPES").findall("GROUPE") == []

    def test_eleve_sans_groupe_a_quand_meme_une_entree(self, db_session):
        """Même comportement que GEPI (export_groupes_sconet.php:216-241) : un élève éligible
        obtient une entrée ELEVE même sans aucun groupe actif, avec un GROUPES vide."""
        ctx = _scaffold(db_session)
        _make_student(db_session, ctx)
        contenu = build_import_eleves(db_session, ctx["school"], date(2026, 10, 1), 1)
        racine = ET.fromstring(contenu)
        assert racine.find(".//ELEVE") is not None

    def test_exclus_absents_du_fichier(self, db_session):
        ctx = _scaffold(db_session)
        _make_student(db_session, ctx, siecle_id=None)
        contenu = build_import_eleves(db_session, ctx["school"], date(2026, 10, 1), 1)
        racine = ET.fromstring(contenu)
        assert racine.find(".//ELEVE") is None


def test_export_filename():
    school = type("S", (), {"uai": "0750001A"})()
    assert export_filename(school, date(2026, 8, 22)) == "0750001A_ELEGROUPE_20260822.xml"


class TestWizard:
    def _wizard(self):
        return WizardElevesExport(id=1)

    def test_aucune_ecriture_a_l_apercu(self, db_session):
        ctx = _scaffold(db_session)
        _make_student(db_session, ctx)
        assert SystemSetting.get_siecle_group_export_seq(db_session) == 0
        self._wizard().rpc_preview(db_session, school_id=ctx["school"].id)
        assert SystemSetting.get_siecle_group_export_seq(db_session) == 0

    def test_export_incremente_le_compteur_une_fois(self, db_session):
        ctx = _scaffold(db_session)
        _make_student(db_session, ctx)
        result = self._wizard().rpc_export(db_session, school_id=ctx["school"].id)
        assert SystemSetting.get_siecle_group_export_seq(db_session) == 1
        assert "envoi n°1" in result["result_html"]
        assert result["export_file"]["filename"].startswith("0750001A_ELEGROUPE_")

    def test_deux_exports_successifs_incrementent_deux_fois(self, db_session):
        ctx = _scaffold(db_session)
        _make_student(db_session, ctx)
        self._wizard().rpc_export(db_session, school_id=ctx["school"].id)
        self._wizard().rpc_export(db_session, school_id=ctx["school"].id)
        assert SystemSetting.get_siecle_group_export_seq(db_session) == 2

    def test_echec_de_generation_n_incremente_pas(self, db_session):
        ctx = _scaffold(db_session, with_end_date=False)
        _make_student(db_session, ctx)
        with pytest.raises(ValueError):
            self._wizard().rpc_export(db_session, school_id=ctx["school"].id)
        assert SystemSetting.get_siecle_group_export_seq(db_session) == 0

    def test_ecran_precedent_ne_correspond_pas_a_une_ecriture(self, db_session):
        ctx = _scaffold(db_session)
        _make_student(db_session, ctx)
        self._wizard().rpc_preview(db_session, school_id=ctx["school"].id)
        self._wizard().rpc_preview(db_session, school_id=ctx["school"].id)
        assert SystemSetting.get_siecle_group_export_seq(db_session) == 0
