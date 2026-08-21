"""
Tests du parseur de flux STS-web descendant (backend/app/core/sts_flux.py).

Module pur, sans base : ces tests ne montent aucune session. Les fichiers de
backend/tests/fixtures/ sont issus d'analyses faites sur le code source de GEPI et CDT.
"""
import pathlib
# pyrefly: ignore [missing-import]
import pytest

from backend.app.core.sts_flux import parse, StsFlux, StsFluxError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _flux() -> StsFlux:
    return parse((FIXTURES / "sts_emp_0750001A_2026.xml").read_bytes())


class TestEnTete:
    def test_uai_et_annee_sont_lus(self):
        flux = _flux()
        assert flux.uai == "0750001A"
        assert flux.school_year == 2026
        assert flux.school_name == "COLLEGE CLAUDE BERNARD"

    def test_fichier_montant_rejete_avec_un_message_explicite(self):
        """La confusion entre les deux sens est l'erreur la plus courante : leurs noms sont
        anagrammes l'un de l'autre. Le message doit nommer le fichier attendu."""
        with pytest.raises(StsFluxError) as exc:
            parse((FIXTURES / "emp_sts_0750001A_2026.xml").read_bytes())
        assert "sts_emp" in str(exc.value)

    def test_racine_inconnue_rejetee(self):
        with pytest.raises(StsFluxError, match="STS_EDT"):
            parse(b"<BEE_COMMUN><PARAMETRES/></BEE_COMMUN>")

    def test_xml_invalide_rejete(self):
        with pytest.raises(StsFluxError, match="XML"):
            parse(b"ceci n'est pas du XML")

    def test_sans_uaj_rejete(self):
        with pytest.raises(StsFluxError, match="code établissement"):
            parse(b"<STS_EDT><DONNEES/></STS_EDT>")

    def test_sans_annee_rejete(self):
        with pytest.raises(StsFluxError, match="année scolaire"):
            parse(b'<STS_EDT><PARAMETRES><UAJ CODE="0750001A"/></PARAMETRES><DONNEES/></STS_EDT>')


class TestNomenclatures:
    def test_matieres(self):
        flux = _flux()
        assert flux.counts()["subjects"] == 2
        allemand = next(s for s in flux.subjects if s["code_nomenclature"] == "030101")
        assert allemand["code_gestion"] == "ALLEMAND"
        assert allemand["short_name"] == "ALLEMAND LV1"
        assert allemand["name"] == "ALLEMAND PREMIERE LANGUE"

    def test_seuls_les_mef_de_nomenclature_sont_retenus(self):
        """MEF apparaît à deux endroits : en nomenclature avec ses libellés, et sous
        DIVISION/MEFS_APPARTENANCE réduit à son seul code. Seul le premier est un MEF à créer."""
        flux = _flux()
        assert flux.counts()["mefs"] == 1
        assert flux.mefs[0] == {"code_national": "10010012110", "name": "6EME"}


class TestIndividus:
    def test_enseignants(self):
        flux = _flux()
        assert flux.counts()["teachers"] == 2
        durand = next(t for t in flux.teachers if t["epp_id"] == "8949")
        assert durand["last_name"] == "DURAND"
        assert durand["first_name"] == "Michel"
        assert durand["birth_date"] == "1975-03-12"
        assert durand["discipline_codes"] == ["030101"]

    def test_professeur_principal(self):
        flux = _flux()
        durand = next(t for t in flux.teachers if t["epp_id"] == "8949")
        assert durand["main_teacher_of"] == ["6E1"]
        petit = next(t for t in flux.teachers if t["epp_id"] == "8950")
        assert petit["main_teacher_of"] == []

    def test_type_epp_par_defaut(self):
        assert _flux().teachers[0]["is_epp"] is True

    def test_type_local_reconnu(self):
        flux = parse(
            b'<STS_EDT><PARAMETRES><UAJ CODE="0750001A"/>'
            b'<ANNEE_SCOLAIRE ANNEE="2026"/></PARAMETRES>'
            b'<DONNEES><INDIVIDUS><INDIVIDU ID="99" TYPE="local">'
            b"<NOM_USAGE>REMPLACANT</NOM_USAGE></INDIVIDU></INDIVIDUS></DONNEES></STS_EDT>"
        )
        assert flux.teachers[0]["is_epp"] is False


class TestStructure:
    def test_divisions_et_services(self):
        flux = _flux()
        assert flux.counts()["divisions"] == 1
        division = flux.divisions[0]
        assert division["code"] == "6E1"
        assert division["mef_codes"] == ["10010012110"]
        assert division["services"] == [
            {"code_nomenclature": "030101", "modality_code": "CG", "teacher_epp_ids": ["8949"]}
        ]

    def test_groupes(self):
        flux = _flux()
        assert flux.counts()["groups"] == 2
        groupe = next(g for g in flux.groups if g["code"] == "6LV1.ALL")
        assert groupe["name"] == "6EME ALLEMAND LV1"
        assert groupe["division_codes"] == ["6E1"]
        assert groupe["services"][0]["teacher_epp_ids"] == ["8949"]

    def test_une_seule_division_rattachee_signifie_groupe(self):
        """Le cardinal de DIVISIONS_APPARTENANCE porte à lui seul la nature du groupe : aucune
        balise ne la déclare. Une division rattachée = portion de classe."""
        assert all(g["is_regroupement"] is False for g in _flux().groups)

    def test_deux_divisions_rattachees_signifient_regroupement(self):
        flux = parse(
            b'<STS_EDT><PARAMETRES><UAJ CODE="0750001A"/>'
            b'<ANNEE_SCOLAIRE ANNEE="2026"/></PARAMETRES><DONNEES><STRUCTURE><GROUPES>'
            b'<GROUPE CODE="6LV1.ALL"><DIVISIONS_APPARTENANCE>'
            b'<DIVISION_APPARTENANCE CODE="6E1"/><DIVISION_APPARTENANCE CODE="6E2"/>'
            b'</DIVISIONS_APPARTENANCE><SERVICES><SERVICE CODE_MATIERE="030101"/></SERVICES>'
            b"</GROUPE></GROUPES></STRUCTURE></DONNEES></STS_EDT>"
        )
        groupe = flux.groups[0]
        assert groupe["division_codes"] == ["6E1", "6E2"]
        assert groupe["is_regroupement"] is True

    def test_modalite_absente_vaut_none(self):
        """CODE_MOD_COURS est facultatif ; c'est à l'import de retomber sur CG, pas au parseur
        d'inventer une valeur."""
        flux = parse(
            b'<STS_EDT><PARAMETRES><UAJ CODE="0750001A"/>'
            b'<ANNEE_SCOLAIRE ANNEE="2026"/></PARAMETRES><DONNEES><STRUCTURE><DIVISIONS>'
            b'<DIVISION CODE="6E1"><SERVICES><SERVICE CODE_MATIERE="030101"/></SERVICES>'
            b"</DIVISION></DIVISIONS></STRUCTURE></DONNEES></STS_EDT>"
        )
        assert flux.divisions[0]["services"][0]["modality_code"] is None


class TestProgrammes:
    """`NOMENCLATURES/PROGRAMMES` associe un MEF à une matière, avec son horaire hebdomadaire.
    Section facultative : prouvée dans Nomenclature.xml (SIECLE), jamais observée dans un sts_emp
    réel, mais déclarée au schéma et portée par les fichiers d'exemple."""

    def test_programmes_du_fichier(self):
        flux = _flux()
        assert flux.counts()["programmes"] == 2
        allemand = next(p for p in flux.programmes if p["code_nomenclature"] == "030101")
        assert allemand["code_national"] == "10010012110"
        assert allemand["election_code"] == "O"
        assert allemand["horaire"] == "4.00"

    def test_les_couples_sont_coherents_avec_les_nomenclatures(self):
        """Chaque programme référence un MEF et une matière effectivement déclarés dans le même
        fichier — c'est ce qui rend l'exemple exploitable de bout en bout."""
        flux = _flux()
        mefs = {m["code_national"] for m in flux.mefs}
        matieres = {s["code_nomenclature"] for s in flux.subjects}
        for programme in flux.programmes:
            assert programme["code_national"] in mefs
            assert programme["code_nomenclature"] in matieres

    def test_section_absente_donne_une_liste_vide(self):
        flux = parse(
            b'<STS_EDT><PARAMETRES><UAJ CODE="0750001A"/>'
            b'<ANNEE_SCOLAIRE ANNEE="2026"/></PARAMETRES><DONNEES/></STS_EDT>'
        )
        assert flux.programmes == []
        assert flux.counts()["programmes"] == 0
