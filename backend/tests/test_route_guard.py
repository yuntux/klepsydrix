"""
Tests du garde-fou de portée des routes (core/route_guard.py) — voir architecture.md, moteur de
droits. Deux niveaux :

1. Le garde-fou fait bien son travail : une route non authentifiée et non marquée fait échouer le
   contrôle (sinon le garde-fou lui-même pourrait être cassé sans que rien ne le signale) ;
2. L'application réelle le passe, et pour les bonnes raisons — chaque dérogation est explicite.
"""
import pytest
from fastapi import Depends, FastAPI

from backend.app.core.database import current_db_user
from backend.app.core.instance_session import require_instance_session
from backend.app.core.route_guard import assert_all_routes_scoped, system_scoped


def test_route_non_protegee_fait_echouer_le_controle():
    """Le cas que le garde-fou existe pour attraper : un routeur monté sans dépendance de portée."""
    app = FastAPI()

    @app.get("/api/fuite")
    def fuite():
        return {}

    with pytest.raises(RuntimeError) as exc:
        assert_all_routes_scoped(app)
    assert "/api/fuite" in str(exc.value)


def test_route_protegee_par_current_db_user_passe():
    app = FastAPI()

    @app.get("/api/donnees", dependencies=[Depends(current_db_user)])
    def donnees():
        return {}

    assert_all_routes_scoped(app)


def test_dependance_posee_sur_le_routeur_est_vue():
    """
    Cas réel de l'application : les endpoints de generic.py ne déclarent que Depends(get_db), la
    protection vient de include_router(dependencies=[...]). Si le parcours ne voyait pas ce niveau,
    le garde-fou refuserait de démarrer sur 800+ routes pourtant correctes.
    """
    from fastapi import APIRouter

    app = FastAPI()
    router = APIRouter(prefix="/api/generique")

    @router.get("/chose")
    def chose():
        return {}

    app.include_router(router, dependencies=[Depends(current_db_user)])
    assert_all_routes_scoped(app)


def test_route_de_portee_instance_passe():
    """L'administration de l'instance n'agit sur aucune ligne : require_instance_session suffit."""
    app = FastAPI()

    @app.get("/api/instance/chose", dependencies=[Depends(require_instance_session)])
    def chose():
        return {}

    assert_all_routes_scoped(app)


def test_marqueur_system_scoped_dispense():
    app = FastAPI()

    @app.get("/api/auth/quelque-chose")
    @system_scoped("Authentification : ne peut pas exiger une session.")
    def sans_session():
        return {}

    assert_all_routes_scoped(app)


def test_application_reelle_passe_le_controle():
    """Le contrat de démarrage lui-même : `import main` + contrôle, sans lever."""
    from backend.app.main import app
    assert_all_routes_scoped(app)


def test_inventaire_des_derogations():
    """
    Verrouille la LISTE des routes dispensées : ajouter un @system_scoped devient un acte
    délibéré qui casse ce test, plutôt qu'une ligne qui passe inaperçue en revue. Chaque entrée
    ici est une route qui s'exécute sans moteur de droits — la liste doit rester courte et
    n'appartenir qu'à l'authentification (+ healthcheck + sélecteur de base).
    """
    from fastapi.routing import APIRoute
    from backend.app.main import app

    derogations = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and getattr(route.endpoint, "_system_scoped_reason", None)
    }
    assert derogations == {
        "/",
        "/api/auth/providers",
        "/api/auth/login/local",
        "/api/auth/login/master",
        "/api/auth/logout",
        "/api/auth/password-reset/request",
        "/api/auth/password-reset/confirm",
        "/api/auth/oidc/login/{provider_key}",
        "/api/auth/oidc/callback/{provider_key}",
        # `/api/instance/databases` a été SUPPRIMÉE : elle servait la liste de tous les
        # établissements hébergés à n'importe quel anonyme. Le sélecteur passe désormais par
        # `/api/instance/my-databases`, sous session (voir instance_admin.py).
    }


def test_toute_derogation_est_motivee():
    """Un @system_scoped("") passerait le test précédent — la raison doit être réellement écrite."""
    from fastapi.routing import APIRoute
    from backend.app.main import app

    for route in app.routes:
        if isinstance(route, APIRoute):
            raison = getattr(route.endpoint, "_system_scoped_reason", None)
            if raison is not None:
                assert len(raison.strip()) > 20, f"Dérogation non motivée sur {route.path}"
