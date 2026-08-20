"""
Tests pour la console d'administration d'instance (voir architecture.md §19, plan "Multi-SGBD,
Multi-Base, Utilisateurs/IDP, Droits, Console Admin") : authentification par mot de passe maître
(core/master_auth.py), autorisation super-admin/admin de base (core/instance_admin.py), et le
mécanisme de pré-appariement par email (database.py::current_db_user).

Les opérations physiques sur une base (créer/dupliquer/sauvegarder/restaurer/supprimer, voir
core/db_admin_ops.py) et les routes HTTP (api/instance_endpoints.py) sont couvertes manuellement
via curl (voir architecture.md §19) plutôt qu'ici : elles touchent le système de fichiers/lancent
des sous-processus, hors du périmètre habituel (SQLite RAM / Postgres jetable) de cette suite.
"""
import time
import pytest
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models import User, UserIdentityProvider, ResGroup
from backend.tests.db_test_utils import make_test_engine
from backend.app.core.config import settings, SuperAdminPair
from backend.app.core import master_auth
from backend.app.core.master_auth import verify_master_password, MASTER_PROVIDER_KEY, MASTER_SUBJECT
from backend.app.core.instance_admin import is_super_admin, is_db_admin, administrable_databases, require_admin_of
from backend.app.core.instance_session import InstanceSession
from backend.app.core.database import current_db_user
from backend.app.api.ui_endpoints import whoami
from fastapi import HTTPException

test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


class _FakeRequestForCurrentDbUser:
    """current_db_user lit request.url.path pour l'exemption PASSWORD_CHANGE_REQUIRED (voir
    database.py) — sans intérêt pour ces tests (aucun n'active must_change_password), juste de quoi
    satisfaire la signature sans monter un vrai objet Request ASGI. Nommée différemment du
    _FakeRequest plus bas (TestMasterAuth/TestClientIpTrustedProxy, forme .client/.headers) — les
    deux servent un objet Request minimal, mais pour des attributs disjoints."""
    class url:
        path = "/irrelevant"


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


@pytest.fixture(autouse=True)
def _reset_master_auth_state():
    """Config maître/super-admins/proxies de confiance — isolée par test, jamais laissée en fuite
    d'un test à l'autre (settings est un singleton process-wide, voir conftest.py::
    override_settings pour le même principe déjà appliqué à SOLVER_TIME_LIMIT_SECONDS)."""
    original_master_cfg = settings.master_db_local_auth
    original_super_admins = settings.super_admins
    original_trusted_proxies = settings.server.trusted_proxies
    yield
    settings.master_db_local_auth = original_master_cfg
    settings.super_admins = original_super_admins
    settings.server.trusted_proxies = original_trusted_proxies


class TestMasterAuth:
    def test_disabled_by_default_returns_404(self):
        settings.master_db_local_auth = type(settings.master_db_local_auth)(enabled=False)
        with pytest.raises(HTTPException) as exc_info:
            verify_master_password(_FakeRequest(), "whatever")
        assert exc_info.value.status_code == 404

    def test_correct_password_succeeds(self):
        password_hash = master_auth._password_hasher.hash("correct-horse-battery-staple")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(enabled=True, password_hash=password_hash)
        verify_master_password(_FakeRequest(), "correct-horse-battery-staple")  # ne lève rien

    def test_incorrect_password_returns_401(self):
        password_hash = master_auth._password_hasher.hash("correct-horse-battery-staple")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(enabled=True, password_hash=password_hash)
        with pytest.raises(HTTPException) as exc_info:
            verify_master_password(_FakeRequest(), "wrong-password")
        assert exc_info.value.status_code == 401

    def test_no_lockout_after_many_failed_attempts(self):
        """AUCUN verrouillage applicatif (décision explicite, voir architecture.md §19.A) : même
        après de nombreux échecs, chaque tentative reste évaluée normalement (401 sur mot de passe
        incorrect, jamais un 403 de verrouillage) — la protection anti-brute-force est entièrement
        déléguée à fail2ban, qui lit le journal de ces échecs."""
        password_hash = master_auth._password_hasher.hash("correct-horse-battery-staple")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(enabled=True, password_hash=password_hash)
        request = _FakeRequest("198.51.100.7")
        for _ in range(20):
            with pytest.raises(HTTPException) as exc_info:
                verify_master_password(request, "wrong-password")
            assert exc_info.value.status_code == 401
        # Le bon mot de passe fonctionne toujours, même après 20 échecs consécutifs.
        verify_master_password(request, "correct-horse-battery-staple")  # ne lève rien

    def test_ip_allowlist_rejects_unlisted_address(self):
        password_hash = master_auth._password_hasher.hash("correct-horse-battery-staple")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(
            enabled=True, password_hash=password_hash, ip_allowlist=["10.0.0.0/8"],
        )
        with pytest.raises(HTTPException) as exc_info:
            verify_master_password(_FakeRequest("203.0.113.1"), "correct-horse-battery-staple")
        assert exc_info.value.status_code == 403

    def test_ip_allowlist_accepts_listed_address(self):
        password_hash = master_auth._password_hasher.hash("correct-horse-battery-staple")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(
            enabled=True, password_hash=password_hash, ip_allowlist=["10.0.0.0/8"],
        )
        verify_master_password(_FakeRequest("10.1.2.3"), "correct-horse-battery-staple")  # ne lève rien

    def test_enabled_without_password_hash_returns_403(self):
        settings.master_db_local_auth = type(settings.master_db_local_auth)(enabled=True, password_hash=None)
        with pytest.raises(HTTPException) as exc_info:
            verify_master_password(_FakeRequest(), "anything")
        assert exc_info.value.status_code == 403


class TestClientIpTrustedProxy:
    """
    `_client_ip` (voir architecture.md §19.A) : X-Forwarded-For n'est lu que si la connexion TCP
    directe vient d'un reverse proxy explicitement listé dans server.trusted_proxies — sinon
    n'importe quel client pourrait fixer cet en-tête lui-même pour usurper une IP autorisée par
    ip_allowlist.
    """
    def test_untrusted_direct_connection_ignores_forwarded_header(self):
        settings.server.trusted_proxies = []
        request = _FakeRequest(host="198.51.100.9", headers={"x-forwarded-for": "10.0.0.5"})
        assert master_auth._client_ip(request) == "198.51.100.9"

    def test_trusted_proxy_forwarded_header_is_used(self):
        settings.server.trusted_proxies = ["127.0.0.1", "::1"]
        request = _FakeRequest(host="127.0.0.1", headers={"x-forwarded-for": "203.0.113.42"})
        assert master_auth._client_ip(request) == "203.0.113.42"

    def test_trusted_proxy_takes_leftmost_entry_of_a_chain(self):
        settings.server.trusted_proxies = ["127.0.0.1"]
        request = _FakeRequest(host="127.0.0.1", headers={"x-forwarded-for": "203.0.113.42, 10.0.0.1"})
        assert master_auth._client_ip(request) == "203.0.113.42"

    def test_trusted_proxy_without_forwarded_header_falls_back_to_direct_ip(self):
        settings.server.trusted_proxies = ["127.0.0.1"]
        request = _FakeRequest(host="127.0.0.1", headers={})
        assert master_auth._client_ip(request) == "127.0.0.1"

    def test_untrusted_proxy_ip_is_not_matched_by_cidr_meant_for_another_range(self):
        settings.server.trusted_proxies = ["10.0.0.0/8"]
        request = _FakeRequest(host="198.51.100.9", headers={"x-forwarded-for": "attacker-controlled"})
        assert master_auth._client_ip(request) == "198.51.100.9"

    def test_ip_allowlist_end_to_end_behind_trusted_proxy(self):
        """Le scénario réel qui a motivé ce mécanisme : ip_allowlist doit filtrer sur l'IP du
        CLIENT, pas sur celle du reverse proxy — voir architecture.md §19.A."""
        settings.server.trusted_proxies = ["127.0.0.1"]
        password_hash = master_auth._password_hasher.hash("correct-horse-battery-staple")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(
            enabled=True, password_hash=password_hash, ip_allowlist=["10.0.0.0/8"],
        )
        # Client réel hors liste, même en passant par le proxy de confiance : refusé.
        request = _FakeRequest(host="127.0.0.1", headers={"x-forwarded-for": "203.0.113.42"})
        with pytest.raises(HTTPException) as exc_info:
            verify_master_password(request, "correct-horse-battery-staple")
        assert exc_info.value.status_code == 403
        # Client réel dans la liste, passant par le même proxy : autorisé.
        request = _FakeRequest(host="127.0.0.1", headers={"x-forwarded-for": "10.1.2.3"})
        verify_master_password(request, "correct-horse-battery-staple")  # ne lève rien


class TestSuperAdminResolution:
    def test_named_pair_is_super_admin(self):
        settings.super_admins = [SuperAdminPair(provider_key="educonnect", subject="abc123")]
        session = InstanceSession(provider_key="educonnect", subject="abc123")
        assert is_super_admin(session) is True

    def test_unrelated_identity_is_not_super_admin(self):
        settings.super_admins = [SuperAdminPair(provider_key="educonnect", subject="abc123")]
        session = InstanceSession(provider_key="educonnect", subject="someone-else")
        assert is_super_admin(session) is False

    def test_master_identity_is_always_super_admin(self):
        settings.super_admins = []
        session = InstanceSession(provider_key=MASTER_PROVIDER_KEY, subject=MASTER_SUBJECT)
        assert is_super_admin(session) is True

    def test_local_provider_is_refused_as_super_admin_pair(self):
        """
        Un admin de base quelconque a le droit create/write sur user_identity_providers (comme tout
        modèle, pour le groupe "Admin") — il pourrait donc se créer LUI-MÊME un compte local avec le
        même external_subject qu'une paire super_admins configurée, et usurper le statut super-admin
        sur toute l'instance (login_local ne retient jamais dans quelle base l'identifiant a été
        vérifié). provider_key="local" est donc refusé à la configuration, pas seulement déconseillé.
        """
        with pytest.raises(ValueError, match="local"):
            SuperAdminPair(provider_key="local", subject="quelqu.un@example.fr")


class TestDbAdmin:
    def test_admin_group_member_is_db_admin(self, db_session, monkeypatch):
        user = User.create(db_session, {"first_name": "A", "last_name": "Dmin", "email": "a@example.fr"})
        UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "local", "external_subject": "a@example.fr"})
        admin_group = ResGroup.create(db_session, {"name": "Admin", "user_ids": [user.id]})
        db_session.commit()

        monkeypatch.setattr("backend.app.core.db_registry.sessionmaker_for", lambda slug: TestSessionLocal)
        session = InstanceSession(provider_key="local", subject="a@example.fr")
        assert is_db_admin(session, "whatever-slug") is True

    def test_non_admin_user_is_not_db_admin(self, db_session, monkeypatch):
        user = User.create(db_session, {"first_name": "B", "last_name": "Asic", "email": "b@example.fr"})
        UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "local", "external_subject": "b@example.fr"})
        db_session.commit()

        monkeypatch.setattr("backend.app.core.db_registry.sessionmaker_for", lambda slug: TestSessionLocal)
        session = InstanceSession(provider_key="local", subject="b@example.fr")
        assert is_db_admin(session, "whatever-slug") is False

    def test_unknown_identity_is_not_db_admin(self, db_session, monkeypatch):
        monkeypatch.setattr("backend.app.core.db_registry.sessionmaker_for", lambda slug: TestSessionLocal)
        session = InstanceSession(provider_key="local", subject="nobody@example.fr")
        assert is_db_admin(session, "whatever-slug") is False

    def test_master_identity_is_never_db_admin(self):
        session = InstanceSession(provider_key=MASTER_PROVIDER_KEY, subject=MASTER_SUBJECT)
        assert is_db_admin(session, "whatever-slug") is False

    def test_require_admin_of_rejects_non_admin(self, db_session, monkeypatch):
        monkeypatch.setattr("backend.app.core.db_registry.sessionmaker_for", lambda slug: TestSessionLocal)
        settings.super_admins = []
        session = InstanceSession(provider_key="local", subject="nobody@example.fr")
        with pytest.raises(HTTPException) as exc_info:
            require_admin_of("whatever-slug", session=session)
        assert exc_info.value.status_code == 403


class TestPendingPairingPromotion:
    """
    Voir database.py::current_db_user — mécanisme de pré-appariement par email : à la création
    d'une base via la console d'administration, l'admin désigné n'a pas encore de `sub` réel ; une
    ligne UserIdentityProvider(provider_key="pending", external_subject=<email>) est créée à la
    place, et promue ici à la première VRAIE connexion dont l'email correspond.
    """
    def test_first_real_login_promotes_pending_row_instead_of_duplicating_user(self, db_session):
        user = User.create(db_session, {"first_name": "En attente", "last_name": "de première connexion", "email": "future.admin@example.fr"})
        pending_idp = UserIdentityProvider.create(db_session, {
            "user_id": user.id, "provider_key": "pending", "external_subject": "future.admin@example.fr",
        })
        db_session.commit()

        session = InstanceSession(provider_key="educonnect", subject="real-oidc-sub-42", first_name="Future", last_name="Admin", email="future.admin@example.fr")
        resolved_user = current_db_user(request=_FakeRequestForCurrentDbUser(), session=session, db=db_session)

        assert resolved_user.id == user.id  # même User, pas un doublon
        # current_db_user pose db.klepsydrix_user_id (drapeau ambiant, voir base.py) : ce User
        # n'a aucun ResGroup, donc User.count() (filtré par droits) verrait 0 — requête brute pour
        # vérifier l'absence de doublon, indépendamment du moteur de droits (hors périmètre ici).
        assert db_session.query(User).count() == 1
        db_session.refresh(pending_idp)
        assert pending_idp.provider_key == "educonnect"
        assert pending_idp.external_subject == "real-oidc-sub-42"

    def test_login_with_no_matching_pending_row_creates_new_user(self, db_session):
        session = InstanceSession(provider_key="educonnect", subject="brand-new-sub", first_name="Brand", last_name="New", email="brand.new@example.fr")
        resolved_user = current_db_user(request=_FakeRequestForCurrentDbUser(), session=session, db=db_session)
        assert resolved_user.email == "brand.new@example.fr"
        assert db_session.query(User).count() == 1

    def test_master_identity_is_rejected_for_application_data(self, db_session):
        """Code structuré (pas un texte libre) : reconnu par apiFetch() côté frontend pour renvoyer
        l'utilisateur vers /login plutôt que de le laisser dans une impasse silencieuse."""
        session = InstanceSession(provider_key=MASTER_PROVIDER_KEY, subject=MASTER_SUBJECT)
        with pytest.raises(HTTPException) as exc_info:
            current_db_user(request=_FakeRequestForCurrentDbUser(), session=session, db=db_session)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == {"code": "MASTER_IDENTITY_FORBIDDEN"}


class TestWhoAmI:
    """`GET /api/ui/whoami` (ui_endpoints.py) — sert l'IHM (NotebooksTree.vue) pour afficher
    l'identité connectée et proposer un lien vers la console d'administration."""

    def test_admin_group_member_is_flagged_admin(self, db_session):
        user = User.create(db_session, {"first_name": "A", "last_name": "Dmin", "email": "a@example.fr"})
        ResGroup.create(db_session, {"name": "Admin", "user_ids": [user.id]})
        db_session.commit()
        session = InstanceSession(provider_key="local", subject="a@example.fr")

        result = whoami(session=session, db=db_session, user=user)

        assert result == {"display_name": "A Dmin", "email": "a@example.fr", "is_admin": True, "must_change_password": False}

    def test_non_admin_user_is_not_flagged_admin(self, db_session):
        user = User.create(db_session, {"first_name": "B", "last_name": "Asic", "email": "b@example.fr"})
        db_session.commit()
        session = InstanceSession(provider_key="local", subject="b@example.fr")

        result = whoami(session=session, db=db_session, user=user)

        assert result["is_admin"] is False

    def test_instance_super_admin_is_flagged_admin_even_without_local_group(self, db_session):
        """Un super-admin d'instance (voir instance_admin.py::is_super_admin) n'a pas forcément le
        groupe "Admin" DANS cette base précise — les deux voies doivent quand même donner is_admin."""
        user = User.create(db_session, {"first_name": "C", "last_name": "Super", "email": "c@example.fr"})
        db_session.commit()
        settings.super_admins = [SuperAdminPair(provider_key="educonnect", subject="c-sub")]
        session = InstanceSession(provider_key="educonnect", subject="c-sub")

        result = whoami(session=session, db=db_session, user=user)

        assert result["is_admin"] is True
