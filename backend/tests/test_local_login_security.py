"""
Tests pour la journalisation de `POST /api/auth/login/local` (voir architecture.md §17.H,
api/auth_endpoints.py). AUCUN verrouillage applicatif ici (décision explicite, voir §17.H) : la
protection anti-brute-force est entièrement déléguée à fail2ban, qui lit ce journal — voir
`test_fail2ban_filter_contracts.py` pour la vérification que le FORMAT de ces lignes correspond
bien au filtre fail2ban réellement déployé.
"""
import logging
import pytest
from fastapi import HTTPException, Response
from sqlalchemy.orm import sessionmaker

from backend.app.models.base import Base
from backend.app.models import User, UserIdentityProvider
from backend.tests.db_test_utils import make_test_engine
from backend.app.api.auth_endpoints import LocalLoginPayload, login_local

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, host="203.0.113.1", headers=None):
        self.client = _FakeClient(host)
        self.headers = headers or {}


def _make_local_account(db, identifier="a@example.fr", password="correct-horse-battery"):
    user = User.create(db, {"first_name": "A", "last_name": "Local", "email": identifier})
    UserIdentityProvider.register_local_password(db, user.id, identifier, password)
    db.commit()


class TestLocalLoginLogging:
    def test_wrong_password_is_rejected(self, db_session):
        _make_local_account(db_session)
        request = _FakeRequest("198.51.100.9")

        with pytest.raises(HTTPException) as exc_info:
            login_local(LocalLoginPayload(identifier="a@example.fr", password="wrong"), request, Response(), db_session)
        assert exc_info.value.status_code == 401

    def test_correct_password_succeeds(self, db_session):
        _make_local_account(db_session)
        request = _FakeRequest("198.51.100.9")

        result = login_local(LocalLoginPayload(identifier="a@example.fr", password="correct-horse-battery"), request, Response(), db_session)

        assert result == {"status": "success"}

    def test_failed_attempt_is_logged_as_warning_with_ip(self, db_session, caplog):
        _make_local_account(db_session)
        request = _FakeRequest("198.51.100.9")

        with caplog.at_level(logging.WARNING, logger="backend.app.api.auth_endpoints"):
            with pytest.raises(HTTPException):
                login_local(LocalLoginPayload(identifier="a@example.fr", password="wrong"), request, Response(), db_session)

        assert any("Échec de connexion locale" in r.message and "198.51.100.9" in r.message for r in caplog.records)

    def test_successive_failed_attempts_are_all_logged_without_any_lockout(self, db_session, caplog):
        """Contrairement à l'ancien comportement (retiré, voir §17.H) : aucune tentative n'est
        jamais bloquée côté application, quel que soit le nombre d'échecs — chacune est journalisée
        pour que fail2ban puisse faire son travail, sans jamais renvoyer autre chose qu'un 401."""
        _make_local_account(db_session)
        request = _FakeRequest("198.51.100.9")

        with caplog.at_level(logging.WARNING, logger="backend.app.api.auth_endpoints"):
            for _ in range(20):
                with pytest.raises(HTTPException) as exc_info:
                    login_local(LocalLoginPayload(identifier="a@example.fr", password="wrong"), request, Response(), db_session)
                assert exc_info.value.status_code == 401  # jamais 403 : pas de verrouillage applicatif

        assert sum("Échec de connexion locale" in r.message for r in caplog.records) == 20

    def test_successful_attempt_is_not_logged_as_warning(self, db_session, caplog):
        """Une connexion réussie est le flux normal et quotidien — la journaliser en WARNING
        noierait le signal utile (voir docstring de login_local)."""
        _make_local_account(db_session)
        request = _FakeRequest("198.51.100.9")

        with caplog.at_level(logging.WARNING, logger="backend.app.api.auth_endpoints"):
            login_local(LocalLoginPayload(identifier="a@example.fr", password="correct-horse-battery"), request, Response(), db_session)

        assert len(caplog.records) == 0
