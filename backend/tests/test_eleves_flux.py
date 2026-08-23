"""
Tests du parseur des flux SIECLE descendants élèves/responsables
(backend/app/core/eleves_flux.py).

Module pur, sans base : ces tests ne montent aucune session. Les fichiers de
backend/tests/fixtures/ sont repris de exemple1/ du dossier d'analyse XML_STS_SCONET.
"""
import pathlib
import pytest

from backend.app.core.eleves_flux import (
    ElevesFluxError, parse_eleves, parse_responsables, ElevesFlux, ResponsablesFlux,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _eleves() -> ElevesFlux:
    return parse_eleves((FIXTURES / "ElevesAvecAdresses_0750001A_2026.xml").read_bytes())


def _responsables() -> ResponsablesFlux:
    return parse_responsables((FIXTURES / "ResponsablesAvecAdresses_0750001A_2026.xml").read_bytes())


class TestParseEleves:
    def test_en_tete(self):
        flux = _eleves()
        assert flux.uai == "0750001A"
        assert flux.school_year == 2026
        assert flux.date_export == "19/05/2026"
        assert flux.horodatage == "19/05/2026 08:30:00"

    def test_deux_eleves(self):
        flux = _eleves()
        assert flux.counts()["students"] == 2

    def test_identite_et_scolarite(self):
        flux = _eleves()
        martin = next(e for e in flux.students if e["eleve_id"] == "10001")
        assert martin["last_name"] == "MARTIN"
        assert martin["first_name"] == "Jean"
        assert martin["birth_date"] == "15/04/2015"
        assert martin["sexe"] == "1"
        assert martin["mef_code"] == "10010012110"
        assert martin["division_code"] == "6E1"
        assert martin["group_codes"] == ["6LV1.ALL"]
        assert martin["regime_code"] == "DP"
        assert martin["birth_city_insee_code"] == "75101"

    def test_scolarite_an_dernier(self):
        flux = _eleves()
        martin = next(e for e in flux.students if e["eleve_id"] == "10001")
        assert martin["last_year"]["level"] == "CM2"
        assert martin["last_year"]["rne_code"] == "0759999Z"
        assert martin["last_year"]["city_insee_code"] == "75101"

    def test_options(self):
        flux = _eleves()
        martin = next(e for e in flux.students if e["eleve_id"] == "10001")
        assert martin["options"] == [{"num_option": "1", "election_code": "O", "subject_code": "030101"}]

    def test_racine_totalement_inconnue_rejetee(self):
        with pytest.raises(ElevesFluxError, match="BEE_ELEVES"):
            parse_eleves(b"<AUTRE_CHOSE><PARAMETRES/></AUTRE_CHOSE>")

    def test_racine_communs_rejetee_avec_message_explicite(self):
        with pytest.raises(ElevesFluxError, match="Communs.xml"):
            parse_eleves(b"<BEE_COMMUN><PARAMETRES/></BEE_COMMUN>")

    def test_fichier_responsables_rejete_avec_message_explicite(self):
        with pytest.raises(ElevesFluxError, match="(?i)responsables"):
            parse_eleves((FIXTURES / "ResponsablesAvecAdresses_0750001A_2026.xml").read_bytes())

    def test_xml_invalide_rejete(self):
        with pytest.raises(ElevesFluxError, match="XML"):
            parse_eleves(b"ceci n'est pas du XML")

    def test_sans_uaj_rejete(self):
        with pytest.raises(ElevesFluxError, match="code établissement"):
            parse_eleves(b"<BEE_ELEVES><DONNEES/></BEE_ELEVES>")


class TestParseResponsables:
    def test_en_tete(self):
        flux = _responsables()
        assert flux.uai == "0750001A"
        assert flux.school_year == 2026

    def test_deux_personnes(self):
        flux = _responsables()
        assert flux.counts()["persons"] == 2
        martin = flux.persons["50001"]
        assert martin["last_name"] == "MARTIN"
        assert martin["first_name"] == "Pierre"
        assert martin["civilite"] == "M."
        assert martin["mobile_phone"] == "0699887766"
        assert martin["adresse_id"] == "20001"
        assert martin["job_code"] == "42"

    def test_adresses(self):
        flux = _responsables()
        assert flux.addresses["20001"]["address_line1"] == "45 RUE DE RIVOLI"
        assert flux.addresses["20001"]["zip_code"] == "75001"
        assert flux.addresses["20001"]["country_name"] == "FRANCE"

    def test_liens(self):
        flux = _responsables()
        assert flux.counts()["links"] == 2
        lien = next(l for l in flux.links if l["eleve_id"] == "10001")
        assert lien["personne_id"] == "50001"
        assert lien["resp_legal_code"] == "1"
        assert lien["pays_school_fees"] == "1"

    def test_fichier_eleves_rejete_avec_message_explicite(self):
        with pytest.raises(ElevesFluxError, match="(?i)élèves"):
            parse_responsables((FIXTURES / "ElevesAvecAdresses_0750001A_2026.xml").read_bytes())
