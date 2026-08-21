"""
Tests du wizard d'import de flux STS-web (backend/app/models/wizard_sts_import.py).

Le parseur lui-même est couvert à part, sans base, par test_sts_flux.py. Ici on teste ce que le
wizard ajoute : les deux garde-fous (année, RNE), l'étape de correspondances, la résolution des
appariements, et la politique « créer ce qui manque, mettre à jour ce qui existe, ne rien
supprimer ».
"""
import base64
import pathlib
import pytest
from sqlalchemy.orm import sessionmaker

from backend.app.models.base import Base
from backend.app.models import (
    School, Discipline, Subject, Mef, Division, SystemSetting, RefGrade, Teacher,
)
from backend.app.models.group import Group
from backend.app.models.mef import MefDivision, MefService
from backend.app.models.service import Service
from backend.app.models.teacher import TeacherDiscipline
from backend.app.models.wizard_sts_import import WizardStsImport
from backend.tests.db_test_utils import make_test_engine
from backend.app.core.html_text import esc

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
FLUX_UAI = "0750001A"
FLUX_YEAR = "2026"


def _upload(nom="sts_emp_0750001A_2026.xml") -> dict:
    """Valeur d'un champ `type: "binary"` telle que la produit le frontend (§15.Q)."""
    return {
        "filename": nom,
        "mime_type": "text/xml",
        "data_base64": base64.b64encode((FIXTURES / nom).read_bytes()).decode("ascii"),
    }


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        SystemSetting.create(db, {"key": "STANDARD_TIMESLOT_DURATION", "value": "30"})
        SystemSetting.create(db, {"key": "SCHOOL_YEAR", "value": FLUX_YEAR})
        School.create(db, {"uai": FLUX_UAI, "name": "Collège Claude Bernard"})
        for name in ("6EME", "5EME"):
            RefGrade.create(db, {"name": name})
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _wizard():
    return WizardStsImport(id=1)


def _resolutions(db, **overrides):
    """Rejoue l'étape 1 puis renvoie les lignes de correspondance, éventuellement retouchées —
    c'est exactement ce que le formulaire transmet à l'étape suivante."""
    res = _wizard().rpc_analyze(db, sts_file=_upload())
    mef_rows, subject_rows = res["mef_rows"], res["subject_rows"]
    for row in mef_rows:
        if row["code"] in overrides:
            row["ref_grade_id"] = overrides[row["code"]]
    for row in subject_rows:
        if row["code"] in overrides:
            row["discipline_id"] = overrides[row["code"]]
    return mef_rows, subject_rows


def _selection(**overrides):
    defauts = dict(
        import_school=True, import_disciplines=True, import_subjects=True, import_mefs=True,
        import_teachers=True, import_divisions=True, import_groups=True,
        import_services=False,
    )
    defauts.update(overrides)
    return defauts


def _preview(db, **selection):
    mef_rows, subject_rows = _resolutions(db)
    return _wizard().rpc_preview(
        db, sts_file=_upload(), mef_rows=mef_rows, subject_rows=subject_rows, **_selection(**selection)
    )


def _import(db, mef_rows=None, subject_rows=None, **selection):
    if mef_rows is None or subject_rows is None:
        mef_rows, subject_rows = _resolutions(db)
    return _wizard().rpc_import(
        db, sts_file=_upload(), mef_rows=mef_rows, subject_rows=subject_rows, **_selection(**selection)
    )


class TestGardeFous:
    def test_annee_differente_refusee(self, db_session):
        setting = db_session.query(SystemSetting).filter(SystemSetting.key == "SCHOOL_YEAR").first()
        setting.update(db_session, {"value": "2030"})
        with pytest.raises(ValueError, match="année scolaire"):
            _wizard().rpc_analyze(db_session, sts_file=_upload())

    def test_rne_inconnu_refuse(self, db_session):
        school = db_session.query(School).filter(School.uai == FLUX_UAI).first()
        school.update(db_session, {"uai": "9999999Z"})
        with pytest.raises(ValueError, match="ne correspond à aucun établissement"):
            _wizard().rpc_analyze(db_session, sts_file=_upload())

    def test_le_message_de_rne_liste_les_rne_connus(self, db_session):
        school = db_session.query(School).filter(School.uai == FLUX_UAI).first()
        school.update(db_session, {"uai": "9999999Z"})
        with pytest.raises(ValueError, match="9999999Z"):
            _wizard().rpc_analyze(db_session, sts_file=_upload())

    def test_fichier_montant_refuse(self, db_session):
        with pytest.raises(ValueError, match="sts_emp"):
            _wizard().rpc_analyze(db_session, sts_file=_upload("emp_sts_0750001A_2026.xml"))

    def test_aucune_ecriture_avant_l_import(self, db_session):
        _preview(db_session)
        assert db_session.query(Teacher).count() == 0
        assert db_session.query(Division).count() == 0
        assert db_session.query(Subject).count() == 0


class TestAvertissementExperimental:
    def test_encart_present_sur_la_premiere_page(self, db_session):
        html = WizardStsImport.read(db_session)[0].info_html
        assert "expérimental" in html.lower()
        assert "GEPI" in html and "CDT" in html
        assert "pseudonymis" in html

    def test_les_services_sont_decoches_par_defaut(self, db_session):
        wizard = WizardStsImport.read(db_session)[0]
        assert wizard.import_services is False
        assert wizard.import_divisions is True


class TestCorrespondances:
    def test_le_niveau_du_mef_est_preremplí(self, db_session):
        res = _wizard().rpc_analyze(db_session, sts_file=_upload())
        ligne = next(r for r in res["mef_rows"] if r["code"] == "10010012110")
        grade_6eme = db_session.query(RefGrade).filter(RefGrade.name == "6EME").first()
        assert ligne["ref_grade_id"] == grade_6eme.id

    def test_un_niveau_indeductible_est_laisse_vide_et_soumis_a_l_utilisateur(self, db_session):
        """Le flux ne porte pas le niveau. Sans correspondance de libellé, on ne devine pas : la
        ligne arrive vide dans l'étape « Correspondances »."""
        for grade in db_session.query(RefGrade).all():
            grade.update(db_session, {"name": "TERMINALE"} if grade.name == "6EME" else {"name": "2NDE"})
        res = _wizard().rpc_analyze(db_session, sts_file=_upload())
        ligne = next(r for r in res["mef_rows"] if r["code"] == "10010012110")
        assert ligne["ref_grade_id"] is None
        assert "à compléter" in res["resolution_html"]

    def test_un_mef_laisse_vide_n_est_pas_importe(self, db_session):
        mef_rows, subject_rows = _resolutions(db_session)
        for row in mef_rows:
            row["ref_grade_id"] = None
        res = _import(db_session, mef_rows=mef_rows, subject_rows=subject_rows)
        assert db_session.query(Mef).count() == 0
        assert "aucun niveau choisi" in res["result_html"]

    def test_le_choix_de_l_utilisateur_prime(self, db_session):
        grade_5eme = db_session.query(RefGrade).filter(RefGrade.name == "5EME").first()
        mef_rows, subject_rows = _resolutions(db_session, **{"10010012110": grade_5eme.id})
        _import(db_session, mef_rows=mef_rows, subject_rows=subject_rows)
        mef = db_session.query(Mef).filter(Mef.code_national == "10010012110").first()
        assert mef.ref_grade_id == grade_5eme.id

    def test_seuls_les_objets_a_creer_sont_soumis(self, db_session):
        """Un MEF déjà en base a déjà son niveau : l'import ne le remet pas en cause."""
        grade = db_session.query(RefGrade).first()
        Mef.create(db_session, {
            "school_id": db_session.query(School).first().id,
            "code_national": "10010012110", "name": "6EME", "ref_grade_id": grade.id,
        })
        res = _wizard().rpc_analyze(db_session, sts_file=_upload())
        assert res["mef_rows"] == []

    def test_matiere_sans_discipline_deductible_est_laissee_vide(self, db_session):
        """La déduction passe par les services du flux ; les disciplines n'existant pas encore en
        base, la ligne arrive sans discipline_id mais avec le code deviné."""
        res = _wizard().rpc_analyze(db_session, sts_file=_upload())
        ligne = next(r for r in res["subject_rows"] if r["code"] == "030101")
        assert ligne["discipline_id"] is None
        assert ligne["guessed_discipline_code"] == "030101"

    def test_matiere_sans_discipline_du_tout_est_laissee_de_cote(self, db_session):
        mef_rows, subject_rows = _resolutions(db_session)
        for row in subject_rows:
            row["discipline_id"] = None
            row["guessed_discipline_code"] = None
        res = _import(db_session, mef_rows=mef_rows, subject_rows=subject_rows)
        assert db_session.query(Subject).count() == 0
        assert "aucune discipline choisie" in res["result_html"]

    def test_la_discipline_choisie_par_l_utilisateur_est_utilisee(self, db_session):
        lettres = Discipline.create(db_session, {"code": "L0100", "name": "Lettres"})
        mef_rows, subject_rows = _resolutions(db_session, **{"030101": lettres.id})
        _import(db_session, mef_rows=mef_rows, subject_rows=subject_rows)
        allemand = db_session.query(Subject).filter(Subject.code_nomenclature == "030101").first()
        assert allemand.discipline_id == lettres.id


class TestApercu:
    def test_entete_porte_rne_annee_et_etablissement(self, db_session):
        res = _wizard().rpc_analyze(db_session, sts_file=_upload())
        assert FLUX_UAI in res["header_html"]
        assert "2026-2027" in res["header_html"]
        assert "Collège Claude Bernard" in res["header_html"]

    def test_volumetrie_par_type(self, db_session):
        res = _preview(db_session)
        par_type = {r["entity"]: r for r in res["summary_rows"]}
        assert par_type["Enseignants"]["to_create"] == 2
        assert par_type["Classes"]["to_create"] == 1
        assert par_type["Groupes"]["to_create"] == 2
        assert par_type["MEF"]["to_create"] == 1


class TestImport:
    def test_enseignants_crees_avec_leur_identifiant_epp(self, db_session):
        _import(db_session)
        durand = db_session.query(Teacher).filter(Teacher.epp_id == "8949").first()
        assert durand is not None
        assert durand.last_name == "DURAND"
        assert durand.first_name == "Michel"
        assert durand.is_epp is True
        assert durand.school_id == db_session.query(School).first().id

    def test_teacher_discipline_cree_depuis_les_balises_du_flux(self, db_session):
        """INDIVIDU/DISCIPLINE/@CODE — une ligne TeacherDiscipline par discipline déclarée."""
        _import(db_session)
        durand = db_session.query(Teacher).filter(Teacher.epp_id == "8949").first()
        assert [l.discipline.code for l in durand.discipline_lines] == ["030101"]

    def test_les_lignes_discipline_existantes_ne_sont_jamais_retirees(self, db_session):
        """Un enseignant peut porter dans la base des disciplines que le flux ignore."""
        _import(db_session)
        durand = db_session.query(Teacher).filter(Teacher.epp_id == "8949").first()
        autre = Discipline.create(db_session, {"code": "L9999", "name": "Discipline locale"})
        TeacherDiscipline.create(db_session, {"teacher_id": durand.id, "discipline_id": autre.id})
        _import(db_session)
        assert "L9999" in [l.discipline.code for l in durand.discipline_lines]

    def test_professeur_principal_reporte_sur_la_classe(self, db_session):
        _import(db_session)
        division = db_session.query(Division).filter(Division.code == "6E1").first()
        assert division.main_teacher.epp_id == "8949"

    def test_classe_rattachee_a_son_mef(self, db_session):
        _import(db_session)
        division = db_session.query(Division).filter(Division.code == "6E1").first()
        liens = db_session.query(MefDivision).filter(MefDivision.division_id == division.id).all()
        assert [l.mef.code_national for l in liens] == ["10010012110"]

    def test_mef_rattache_au_bon_niveau(self, db_session):
        _import(db_session)
        mef = db_session.query(Mef).filter(Mef.code_national == "10010012110").first()
        assert mef.ref_grade.name == "6EME"
        assert mef.school_id == db_session.query(School).first().id

    def test_matieres_creees_avec_leurs_deux_codes(self, db_session):
        _import(db_session)
        allemand = db_session.query(Subject).filter(Subject.code_nomenclature == "030101").first()
        assert allemand.code == "ALLEMAND"
        assert allemand.short_name == "ALLEMAND LV1"

    def test_groupes_crees_avec_leur_code_sts_comme_nom(self, db_session):
        _import(db_session)
        assert {g.name for g in db_session.query(Group).all()} == {"6LV1.ALL", "6LV1.ANG"}

    def test_disciplines_creees(self, db_session):
        _import(db_session)
        assert {d.code for d in db_session.query(Discipline).all()} == {"030101", "030201"}


class TestServices:
    """Import des services : décoché par défaut, et il crée le gabarit MEF manquant à volumes
    nuls pour que la cascade native du modèle engendre les Service."""

    def test_decoche_aucun_service_n_est_cree(self, db_session):
        _import(db_session)
        assert db_session.query(Service).count() == 0
        assert db_session.query(MefService).count() == 0

    def test_coche_le_gabarit_mef_est_cree(self, db_session):
        """Le fichier d'exemple porte une section PROGRAMMES : le gabarit reçoit donc son volume.
        Sans cette section, il serait créé à zéro — voir TestProgrammes."""
        _import(db_session, import_services=True)
        gabarit = db_session.query(MefService).one()
        assert gabarit.subject.code_nomenclature == "030101"
        assert gabarit.weekly_duration_full_class_minutes == 240

    def test_le_service_est_engendre_par_la_cascade_et_recoit_ses_enseignants(self, db_session):
        _import(db_session, import_services=True)
        service = db_session.query(Service).one()
        assert service.division_id == db_session.query(Division).filter(Division.code == "6E1").first().id
        assert [t.epp_id for t in service.teachers] == ["8949"]

    def test_le_rapport_annonce_les_volumes_a_completer(self, db_session):
        res = _import(db_session, import_services=True)
        assert "volumes horaires nuls" in res["result_html"]

    def test_le_compteur_porte_sur_les_gabarits_pas_sur_les_lignes_du_fichier(self, db_session):
        """La cascade engendre un Service par classe du MEF : compter les lignes de service du
        fichier donnerait un chiffre faux dans les deux sens."""
        res = _import(db_session, import_services=True)
        assert "1 gabarit(s) MEF créé(s)" in res["result_html"]
        assert "1 service(s) pourvu(s) en enseignants" in res["result_html"]

    def test_le_rapport_annonce_la_cascade(self, db_session):
        res = _import(db_session, import_services=True)
        assert "toutes</em> les classes de son" in res["result_html"]

    def test_les_services_de_groupe_sont_signales_non_importes(self, db_session):
        res = _import(db_session, import_services=True)
        assert "porté par un groupe" in res["result_html"]

    def test_second_import_ne_duplique_pas_le_gabarit(self, db_session):
        _import(db_session, import_services=True)
        _import(db_session, import_services=True)
        assert db_session.query(MefService).count() == 1
        assert db_session.query(Service).count() == 1


class TestSelectionEtIdempotence:
    def test_un_type_decoche_n_est_pas_importe(self, db_session):
        _import(db_session, import_groups=False)
        assert db_session.query(Group).count() == 0
        assert db_session.query(Teacher).count() == 2

    def test_second_import_ne_duplique_rien(self, db_session):
        _import(db_session)
        compteurs = {
            "teachers": db_session.query(Teacher).count(),
            "divisions": db_session.query(Division).count(),
            "subjects": db_session.query(Subject).count(),
            "groups": db_session.query(Group).count(),
        }
        _import(db_session)
        assert db_session.query(Teacher).count() == compteurs["teachers"]
        assert db_session.query(Division).count() == compteurs["divisions"]
        assert db_session.query(Subject).count() == compteurs["subjects"]
        assert db_session.query(Group).count() == compteurs["groups"]

    def test_un_objet_existant_est_mis_a_jour_et_non_duplique(self, db_session):
        """Politique retenue : créer ce qui manque, mettre à jour ce qui existe. L'appariement
        se fait sur le code national, ici Division.code."""
        Division.create(db_session, {
            "school_id": db_session.query(School).first().id,
            "code": "6E1", "name": "ancien libellé", "student_count": 12,
        })
        res = _import(db_session)
        divisions = db_session.query(Division).filter(Division.code == "6E1").all()
        assert len(divisions) == 1
        assert divisions[0].student_count == 12, "l'effectif local n'est pas écrasé par le flux"
        assert "1 mis à jour" in res["result_html"]

    def test_import_ne_supprime_jamais(self, db_session):
        """Un objet absent du flux survit à l'import — c'est la règle annoncée à l'utilisateur."""
        Division.create(db_session, {
            "school_id": db_session.query(School).first().id, "code": "HORS_FLUX", "name": "Classe locale",
        })
        _import(db_session)
        assert db_session.query(Division).filter(Division.code == "HORS_FLUX").first() is not None


class TestAbsentsDuFichier:
    """Objets déjà en base et absents du flux : purement informatif, l'import ne supprime jamais,
    mais l'écart doit se voir — c'est lui qui révèle un départ, une fermeture de classe, ou un
    fichier qui n'est pas celui qu'on croyait."""

    def test_une_classe_absente_du_fichier_est_signalee(self, db_session):
        Division.create(db_session, {
            "school_id": db_session.query(School).first().id,
            "code": "5Z", "name": "Classe fermée",
        })
        res = _preview(db_session)
        par_type = {r["entity"]: r for r in res["summary_rows"]}
        assert par_type["Classes"]["missing"] == 1
        assert "Classe fermée" in res["missing_html"]

    def test_un_enseignant_sans_epp_id_est_signale(self, db_session):
        """Il ne peut pas figurer dans le fichier faute de clé d'appariement, et c'est justement
        ce qu'il faut voir : il ne remontera jamais vers STS-web."""
        school = db_session.query(School).first()
        discipline = Discipline.create(db_session, {"code": "L0100", "name": "Lettres"})
        local = Teacher.create(db_session, {"code": "LOCAL1", "last_name": "LOCAL", "school_id": school.id})
        TeacherDiscipline.create(db_session, {"teacher_id": local.id, "discipline_id": discipline.id})
        res = _preview(db_session)
        par_type = {r["entity"]: r for r in res["summary_rows"]}
        assert par_type["Enseignants"]["missing"] == 1
        assert "LOCAL" in res["missing_html"]

    def test_un_enseignant_d_un_autre_etablissement_n_est_pas_signale(self, db_session):
        """Le fichier ne concerne qu'un RNE : signaler les objets d'un autre établissement de la
        base n'aurait aucun sens."""
        autre = School.create(db_session, {"uai": "0750002B", "name": "Lycée voisin"})
        discipline = Discipline.create(db_session, {"code": "L0100", "name": "Lettres"})
        ailleurs = Teacher.create(db_session, {"code": "AILLEURS", "last_name": "AILLEURS", "epp_id": "7777", "school_id": autre.id})
        TeacherDiscipline.create(db_session, {"teacher_id": ailleurs.id, "discipline_id": discipline.id})
        res = _preview(db_session)
        par_type = {r["entity"]: r for r in res["summary_rows"]}
        assert par_type["Enseignants"]["missing"] == 0

    def test_rien_a_signaler_sur_une_base_vide(self, db_session):
        res = _preview(db_session)
        assert "Tout ce que contient la base figure aussi dans le fichier" in res["missing_html"]

    def test_le_bilan_d_import_les_signale_aussi(self, db_session):
        Division.create(db_session, {
            "school_id": db_session.query(School).first().id,
            "code": "5Z", "name": "Classe fermée",
        })
        res = _import(db_session)
        assert "Déjà en base, absents du fichier" in res["result_html"]
        assert "Classe fermée" in res["result_html"]

    def test_l_ecart_est_calcule_avant_l_ecriture(self, db_session):
        """Après import, tous les objets du flux existent en base : calculer l'écart après coup
        ne dirait plus rien. Le second import doit toujours signaler la classe préexistante, et
        jamais celles que l'import vient lui-même de créer."""
        Division.create(db_session, {
            "school_id": db_session.query(School).first().id,
            "code": "5Z", "name": "Classe fermée",
        })
        _import(db_session)
        res = _import(db_session)
        bloc_absents = res["result_html"].split("absents du fichier")[1]
        assert "5Z" in bloc_absents
        assert "6E1" not in bloc_absents


class TestCodesDejaPris:
    """Les codes du flux STS sont des clés : repris tels quels, jamais suffixés — sans quoi le
    prochain import ne retrouverait plus l'enregistrement. Un code déjà porté par un AUTRE
    enregistrement est un conflit de données, signalé et laissé à l'utilisateur."""

    def test_code_de_matiere_repris_tel_quel(self, db_session):
        _import(db_session)
        allemand = db_session.query(Subject).filter(Subject.code_nomenclature == "030101").first()
        assert allemand.code == "ALLEMAND"

    def test_code_d_enseignant_est_son_identifiant_epp(self, db_session):
        _import(db_session)
        durand = db_session.query(Teacher).filter(Teacher.epp_id == "8949").first()
        assert durand.code == "8949"

    def test_code_de_matiere_deja_porte_par_une_autre_matiere(self, db_session):
        autre = Discipline.create(db_session, {"code": "L0100", "name": "Lettres"})
        Subject.create(db_session, {
            "code": "ALLEMAND", "code_nomenclature": "999999",
            "short_name": "Local", "name": "Matière locale", "discipline_id": autre.id,
        })
        res = _import(db_session)
        assert db_session.query(Subject).filter(Subject.code_nomenclature == "030101").first() is None
        assert "désigne déjà la matière" in res["result_html"]
        assert "Matière locale" in res["result_html"]

    def test_code_d_enseignant_deja_porte_par_un_autre_enseignant(self, db_session):
        discipline = Discipline.create(db_session, {"code": "L0100", "name": "Lettres"})
        occupant = Teacher.create(db_session, {
            "code": "8949", "last_name": "OCCUPANT", "school_id": db_session.query(School).first().id,
        })
        TeacherDiscipline.create(db_session, {"teacher_id": occupant.id, "discipline_id": discipline.id})
        res = _import(db_session)
        assert db_session.query(Teacher).filter(Teacher.epp_id == "8949").first() is None
        # Le rapport est du HTML rendu via innerHTML : toute valeur y est échappée (voir
        # core/html_text.py), apostrophe française comprise — d'où la comparaison via esc().
        assert esc("désigne déjà l'enseignant") in res["result_html"]
        assert "OCCUPANT" in res["result_html"]


class TestDonneesEtablissement:
    """Case « Données communes de l'établissement » : PARAMETRES/UAJ et ANNEE_SCOLAIRE. L'import
    complète l'établissement apparié par son RNE, il n'en crée jamais."""

    def test_identite_et_coordonnees(self, db_session):
        _import(db_session)
        school = db_session.query(School).first()
        assert school.name == "COLLEGE CLAUDE BERNARD"
        assert school.address == "1 AVENUE CLAUDE BERNARD"
        assert school.zip_code == "75016"
        assert school.phone == "0102030405"

    def test_academie_creee_a_la_demande(self, db_session):
        from backend.app.models.ref_academie import RefAcademie
        _import(db_session)
        academie = db_session.query(RefAcademie).one()
        assert (academie.code, academie.name) == ("01", "PARIS")
        assert db_session.query(School).first().academie_id == academie.id

    def test_commune_creee_dans_ref_city(self, db_session):
        from backend.app.models.ref_city import RefCity
        _import(db_session)
        ville = db_session.query(RefCity).filter(RefCity.name == "PARIS").one()
        assert ville.zip_code == "75016"
        assert db_session.query(School).first().city_id == ville.id

    def test_dates_de_l_annee_scolaire(self, db_session):
        import datetime
        _import(db_session)
        school = db_session.query(School).first()
        assert school.student_start_date == datetime.date(2026, 9, 2)
        assert school.student_end_date == datetime.date(2027, 7, 4)

    def test_decochee_rien_n_est_touche(self, db_session):
        _import(db_session, import_school=False)
        school = db_session.query(School).first()
        assert school.name == "Collège Claude Bernard"
        assert school.address is None

    def test_une_balise_absente_n_efface_pas(self, db_session):
        """Le fichier d'exemple ne porte ni SIGLE ni STATUT : les valeurs déjà en base survivent."""
        school = db_session.query(School).first()
        school.update(db_session, {"sigle": "CLG", "statut": "Public"})
        _import(db_session)
        assert school.sigle == "CLG"
        assert school.statut == "Public"


class TestEtatCivilEnseignant:
    def test_sexe_grade_fonction_et_nom_de_naissance(self, db_session):
        import datetime
        _import(db_session)
        durand = db_session.query(Teacher).filter(Teacher.epp_id == "8949").first()
        assert durand.gender == "M"
        assert durand.birth_date == datetime.date(1975, 3, 12)
        assert durand.birth_last_name == "DURAND"
        assert durand.level.code == "CERTIFIE"
        assert durand.function.code == "ENS"

    def test_grade_inconnu_cree_la_ligne_de_referentiel(self, db_session):
        """Le référentiel ne connaît pas « CERTIFIE » au départ : perdre l'information serait pire
        que d'ajouter une ligne, que l'utilisateur pourra renommer."""
        from backend.app.models.ref_level import RefLevel
        assert db_session.query(RefLevel).filter(RefLevel.code == "CERTIFIE").first() is None
        _import(db_session)
        assert db_session.query(RefLevel).filter(RefLevel.code == "CERTIFIE").first() is not None

    def test_discipline_prend_le_libelle_du_flux(self, db_session):
        """Avant, le nom recevait le code recopié alors que le libellé est dans le fichier."""
        _import(db_session)
        allemand = db_session.query(Discipline).filter(Discipline.code == "030101").one()
        assert allemand.name == "ALLEMAND"


class TestGroupesRattachesAuxClasses:
    def test_libelle_long_conserve(self, db_session):
        _import(db_session)
        groupe = db_session.query(Group).filter(Group.name == "6LV1.ALL").one()
        assert groupe.long_name == "6EME ALLEMAND LV1"

    def test_une_partition_et_une_partie_par_classe_rattachee(self, db_session):
        """Le flux dit seulement « ce groupe puise dans cette classe » : on matérialise une
        partition ne contenant que la partie de ce groupe."""
        from backend.app.models.group import ClassPart, Partition
        _import(db_session)
        groupe = db_session.query(Group).filter(Group.name == "6LV1.ALL").one()
        assert len(groupe.class_parts) == 1
        partie = groupe.class_parts[0]
        assert partie.name == "6LV1.ALL"
        assert partie.division_id == db_session.query(Division).filter(Division.code == "6E1").first().id
        partition = db_session.get(Partition, partie.partition_id)
        assert len(partition.class_parts) == 1

    def test_second_import_ne_duplique_ni_partition_ni_partie(self, db_session):
        from backend.app.models.group import ClassPart, Partition
        _import(db_session)
        avant = (db_session.query(Partition).count(), db_session.query(ClassPart).count())
        _import(db_session)
        assert (db_session.query(Partition).count(), db_session.query(ClassPart).count()) == avant


class TestProgrammes:
    """`NOMENCLATURES/PROGRAMMES` porte l'horaire hebdomadaire d'un couple (MEF, matière). La
    section est prouvée dans Nomenclature.xml (SIECLE) mais n'a jamais été observée dans un
    sts_emp : on la lit si elle est là, sans en dépendre."""

    def _flux_avec_programmes(self, horaire="4.00"):
        return {
            "filename": "sts_emp_0750001A_2026.xml", "mime_type": "text/xml",
            "data_base64": base64.b64encode(
                b'<STS_EDT><PARAMETRES><UAJ CODE="0750001A"/><ANNEE_SCOLAIRE ANNEE="2026"/></PARAMETRES>'
                b"<NOMENCLATURES><MATIERES>"
                b'<MATIERE CODE="030101"><CODE_GESTION>ALL</CODE_GESTION>'
                b"<LIBELLE_COURT>ALLEMAND</LIBELLE_COURT></MATIERE></MATIERES>"
                b'<MEFS><MEF CODE="10010012110"><LIBELLE_COURT>6EME</LIBELLE_COURT></MEF></MEFS>'
                b"<PROGRAMMES><PROGRAMME><CODE_MEF>10010012110</CODE_MEF>"
                b"<CODE_MATIERE>030101</CODE_MATIERE><CODE_MODALITE_ELECT>S</CODE_MODALITE_ELECT>"
                b"<HORAIRE>" + horaire.encode() + b"</HORAIRE></PROGRAMME></PROGRAMMES>"
                b"</NOMENCLATURES><DONNEES><INDIVIDUS>"
                b'<INDIVIDU ID="8949"><NOM_USAGE>DURAND</NOM_USAGE>'
                b'<DISCIPLINES><DISCIPLINE CODE="030101"/></DISCIPLINES></INDIVIDU></INDIVIDUS>'
                b'<STRUCTURE><DIVISIONS><DIVISION CODE="6E1"><SERVICES>'
                b'<SERVICE CODE_MATIERE="030101"><ENSEIGNANTS><ENSEIGNANT ID="8949"/></ENSEIGNANTS>'
                b'</SERVICE></SERVICES><MEFS_APPARTENANCE><MEF CODE="10010012110"/>'
                b"</MEFS_APPARTENANCE></DIVISION></DIVISIONS></STRUCTURE></DONNEES></STS_EDT>"
            ).decode("ascii"),
        }

    def _importe(self, db, fichier):
        ana = _wizard().rpc_analyze(db, sts_file=fichier)
        return _wizard().rpc_import(
            db, sts_file=fichier, mef_rows=ana["mef_rows"], subject_rows=ana["subject_rows"],
            **_selection(import_services=True),
        )

    def test_l_horaire_alimente_le_gabarit(self, db_session):
        self._importe(db_session, self._flux_avec_programmes("4.00"))
        gabarit = db_session.query(MefService).one()
        assert gabarit.weekly_duration_full_class_minutes == 240
        assert gabarit.total_weekly_duration_minutes == 240

    def test_la_modalite_d_election_est_reprise(self, db_session):
        from backend.app.models.ref_election_method import RefElectionMethod
        methode = RefElectionMethod.create(db_session, {"code": "S", "name": "Tronc commun", "export_code": "TC"})
        self._importe(db_session, self._flux_avec_programmes())
        assert db_session.query(MefService).one().election_method_id == methode.id

    def test_horaire_arrondi_au_pas_horaire(self, db_session):
        """1h10 n'est pas un multiple du pas de 30 min : la contrainte du modèle le refuserait."""
        self._importe(db_session, self._flux_avec_programmes("1.17"))
        assert db_session.query(MefService).one().weekly_duration_full_class_minutes == 60

    def test_sans_programmes_le_gabarit_reste_a_zero(self, db_session):
        """Cas de repli : la section est facultative, et aucun sts_emp réel n'a été observé qui
        la porte. Flux synthétique, puisque les fichiers d'exemple en ont désormais une."""
        sans = {
            "filename": "sts_emp_0750001A_2026.xml", "mime_type": "text/xml",
            "data_base64": base64.b64encode(
                b'<STS_EDT><PARAMETRES><UAJ CODE="0750001A"/><ANNEE_SCOLAIRE ANNEE="2026"/></PARAMETRES>'
                b"<NOMENCLATURES><MATIERES>"
                b'<MATIERE CODE="030101"><CODE_GESTION>ALL</CODE_GESTION>'
                b"<LIBELLE_COURT>ALLEMAND</LIBELLE_COURT></MATIERE></MATIERES>"
                b'<MEFS><MEF CODE="10010012110"><LIBELLE_COURT>6EME</LIBELLE_COURT></MEF></MEFS>'
                b"</NOMENCLATURES><DONNEES><INDIVIDUS>"
                b'<INDIVIDU ID="8949"><NOM_USAGE>DURAND</NOM_USAGE>'
                b'<DISCIPLINES><DISCIPLINE CODE="030101"/></DISCIPLINES></INDIVIDU></INDIVIDUS>'
                b'<STRUCTURE><DIVISIONS><DIVISION CODE="6E1"><SERVICES>'
                b'<SERVICE CODE_MATIERE="030101"><ENSEIGNANTS><ENSEIGNANT ID="8949"/></ENSEIGNANTS>'
                b'</SERVICE></SERVICES><MEFS_APPARTENANCE><MEF CODE="10010012110"/>'
                b"</MEFS_APPARTENANCE></DIVISION></DIVISIONS></STRUCTURE></DONNEES></STS_EDT>"
            ).decode("ascii"),
        }
        self._importe(db_session, sans)
        assert db_session.query(MefService).one().total_weekly_duration_minutes == 0


class TestServicesDeGroupeSignales:
    def test_le_nombre_total_est_annonce(self, db_session):
        res = _import(db_session, import_services=True)
        assert "Services</strong> — 2 objet(s)" in res["result_html"]
        assert "porté par un groupe" in res["result_html"]
