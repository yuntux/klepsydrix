"""
Contrôle d'origine sur les méthodes d'écriture (core/csrf.py). Ce que ces tests fixent, c'est la
FRONTIÈRE : ce qui doit passer (l'IHM légitime, les clients non-navigateur) et ce qui ne doit pas
(un site tiers qui ferait jouer le cookie de session de la victime).
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.config import ServerConfig, settings
from backend.app.core.csrf import OriginCheckMiddleware


@pytest.fixture
def client():
    """App jetable (pas `main.app`) : ce middleware doit être testable seul, sans authentification
    ni base — même approche que tests/test_route_guard.py."""
    app = FastAPI()
    app.add_middleware(OriginCheckMiddleware)

    @app.post("/ecrire")
    def ecrire():
        return {"status": "ok"}

    @app.get("/lire")
    def lire():
        return {"status": "ok"}

    return TestClient(app)


@pytest.fixture(autouse=True)
def _origins():
    original = settings.server
    settings.server = ServerConfig(allowed_origins=["http://localhost:3000"])
    yield
    settings.server = original


class TestUnsafeMethods:
    def test_a_third_party_origin_is_refused(self):
        app = FastAPI()
        app.add_middleware(OriginCheckMiddleware)

        @app.post("/ecrire")
        def ecrire():  # pragma: no cover — ne doit jamais être atteint
            return {"status": "ok"}

        response = TestClient(app).post("/ecrire", headers={"Origin": "https://site-malveillant.example"})

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "CROSS_ORIGIN_REFUSED"

    def test_a_configured_origin_is_accepted(self, client):
        response = client.post("/ecrire", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200

    def test_the_applications_own_origin_is_accepted_without_being_listed(self, client):
        """L'IHM et l'API partagent la même origine en développement (Vite proxifie /api) comme
        derrière un reverse proxy : cette origine n'a aucune raison de figurer dans
        `allowed_origins`, dont le rôle est d'autoriser les origines TIERCES."""
        response = client.post("/ecrire", headers={"Origin": "http://testserver", "Host": "testserver"})
        assert response.status_code == 200

    def test_referer_is_used_when_origin_is_absent(self, client):
        refused = client.post("/ecrire", headers={"Referer": "https://site-malveillant.example/piege.html"})
        assert refused.status_code == 403

        accepted = client.post("/ecrire", headers={"Referer": "http://localhost:3000/une/page"})
        assert accepted.status_code == 200

    def test_a_non_browser_client_passes(self, client):
        """Ni Origin ni Referer : ce n'est pas un navigateur, donc pas de cookie ambiant qu'un tiers
        pourrait faire jouer — refuser ici casserait curl, les scripts et les sondes sans rien
        protéger (voir docstring de core/csrf.py)."""
        response = client.post("/ecrire")
        assert response.status_code == 200


class TestSafeMethods:
    def test_a_read_from_any_origin_is_untouched(self, client):
        """Une lecture ne modifie rien ; c'est CORS, pas ce middleware, qui décide si la RÉPONSE est
        lisible par une origine tierce."""
        response = client.get("/lire", headers={"Origin": "https://site-malveillant.example"})
        assert response.status_code == 200
