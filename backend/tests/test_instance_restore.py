"""
`POST /api/instance/admin/databases/{slug}/restore` (api/instance_endpoints.py) — la route la plus
destructive de l'application, et la seule qui avait la forme d'une cible CSRF tant qu'elle
acceptait un envoi multipart (voir la docstring de l'endpoint).

Les opérations physiques (db_admin_ops) sont substituées : ce qui est vérifié ici, c'est le CONTRAT
HTTP (format du corps, confirmation, refus d'un fichier qui n'en est pas un), pas l'écriture disque
— déjà couverte manuellement (voir test_instance_admin.py, docstring du module).
"""
import base64
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core import db_admin_ops, db_registry
from backend.app.core.instance_admin import require_admin_of
from backend.app.core.instance_session import InstanceSession

SQLITE_HEADER = b"SQLite format 3\x00" + b"reste du fichier"


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[require_admin_of] = lambda: InstanceSession(provider_key="educonnect", subject="admin")
    monkeypatch.setattr(db_registry, "is_known_slug", lambda slug: slug == "college-a")
    yield TestClient(app)
    app.dependency_overrides.pop(require_admin_of, None)


@pytest.fixture
def restored(monkeypatch):
    """Capture ce qui SERAIT écrit, sans jamais toucher au disque."""
    calls = []
    monkeypatch.setattr(db_admin_ops, "restore_database", lambda slug, content: calls.append((slug, content)))
    return calls


def _payload(content: bytes, confirm="college-a"):
    return {
        "confirm": confirm,
        "file": {
            "filename": "sauvegarde.db",
            "mime_type": "application/octet-stream",
            "data_base64": base64.b64encode(content).decode("ascii"),
        },
    }


class TestRestoreContract:
    def test_valid_json_payload_is_accepted_and_decoded(self, client, restored):
        response = client.post("/api/instance/admin/databases/college-a/restore", json=_payload(SQLITE_HEADER))

        assert response.status_code == 200
        assert restored == [("college-a", SQLITE_HEADER)]

    def test_confirmation_must_match_the_slug(self, client, restored):
        response = client.post(
            "/api/instance/admin/databases/college-a/restore",
            json=_payload(SQLITE_HEADER, confirm="college-b"),
        )

        assert response.status_code == 400
        assert restored == []

    def test_unknown_database_is_a_404(self, client, restored):
        response = client.post("/api/instance/admin/databases/inconnue/restore", json=_payload(SQLITE_HEADER))

        assert response.status_code == 404
        assert restored == []

    def test_invalid_base64_is_rejected_before_any_write(self, client, restored):
        payload = _payload(SQLITE_HEADER)
        payload["file"]["data_base64"] = "ceci n'est pas du base64 !!"

        response = client.post("/api/instance/admin/databases/college-a/restore", json=payload)

        assert response.status_code == 400
        assert restored == []

    def test_multipart_upload_is_no_longer_accepted(self, client, restored):
        """La forme CSRF-able (type de contenu "simple", aucun préflight) ne doit plus exister —
        voir la docstring de l'endpoint."""
        response = client.post(
            "/api/instance/admin/databases/college-a/restore?confirm=college-a",
            files={"file": ("sauvegarde.db", SQLITE_HEADER)},
        )

        assert response.status_code == 422  # corps JSON attendu
        assert restored == []


class TestRestoreFormatGuard:
    """db_admin_ops.assert_restorable — appelé AVANT toute écriture (voir restore_database)."""

    def test_a_file_that_is_not_a_backup_is_refused(self):
        with pytest.raises(ValueError, match="SQLite"):
            db_admin_ops.assert_restorable(b"%PDF-1.7 ceci est un bulletin, pas une sauvegarde")

    def test_a_real_sqlite_file_passes(self):
        db_admin_ops.assert_restorable(SQLITE_HEADER)  # ne lève rien
