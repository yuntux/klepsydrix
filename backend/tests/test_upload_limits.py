"""
Plafond de taille des corps de requête (core/upload_limits.py) et durcissement de l'analyse XML
(core/sts_flux.py). Réunis ici parce qu'ils couvrent le même risque : un fichier fourni par
l'utilisateur qui coûte au serveur bien plus que sa propre taille.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.config import ServerConfig, settings
from backend.app.core.sts_flux import parse, StsFluxError
from backend.app.core.upload_limits import ContentLengthLimitMiddleware, assert_within_limit


@pytest.fixture(autouse=True)
def _small_limits():
    original = settings.server
    settings.server = ServerConfig(max_upload_mb=1, max_restore_upload_mb=5)
    yield
    settings.server = original


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(ContentLengthLimitMiddleware)

    @app.post("/api/generic/teachers")
    def create():
        return {"status": "ok"}

    @app.post("/api/instance/admin/databases/college-a/restore")
    def restore():
        return {"status": "ok"}

    return TestClient(app)


class TestContentLengthLimit:
    def test_an_ordinary_body_passes(self, client):
        assert client.post("/api/generic/teachers", content=b"x" * 1024).status_code == 200

    def test_an_oversized_body_is_refused_with_413(self, client):
        response = client.post("/api/generic/teachers", content=b"x" * (2 * 1024 * 1024))

        assert response.status_code == 413
        assert "1 Mo" in response.json()["detail"]

    def test_restore_has_its_own_larger_limit(self, client):
        """Une sauvegarde d'établissement pèse légitimement bien plus qu'une photo."""
        body = b"x" * (2 * 1024 * 1024)  # au-delà du plafond ordinaire, sous celui de restore

        assert client.post("/api/instance/admin/databases/college-a/restore", content=body).status_code == 200

    def test_the_restore_limit_is_not_unlimited(self, client):
        response = client.post(
            "/api/instance/admin/databases/college-a/restore",
            content=b"x" * (6 * 1024 * 1024),
        )
        assert response.status_code == 413


class TestPerFieldMessage:
    def test_says_which_file_is_too_large(self):
        with pytest.raises(ValueError, match="Le fichier STS-web"):
            assert_within_limit(b"x" * (2 * 1024 * 1024), "Le fichier STS-web")

    def test_a_file_within_the_limit_is_returned_unchanged(self):
        data = b"contenu"
        assert assert_within_limit(data) is data


class TestXmlHardening:
    def test_an_entity_expansion_bomb_is_refused(self):
        """« Billion laughs » : quelques centaines d'octets, des gigaoctets de mémoire après
        expansion — le plafond de taille ne peut rien y voir, il mesure le fichier."""
        bomb = b"""<?xml version="1.0"?>
        <!DOCTYPE STS_EDT [
          <!ENTITY a "aaaaaaaaaa">
          <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
          <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
        ]>
        <STS_EDT>&c;</STS_EDT>"""

        with pytest.raises(StsFluxError):
            parse(bomb)

    def test_a_malformed_document_still_reports_clearly(self):
        with pytest.raises(StsFluxError, match="XML valide"):
            parse(b"<STS_EDT><PARAMETRES>")
