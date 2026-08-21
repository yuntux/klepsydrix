"""
En-têtes de sécurité (core/security_headers.py). Rappel de portée : ces en-têtes valent pour les
réponses de l'API, pas pour l'IHM — la CSP qui protège la page HTML doit être servie avec
index.html (voir la docstring du module et architecture.md §20.C).
"""
from fastapi.testclient import TestClient

from backend.app.core.security_headers import API_CSP
from backend.app.main import app

client = TestClient(app)


def test_api_response_carries_the_security_headers():
    response = client.get("/")  # healthcheck : aucune session requise

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "same-origin"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["content-security-policy"] == API_CSP


def test_interactive_documentation_keeps_working():
    """Swagger UI est une vraie page HTML qui charge ses scripts depuis un CDN : `default-src
    'none'` la rendrait blanche. La documentation reste un outil de travail du projet."""
    response = client.get("/api/docs")

    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"  # les autres restent posés
