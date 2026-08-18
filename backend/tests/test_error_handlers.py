"""
Tests de la traduction HTTP des exceptions métier (core/error_handlers.py) — voir architecture.md
§18.J. Exercés sur une app FastAPI jetable : c'est la raison d'être de
`register_exception_handlers()` en tant que fonction séparée, et ça évite d'ajouter des routes
factices à l'application réelle (que le garde-fou de routage refuserait, à juste titre).

Le test qui compte le plus est le dernier : une exception INATTENDUE doit produire un 500, pas un
400. C'est précisément ce que l'ancien `except Exception` fourre-tout des endpoints génériques
empêchait — un bug serveur y était annoncé au client comme une erreur de saisie.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from backend.app.core.error_handlers import register_exception_handlers
from backend.app.core.exclusive_mode import ExclusiveModeActiveError
from backend.app.models.base import AccessDeniedError, UnsupportedOperationError
from backend.app.models.composition_mode import CompositionError


def _app_raising(exception):
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boum")
    def boum():
        raise exception

    return app


@pytest.mark.parametrize("exception, expected_status", [
    (AccessDeniedError("Droit « write » refusé sur courses."), 403),
    (UnsupportedOperationError("Création interdite sur ce modèle."), 405),
    (ExclusiveModeActiveError("Une résolution est en cours."), 423),
    (CompositionError("Composition de cours invalide."), 400),
    (ValueError("Une salle ne peut pas être son propre groupe parent."), 400),
])
def test_business_exceptions_are_mapped(exception, expected_status):
    """Le message métier est renvoyé tel quel : il est écrit pour être lu par l'utilisateur."""
    response = TestClient(_app_raising(exception)).get("/boum")
    assert response.status_code == expected_status
    assert response.json() == {"detail": str(exception)}


def test_integrity_error_is_400_and_does_not_leak_sql():
    """
    `str(IntegrityError)` contient la requête et ses paramètres. Journalisé, jamais renvoyé : un
    message d'erreur ne doit pas exposer le schéma de la base.
    """
    exception = IntegrityError(
        "INSERT INTO schools (uai, name) VALUES (?, ?)",
        {"uai": "1234567A"},
        Exception("UNIQUE constraint failed: schools.uai"),
    )
    response = TestClient(_app_raising(exception)).get("/boum")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "INSERT INTO" not in detail
    assert "1234567A" not in detail


def test_unexpected_exception_is_500_not_400():
    """
    Le cœur de la correction : un bug serveur doit rester un bug serveur. L'ancien `except
    Exception` des endpoints génériques renvoyait 400 « erreur de création » sur n'importe quel
    AttributeError/KeyError — le client croyait avoir mal saisi, et rien ne remontait en
    supervision.
    """
    app = _app_raising(KeyError("champ_inexistant"))
    # raise_server_exceptions=False : on veut observer la RÉPONSE HTTP, pas voir l'exception
    # remonter dans le test comme le ferait le client TestClient par défaut.
    response = TestClient(app, raise_server_exceptions=False).get("/boum")
    assert response.status_code == 500


def test_subclass_of_a_mapped_exception_is_mapped_too():
    """
    Starlette résout par la classe la plus spécifique enregistrée : une sous-classe d'une exception
    métier hérite donc de sa traduction, sans rien à déclarer.
    """
    class DomaineSpecifiqueError(ValueError):
        pass

    response = TestClient(_app_raising(DomaineSpecifiqueError("Effectif négatif."))).get("/boum")
    assert response.status_code == 400
