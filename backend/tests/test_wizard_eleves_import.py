"""
Tests du wizard d'import élèves/responsables SIECLE (backend/app/models/wizard_eleves_import.py).

Le parseur est couvert à part, sans base, par test_eleves_flux.py. Ici on teste ce que le wizard
ajoute : les garde-fous (les deux fichiers sont obligatoires, année, RNE, cohérence entre les deux
fichiers), la création dynamique de division/MEF-division/groupe, le blocage sur MEF/matière/
modalité d'élection inconnus, la clé d'appariement (Student.national_id, Parent.siecle_id), et la
correspondance ELEVE_ID -> élève.
"""
import base64
import pathlib
import pytest
from sqlalchemy.orm import sessionmaker

from backend.app.models.base import Base
from backend.app.models import (
    School, Division, Mef, RefGrade, SystemSetting, Subject, Discipline, Student, Parent,
    RefElectionMethod, RefRegime, RefTitle, RefLegalGuardian, StudentParentLink,
)
from backend.app.models.mef import MefDivision
from backend.app.models.group import Group
from backend.app.models.student import StudentSpecialtyChoice
from backend.app.models.wizard_eleves_import import WizardElevesImport
from backend.tests.db_test_utils import make_test_engine

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
FLUX_UAI = "0750001A"
FLUX_YEAR = "2026"

# Fichier responsables minimal mais valide (bon UAJ/année, aucune donnée) : sert de complément
# quand un test porte sur le fichier élèves et n'a rien à tester côté responsables — les deux
# fichiers sont désormais obligatoires (voir _load), aucun test ne peut plus en omettre un.
_MINIMAL_RESPONSABLES = f"""<BEE_RESPONSABLES><PARAMETRES><UAJ>{FLUX_UAI}</UAJ>
<ANNEE_SCOLAIRE>{FLUX_YEAR}</ANNEE_SCOLAIRE><HORODATAGE>01/01/2026 00:00:00</HORODATAGE>
</PARAMETRES><DONNEES/></BEE_RESPONSABLES>""".encode("utf-8")

# Symétrique, pour les tests qui portent sur le fichier responsables.
_MINIMAL_ELEVES = f"""<BEE_ELEVES><PARAMETRES><UAJ>{FLUX_UAI}</UAJ>
<ANNEE_SCOLAIRE>{FLUX_YEAR}</ANNEE_SCOLAIRE><HORODATAGE>01/01/2026 00:00:00</HORODATAGE>
</PARAMETRES><DONNEES/></BEE_ELEVES>""".encode("utf-8")


def _upload(nom) -> dict:
    return {
        "filename": nom,
        "mime_type": "text/xml",
        "data_base64": base64.b64encode((FIXTURES / nom).read_bytes()).decode("ascii"),
    }


def _upload_bytes(content: bytes) -> dict:
    return {"filename": "test.xml", "mime_type": "text/xml", "data_base64": base64.b64encode(content).decode("ascii")}


def _eleves_upload():
    return _upload("ElevesAvecAdresses_0750001A_2026.xml")


def _responsables_upload():
    return _upload("ResponsablesAvecAdresses_0750001A_2026.xml")


def _minimal_responsables_upload():
    return _upload_bytes(_MINIMAL_RESPONSABLES)


def _minimal_eleves_upload():
    return _upload_bytes(_MINIMAL_ELEVES)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        SystemSetting.create(db, {"key": "STANDARD_TIMESLOT_DURATION", "value": "30"})
        SystemSetting.create(db, {"key": "SCHOOL_YEAR", "value": FLUX_YEAR})
        School.create(db, {"uai": FLUX_UAI, "name": "Collège Claude Bernard"})
        ref_grade = RefGrade.create(db, {"name": "6EME"})
        Mef.create(db, {
            "school_id": db.query(School).first().id, "code_national": "10010012110", "name": "6EME",
            "ref_grade_id": ref_grade.id, "max_students_per_class": 30, "forecast_student_count": 30,
        })
        discipline = Discipline.create(db, {"code": "LANG", "name": "Langues"})
        Subject.create(db, {"code": "ALL1", "code_nomenclature": "030101", "short_name": "Allemand", "name": "Allemand LV1", "discipline_id": discipline.id})
        Subject.create(db, {"code": "ANG1", "code_nomenclature": "030201", "short_name": "Anglais", "name": "Anglais LV1", "discipline_id": discipline.id})
        RefElectionMethod.create(db, {"code": "O", "name": "Obligatoire", "export_code": "O"})
        RefRegime.create(db, {"code": "DP", "name": "Demi-pensionnaire"})
        RefTitle.create(db, {"name": "Monsieur", "code": "M."})
        RefTitle.create(db, {"name": "Madame", "code": "MME"})
        RefLegalGuardian.create(db, {"code": "1", "name": "Responsable légal 1"})
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _wizard():
    return WizardElevesImport(id=1)


class TestGardeFous:
    def test_fichier_eleves_manquant_refuse(self, db_session):
        with pytest.raises(ValueError, match="élèves.*obligatoire"):
            _wizard().rpc_analyze(db_session, parents_file=_responsables_upload())

    def test_fichier_responsables_manquant_refuse(self, db_session):
        with pytest.raises(ValueError, match="responsables.*obligatoire"):
            _wizard().rpc_analyze(db_session, students_file=_eleves_upload())

    def test_aucun_fichier_refuse(self, db_session):
        with pytest.raises(ValueError, match="obligatoire"):
            _wizard().rpc_analyze(db_session)

    def test_annee_differente_refusee(self, db_session):
        setting = db_session.query(SystemSetting).filter(SystemSetting.key == "SCHOOL_YEAR").first()
        setting.update(db_session, {"value": "2030"})
        with pytest.raises(ValueError, match="année scolaire"):
            _wizard().rpc_analyze(db_session, students_file=_eleves_upload(), parents_file=_responsables_upload())

    def test_rne_inconnu_refuse(self, db_session):
        school = db_session.query(School).filter(School.uai == FLUX_UAI).first()
        school.update(db_session, {"uai": "9999999Z"})
        with pytest.raises(ValueError, match="ne correspond à aucun établissement"):
            _wizard().rpc_analyze(db_session, students_file=_eleves_upload(), parents_file=_responsables_upload())

    def test_racine_eleves_invalide_refusee(self, db_session):
        with pytest.raises(ValueError, match="BEE_ELEVES"):
            _wizard().rpc_analyze(db_session, students_file=_upload_bytes(b"<AUTRE/>"), parents_file=_responsables_upload())

    def test_deux_fichiers_de_rne_different_refuses(self, db_session):
        School.create(db_session, {"uai": "9999999Z", "name": "Autre collège"})
        autre = b"""<BEE_RESPONSABLES><PARAMETRES><UAJ>9999999Z</UAJ><ANNEE_SCOLAIRE>2026</ANNEE_SCOLAIRE>
        <HORODATAGE>01/01/2026 00:00:00</HORODATAGE></PARAMETRES><DONNEES/></BEE_RESPONSABLES>"""
        with pytest.raises(ValueError, match="RNE"):
            _wizard().rpc_analyze(db_session, students_file=_eleves_upload(), parents_file=_upload_bytes(autre))

    def test_aucune_ecriture_avant_l_import(self, db_session):
        _wizard().rpc_analyze(
            db_session, students_file=_eleves_upload(), parents_file=_responsables_upload(),
            import_students=True, import_groups=True, import_options=True, import_responsables=True,
        )
        assert db_session.query(Student).count() == 0
        assert db_session.query(Parent).count() == 0
        assert db_session.query(Division).count() == 0


class TestImportEleves:
    def test_cree_la_division_dynamiquement(self, db_session):
        assert db_session.query(Division).filter(Division.code == "6E1").first() is None
        _wizard().rpc_import(db_session, students_file=_eleves_upload(), parents_file=_minimal_responsables_upload(), import_students=True)
        division = db_session.query(Division).filter(Division.code == "6E1").first()
        assert division is not None
        assert division.name == "6E1"  # pas de libellé dans le fichier : le code sert de nom

    def test_cree_les_deux_eleves_avec_leurs_champs(self, db_session):
        _wizard().rpc_import(db_session, students_file=_eleves_upload(), parents_file=_minimal_responsables_upload(), import_students=True)
        martin = db_session.query(Student).filter(Student.national_id == "1234567890X").first()
        assert martin is not None
        assert martin.first_name == "Jean"
        assert martin.last_name == "MARTIN"
        assert martin.gender.value == "M"
        assert martin.doublement is False
        assert str(martin.birth_date) == "2015-04-15"
        assert martin.regime.code == "DP"
        assert martin.birth_city.insee_code == "75101"
        assert martin.last_year_level == "CM2"
        assert martin.last_year_school.rne_code == "0759999Z"

    def test_reimport_met_a_jour_par_national_id_sans_doublon(self, db_session):
        for _ in range(2):
            _wizard().rpc_import(db_session, students_file=_eleves_upload(), parents_file=_minimal_responsables_upload(), import_students=True)
        assert db_session.query(Student).count() == 2

    def test_mef_absent_bloque_la_creation_de_l_eleve(self, db_session):
        db_session.query(Mef).filter(Mef.code_national == "10010012110").first().delete(db_session)
        result = _wizard().rpc_import(db_session, students_file=_eleves_upload(), parents_file=_minimal_responsables_upload(), import_students=True)
        assert db_session.query(Student).count() == 0
        assert "MEF" in result["result_html"]

    def test_mef_existant_non_rattache_est_rattache_dynamiquement(self, db_session):
        division = Division.create(db_session, {"code": "6E1", "name": "6ème 1", "school_id": db_session.query(School).first().id})
        mef = db_session.query(Mef).filter(Mef.code_national == "10010012110").first()
        assert db_session.query(MefDivision).filter(MefDivision.mef_id == mef.id, MefDivision.division_id == division.id).first() is None
        _wizard().rpc_import(db_session, students_file=_eleves_upload(), parents_file=_minimal_responsables_upload(), import_students=True)
        assert db_session.query(MefDivision).filter(MefDivision.mef_id == mef.id, MefDivision.division_id == division.id).first() is not None

    def test_case_decochee_ne_cree_rien(self, db_session):
        _wizard().rpc_import(db_session, students_file=_eleves_upload(), parents_file=_minimal_responsables_upload(), import_students=False)
        assert db_session.query(Student).count() == 0


class TestImportGroupes:
    def test_decoche_par_defaut_aucun_groupe_cree(self, db_session):
        _wizard().rpc_import(db_session, students_file=_eleves_upload(), parents_file=_minimal_responsables_upload(), import_students=True)
        assert db_session.query(Group).count() == 0

    def test_coche_cree_le_groupe_et_y_rattache_l_eleve(self, db_session):
        _wizard().rpc_import(
            db_session, students_file=_eleves_upload(), parents_file=_minimal_responsables_upload(),
            import_students=True, import_groups=True,
        )
        groupe = db_session.query(Group).filter(Group.name == "6LV1.ALL").first()
        assert groupe is not None
        martin = db_session.query(Student).filter(Student.national_id == "1234567890X").first()
        assert groupe.class_parts[0] in martin.class_parts

    def test_eleve_sans_division_et_groupe_inexistant_signale_dans_le_bilan(self, db_session):
        sans_division = b"""<BEE_ELEVES><PARAMETRES><UAJ>0750001A</UAJ><ANNEE_SCOLAIRE>2026</ANNEE_SCOLAIRE>
        <HORODATAGE>01/01/2026 00:00:00</HORODATAGE></PARAMETRES><DONNEES>
        <STRUCTURES><STRUCTURES_ELEVE ELEVE_ID="1">
          <STRUCTURE><CODE_STRUCTURE>NOUVGRP</CODE_STRUCTURE><TYPE_STRUCTURE>G</TYPE_STRUCTURE></STRUCTURE>
        </STRUCTURES_ELEVE></STRUCTURES>
        <ELEVES><ELEVE ELEVE_ID="1"><ID_NATIONAL>X</ID_NATIONAL><NOM>TEST</NOM><PRENOM>Sans Division</PRENOM>
        <CODE_MEF>10010012110</CODE_MEF></ELEVE></ELEVES></DONNEES></BEE_ELEVES>"""
        result = _wizard().rpc_import(
            db_session, students_file=_upload_bytes(sans_division), parents_file=_minimal_responsables_upload(),
            import_students=True, import_groups=True,
        )
        assert db_session.query(Group).filter(Group.name == "NOUVGRP").first() is None
        assert "NOUVGRP" in result["result_html"]


class TestImportOptions:
    def test_cree_le_voeu_de_specialite(self, db_session):
        _wizard().rpc_import(db_session, students_file=_eleves_upload(), parents_file=_minimal_responsables_upload(), import_students=True, import_options=True)
        martin = db_session.query(Student).filter(Student.national_id == "1234567890X").first()
        assert db_session.query(StudentSpecialtyChoice).filter(StudentSpecialtyChoice.student_id == martin.id).count() == 1

    def test_matiere_inconnue_bloque_l_option(self, db_session):
        db_session.query(Subject).filter(Subject.code_nomenclature == "030101").first().delete(db_session)
        result = _wizard().rpc_import(db_session, students_file=_eleves_upload(), parents_file=_minimal_responsables_upload(), import_students=True, import_options=True)
        martin = db_session.query(Student).filter(Student.national_id == "1234567890X").first()
        assert db_session.query(StudentSpecialtyChoice).filter(StudentSpecialtyChoice.student_id == martin.id).count() == 0
        assert "030101" in result["result_html"]


class TestImportResponsables:
    def test_cree_les_deux_responsables(self, db_session):
        _wizard().rpc_import(db_session, students_file=_minimal_eleves_upload(), parents_file=_responsables_upload(), import_responsables=True)
        martin = db_session.query(Parent).filter(Parent.siecle_id == "50001").first()
        assert martin is not None
        assert martin.first_name == "Pierre"
        assert martin.title.code == "M."
        assert martin.mobile_phone == "0699887766"
        assert martin.address_city.name == "PARIS"
        assert martin.address_country.name == "FRANCE"

    def test_eleve_absent_du_fichier_eleves_aucun_rattachement(self, db_session):
        """Le fichier élèves déposé est vide (aucun ELEVE_ID connu) : les RESPONSABLE du fichier
        responsables ne peuvent pas être rattachés, mais les Parent sont tout de même créés."""
        _wizard().rpc_import(db_session, students_file=_minimal_eleves_upload(), parents_file=_responsables_upload(), import_responsables=True)
        assert db_session.query(Parent).count() == 2
        assert db_session.query(StudentParentLink).count() == 0

    def test_avec_les_deux_fichiers_le_rattachement_est_cree(self, db_session):
        _wizard().rpc_import(
            db_session, students_file=_eleves_upload(), parents_file=_responsables_upload(),
            import_students=True, import_responsables=True,
        )
        martin_eleve = db_session.query(Student).filter(Student.national_id == "1234567890X").first()
        martin_parent = db_session.query(Parent).filter(Parent.siecle_id == "50001").first()
        lien = db_session.query(StudentParentLink).filter(
            StudentParentLink.student_id == martin_eleve.id, StudentParentLink.parent_id == martin_parent.id,
        ).first()
        assert lien is not None
        assert lien.legal_guardian.code == "1"
        assert lien.pays_school_fees is True

    def test_reimport_ne_duplique_pas_le_rattachement(self, db_session):
        for _ in range(2):
            _wizard().rpc_import(
                db_session, students_file=_eleves_upload(), parents_file=_responsables_upload(),
                import_students=True, import_responsables=True,
            )
        assert db_session.query(StudentParentLink).count() == 2
