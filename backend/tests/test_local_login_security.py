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
from starlette.requests import Request as StarletteRequest

from backend.app.models.base import Base
from backend.app.models import User, UserIdentityProvider
from backend.tests.db_test_utils import make_test_engine
from backend.app.api.auth_endpoints import LocalLoginPayload, login_local
from backend.app.core.config import settings
from backend.app.core.database import current_db_user
from backend.app.core.instance_session import (
    COOKIE_NAME, InstanceSession, require_instance_session, set_session_cookie,
)

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


def _make_local_account(db, identifier="a@example.fr", password="CorrectHorse8!"):
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

        result = login_local(LocalLoginPayload(identifier="a@example.fr", password="CorrectHorse8!"), request, Response(), db_session)

        assert result == {"status": "success"}

    def test_failed_attempt_is_logged_as_warning_with_ip(self, db_session, caplog):
        _make_local_account(db_session)
        request = _FakeRequest("198.51.100.9")

        with caplog.at_level(logging.WARNING, logger="backend.app.api.auth_endpoints"):
            with pytest.raises(HTTPException):
                login_local(LocalLoginPayload(identifier="a@example.fr", password="wrong"), request, Response(), db_session)

        assert any("Échec de connexion locale" in r.message and "198.51.100.9" in r.message for r in caplog.records)

    def test_every_failed_attempt_is_logged_for_fail2ban(self, db_session, caplog):
        """Le journal reste la matière première de fail2ban : chaque échec RETENU y figure, quel
        que soit le limiteur applicatif (voir core/rate_limit.py — les deux cohabitent, le limiteur
        ne remplace pas fail2ban, qui bannit plus tôt et pour toute la machine)."""
        _make_local_account(db_session)
        request = _FakeRequest("198.51.100.9")
        attempts = settings.auth.rate_limit_attempts

        with caplog.at_level(logging.WARNING, logger="backend.app.api.auth_endpoints"):
            for _ in range(attempts):
                with pytest.raises(HTTPException) as exc_info:
                    login_local(LocalLoginPayload(identifier="a@example.fr", password="wrong"), request, Response(), db_session)
                assert exc_info.value.status_code == 401

        assert sum("Échec de connexion locale" in r.message for r in caplog.records) == attempts

    def test_attempts_are_capped_by_the_application_itself(self, db_session):
        """
        Changement de doctrine assumé (voir core/rate_limit.py) : la protection anti-brute-force
        n'est plus ENTIÈREMENT déléguée à fail2ban. Elle l'était pour de bonnes raisons, mais de
        façon binaire — là où fail2ban n'est pas déployé (conteneur sans accès aux journaux de
        l'hôte, instance de démonstration, erreur d'installation silencieuse), il ne restait rien.
        """
        _make_local_account(db_session)
        request = _FakeRequest("198.51.100.9")

        for _ in range(settings.auth.rate_limit_attempts):
            with pytest.raises(HTTPException):
                login_local(LocalLoginPayload(identifier="a@example.fr", password="wrong"), request, Response(), db_session)

        with pytest.raises(HTTPException) as exc_info:
            login_local(LocalLoginPayload(identifier="a@example.fr", password="wrong"), request, Response(), db_session)
        assert exc_info.value.status_code == 429

        # Le BON mot de passe est refusé lui aussi tant que la fenêtre court : c'est le prix d'un
        # limiteur qui ne peut pas distinguer l'utilisateur légitime de l'attaquant depuis la même
        # adresse. La fenêtre est courte (rate_limit_window_minutes) et le quota confortable.
        with pytest.raises(HTTPException) as exc_info:
            login_local(LocalLoginPayload(identifier="a@example.fr", password="CorrectHorse8!"), request, Response(), db_session)
        assert exc_info.value.status_code == 429

    def test_a_successful_login_never_consumes_the_quota(self, db_session):
        """Seuls les ÉCHECS comptent : une application qui reconnecte souvent (plusieurs onglets,
        session expirée) ne doit pas s'auto-bloquer."""
        _make_local_account(db_session)
        request = _FakeRequest("198.51.100.9")

        for _ in range(settings.auth.rate_limit_attempts + 5):
            login_local(LocalLoginPayload(identifier="a@example.fr", password="CorrectHorse8!"), request, Response(), db_session)

    def test_successful_attempt_is_not_logged_as_warning(self, db_session, caplog):
        """Une connexion réussie est le flux normal et quotidien — la journaliser en WARNING
        noierait le signal utile (voir docstring de login_local)."""
        _make_local_account(db_session)
        request = _FakeRequest("198.51.100.9")

        with caplog.at_level(logging.WARNING, logger="backend.app.api.auth_endpoints"):
            login_local(LocalLoginPayload(identifier="a@example.fr", password="CorrectHorse8!"), request, Response(), db_session)

        assert len(caplog.records) == 0


class _FakeRequestForCurrentDbUser:
    """current_db_user lit request.url.path pour l'exemption PASSWORD_CHANGE_REQUIRED (voir
    database.py) — sans intérêt ici, juste de quoi satisfaire la signature."""
    class url:
        path = "/irrelevant"


def _cookie_value(response: Response) -> str:
    """Extrait la valeur du cookie de session d'une réponse (Set-Cookie brut)."""
    for key, value in response.raw_headers:
        if key.lower() == b"set-cookie" and value.startswith(COOKIE_NAME.encode()):
            return value.decode().split(";")[0].split("=", 1)[1]
    raise AssertionError(f"Aucun cookie {COOKIE_NAME} dans la réponse.")


def _request_carrying(token: str) -> StarletteRequest:
    return StarletteRequest({
        "type": "http", "method": "GET", "path": "/", "query_string": b"",
        "headers": [(b"cookie", f"{COOKIE_NAME}={token}".encode())],
    })


class TestLocalIdentityIsBoundToItsDatabase:
    """
    Voir instance_session.py::InstanceSession.db_slug et database.py::current_db_user. Le couple
    (provider_key="local", subject) est choisi librement par l'admin de n'importe quelle base : sans
    liaison à la base où le mot de passe a RÉELLEMENT été vérifié, il valait comme identité
    d'instance et permettait de devenir l'homonyme d'une autre base en changeant simplement
    l'en-tête X-Klepsydrix-Database.
    """

    def test_login_seals_the_database_in_the_session_cookie(self, db_session):
        _make_local_account(db_session)
        response = Response()

        login_local(LocalLoginPayload(identifier="a@example.fr", password="CorrectHorse8!"), _FakeRequest(), response, db_session)

        session = require_instance_session(_request_carrying(_cookie_value(response)), Response())
        assert session.provider_key == "local"
        # Moteur de test non enregistré dans db_registry : slug_for_session retombe sur
        # DEFAULT_DB_NAME, des deux côtés (login_local ET current_db_user) — voir db_registry.py.
        assert session.db_slug == "timetable"

    def test_identity_is_accepted_on_the_database_where_it_was_verified(self, db_session):
        _make_local_account(db_session)
        session = InstanceSession(provider_key="local", subject="a@example.fr", db_slug="timetable")

        user = current_db_user(request=_FakeRequestForCurrentDbUser(), session=session, db=db_session)

        assert user.email == "a@example.fr"

    def test_identity_verified_elsewhere_is_refused(self, db_session):
        """Le scénario d'usurpation : mot de passe vérifié dans la base d'un attaquant, en-tête
        pointant vers la base de la victime, où le même identifiant existe."""
        _make_local_account(db_session)
        session = InstanceSession(provider_key="local", subject="a@example.fr", db_slug="base-de-l-attaquant")

        with pytest.raises(HTTPException) as exc_info:
            current_db_user(request=_FakeRequestForCurrentDbUser(), session=session, db=db_session)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == {"code": "WRONG_DATABASE_FOR_LOCAL_IDENTITY"}

    def test_legacy_cookie_without_db_slug_forces_a_reconnection(self, db_session):
        """Cookie local émis avant l'introduction du champ : impossible de savoir où le mot de
        passe avait été vérifié, donc refus (une seule reconnexion, au déploiement) plutôt qu'un
        repli permissif qui rouvrirait la faille."""
        response = Response()
        set_session_cookie(response, provider_key="local", subject="a@example.fr")  # db_slug=None

        with pytest.raises(HTTPException) as exc_info:
            require_instance_session(_request_carrying(_cookie_value(response)), Response())

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == {"code": "NOT_AUTHENTICATED"}

    def test_federated_identity_is_not_bound_to_any_database(self, db_session):
        """Un `sub` OIDC est émis par un tiers, hors de portée d'un admin de base : aucune raison
        de le restreindre à une base, et la session s'établit avant tout choix de base (§17.F).
        La session n'a donc PAS de `db_slug`, et ça ne doit rien bloquer."""
        oidc_user = User.create(db_session, {"first_name": "O", "last_name": "Idc", "email": "o@example.fr"})
        UserIdentityProvider.create(db_session, {
            "user_id": oidc_user.id, "provider_key": "educonnect", "external_subject": "oidc-sub-1",
        })
        db_session.commit()
        session = InstanceSession(provider_key="educonnect", subject="oidc-sub-1", email="o@example.fr")

        user = current_db_user(request=_FakeRequestForCurrentDbUser(), session=session, db=db_session)

        assert user.id == oidc_user.id
