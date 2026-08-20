"""
Tests HTTP de bout en bout pour les routes d'authentification (auth_endpoints.py) — compte
désactivé, changement de mot de passe forcé (must_change_password), nouvel endpoint
POST /api/auth/password/change. Contrairement à test_api.py (qui surcharge AUSSI current_db_user
pour court-circuiter le moteur de droits), ces tests laissent current_db_user INTACT : c'est
justement le comportement qu'on veut exercer ici (voir database.py::current_db_user,
USER_INACTIVE/PASSWORD_CHANGE_REQUIRED). Seul get_db est surchargé, sur le modèle de test_api.py.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from backend.app.main import app
from backend.app.core.database import get_db
from backend.app.models.base import Base
from backend.app.models.user import User, UserIdentityProvider
from backend.tests.db_test_utils import make_test_engine

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@pytest.fixture(scope="function", autouse=True)
def setup_dependency_overrides():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client():
    # Une instance PAR TEST (pas de singleton module-level) : évite qu'un cookie de session posé
    # par un test contamine le suivant — chaque test démarre avec un jar de cookies vide.
    return TestClient(app)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _make_local_user(db, *, identifier, password="Correct8!", active=True, must_change_password=False):
    user = User.create(db, {"first_name": "Jean", "last_name": "Petit", "email": identifier, "active": active})
    idp = UserIdentityProvider.register_local_password(db, user.id, identifier, password)
    if must_change_password:
        idp.update(db, {"must_change_password": True})
    db.commit()
    return user, idp


class TestInactiveUserLogin:
    def test_active_user_can_log_in(self, db_session, client):
        _make_local_user(db_session, identifier="active@example.com")
        response = client.post("/api/auth/login/local", json={"identifier": "active@example.com", "password": "Correct8!"})
        assert response.status_code == 200
        assert "klepsydrix_session" in response.cookies

    def test_inactive_user_is_rejected_at_login(self, db_session, client):
        _make_local_user(db_session, identifier="inactive@example.com", active=False)
        response = client.post("/api/auth/login/local", json={"identifier": "inactive@example.com", "password": "Correct8!"})
        assert response.status_code == 403
        assert "désactivé" in response.json()["detail"]
        assert "klepsydrix_session" not in response.cookies

    def test_wrong_password_still_reported_generically_even_for_an_inactive_account(self, db_session, client):
        """L'inactivité ne doit jamais se révéler avant que le mot de passe soit vérifié (voir
        auth_endpoints.py::login_local) — sinon un identifiant désactivé se distinguerait d'un
        identifiant inconnu par un message différent, une fuite d'énumération."""
        _make_local_user(db_session, identifier="inactive2@example.com", active=False)
        response = client.post("/api/auth/login/local", json={"identifier": "inactive2@example.com", "password": "wrong"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Identifiant ou mot de passe incorrect."


class TestMustChangePasswordGating:
    def test_generic_endpoint_is_blocked_until_password_is_changed(self, db_session, client):
        _make_local_user(db_session, identifier="forced@example.com", must_change_password=True)
        login = client.post("/api/auth/login/local", json={"identifier": "forced@example.com", "password": "Correct8!"})
        assert login.status_code == 200

        blocked = client.get("/api/generic/users")
        assert blocked.status_code == 403
        assert blocked.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    def test_whoami_remains_reachable_while_password_change_is_required(self, db_session, client):
        _make_local_user(db_session, identifier="forced2@example.com", must_change_password=True)
        client.post("/api/auth/login/local", json={"identifier": "forced2@example.com", "password": "Correct8!"})

        who = client.get("/api/ui/whoami")
        assert who.status_code == 200
        assert who.json()["must_change_password"] is True

    def test_changing_password_lifts_the_gate(self, db_session, client):
        _make_local_user(db_session, identifier="forced3@example.com", must_change_password=True)
        client.post("/api/auth/login/local", json={"identifier": "forced3@example.com", "password": "Correct8!"})

        change = client.post("/api/auth/password/change", json={"current_password": "Correct8!", "new_password": "NewGood9!"})
        assert change.status_code == 200

        unblocked = client.get("/api/generic/users")
        assert unblocked.status_code == 200

        who = client.get("/api/ui/whoami")
        assert who.json()["must_change_password"] is False

    def test_active_flag_still_takes_priority_over_password_change_gate(self, db_session, client):
        """USER_INACTIVE doit rester le rejet observé, même quand must_change_password est AUSSI
        posé — un compte désactivé ne doit jamais rester joignable via l'exemption de la route de
        changement de mot de passe."""
        user, idp = _make_local_user(db_session, identifier="forced4@example.com", must_change_password=True)
        client.post("/api/auth/login/local", json={"identifier": "forced4@example.com", "password": "Correct8!"})
        user.update(db_session, {"active": False})
        db_session.commit()

        # PASSWORD_CHANGE_REQUIRED est exempté sur whoami, mais USER_INACTIVE ne l'est jamais.
        response = client.get("/api/ui/whoami")
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "USER_INACTIVE"


class TestPasswordChangeEndpoint:
    def test_successful_change_invalidates_the_old_password(self, db_session, client):
        _make_local_user(db_session, identifier="change@example.com")
        client.post("/api/auth/login/local", json={"identifier": "change@example.com", "password": "Correct8!"})

        response = client.post("/api/auth/password/change", json={"current_password": "Correct8!", "new_password": "NewGood9!"})
        assert response.status_code == 200

        old_login = client.post("/api/auth/login/local", json={"identifier": "change@example.com", "password": "Correct8!"})
        assert old_login.status_code == 401
        new_login = client.post("/api/auth/login/local", json={"identifier": "change@example.com", "password": "NewGood9!"})
        assert new_login.status_code == 200

    def test_wrong_current_password_is_rejected(self, db_session, client):
        _make_local_user(db_session, identifier="wrongcur@example.com")
        client.post("/api/auth/login/local", json={"identifier": "wrongcur@example.com", "password": "Correct8!"})

        response = client.post("/api/auth/password/change", json={"current_password": "NotIt1!", "new_password": "NewGood9!"})
        assert response.status_code == 401

    def test_weak_new_password_is_rejected(self, db_session, client):
        _make_local_user(db_session, identifier="weaknew@example.com")
        client.post("/api/auth/login/local", json={"identifier": "weaknew@example.com", "password": "Correct8!"})

        response = client.post("/api/auth/password/change", json={"current_password": "Correct8!", "new_password": "weak"})
        assert response.status_code == 400

    def test_requires_an_authenticated_session(self, db_session, client):
        response = client.post("/api/auth/password/change", json={"current_password": "x", "new_password": "NewGood9!"})
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "NOT_AUTHENTICATED"
