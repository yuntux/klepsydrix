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
from backend.app.core.instance_admin import (
    is_super_admin, is_db_admin, administrable_databases, require_admin_of, databases_for_identity,
)
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

    def test_repeated_failures_are_capped_by_the_application(self):
        """
        Changement de doctrine assumé (voir core/rate_limit.py, architecture.md §19.A) : il n'y
        avait AUCUN verrouillage applicatif, la protection reposant entièrement sur fail2ban. Là où
        fail2ban n'est pas déployé, ce point d'entrée — un secret PARTAGÉ qui ouvre la console
        d'administration de l'instance entière — était donc attaquable sans aucune limite.
        """
        password_hash = master_auth._password_hasher.hash("correct-horse-battery-staple")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(enabled=True, password_hash=password_hash)
        request = _FakeRequest("198.51.100.7")

        for _ in range(settings.auth.rate_limit_attempts):
            with pytest.raises(HTTPException) as exc_info:
                verify_master_password(request, "wrong-password")
            assert exc_info.value.status_code == 401  # évalué normalement tant que le quota tient

        with pytest.raises(HTTPException) as exc_info:
            verify_master_password(request, "wrong-password")
        assert exc_info.value.status_code == 429

    def test_a_different_address_keeps_its_own_quota(self):
        """Le quota est par adresse : un attaquant ne peut pas verrouiller l'accès d'un
        administrateur légitime en épuisant le compteur depuis chez lui."""
        password_hash = master_auth._password_hasher.hash("correct-horse-battery-staple")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(enabled=True, password_hash=password_hash)

        for _ in range(settings.auth.rate_limit_attempts + 1):
            with pytest.raises(HTTPException):
                verify_master_password(_FakeRequest("198.51.100.7"), "wrong-password")

        verify_master_password(_FakeRequest("10.1.2.3"), "correct-horse-battery-staple")  # ne lève rien

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

    def test_an_unknown_identity_is_refused_by_default(self, db_session):
        """
        `auth.auto_provision_users` est FAUX par défaut (voir config.py, database.py) : sur une
        instance qui héberge plusieurs établissements fédérés par le même OIDC académique,
        l'auto-création laissait n'importe quel enseignant de l'académie faire apparaître une ligne
        `users` dans CHAQUE base en changeant un simple en-tête HTTP.
        """
        session = InstanceSession(provider_key="educonnect", subject="brand-new-sub", first_name="Brand", last_name="New", email="brand.new@example.fr")

        with pytest.raises(HTTPException) as exc_info:
            current_db_user(request=_FakeRequestForCurrentDbUser(), session=session, db=db_session)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == {"code": "NOT_PROVISIONED"}
        assert db_session.query(User).count() == 0  # rien n'a été écrit

    def test_auto_provisioning_can_be_enabled_for_a_single_school_instance(self, db_session):
        """Instance mono-établissement fédérée : tout porteur d'une identité valide du fournisseur
        est effectivement légitime — le comportement historique reste disponible."""
        settings.auth.auto_provision_users = True
        try:
            session = InstanceSession(provider_key="educonnect", subject="brand-new-sub", first_name="Brand", last_name="New", email="brand.new@example.fr")
            resolved_user = current_db_user(request=_FakeRequestForCurrentDbUser(), session=session, db=db_session)
        finally:
            settings.auth.auto_provision_users = False

        assert resolved_user.email == "brand.new@example.fr"
        assert db_session.query(User).count() == 1
        assert resolved_user.groups == []  # créé SANS aucun droit, comme avant

    def test_local_identity_never_promotes_a_pending_row(self, db_session):
        """
        `session.email` vaut, pour le provider local, l'identifiant SAISI au formulaire (voir
        auth_endpoints.py::login_local) — une chaîne qu'un admin de n'importe quelle base peut se
        faire attribuer en créant chez lui un compte local du même nom. Sans cette restriction, il
        se faisait promouvoir à la place de l'admin désigné d'une base fraîchement créée, groupe
        "Admin" compris. Seul un provider FÉDÉRÉ, dont l'email est vérifié par un tiers, peut
        déclencher la promotion.
        """
        user = User.create(db_session, {"first_name": "En attente", "last_name": "de première connexion", "email": "future.admin@example.fr"})
        pending_idp = UserIdentityProvider.create(db_session, {
            "user_id": user.id, "provider_key": "pending", "external_subject": "future.admin@example.fr",
        })
        db_session.commit()

        session = InstanceSession(
            provider_key="local", subject="future.admin@example.fr",
            email="future.admin@example.fr", db_slug="timetable",
        )
        with pytest.raises(HTTPException) as exc_info:
            current_db_user(request=_FakeRequestForCurrentDbUser(), session=session, db=db_session)

        # Refusée à deux titres : l'email d'une identité locale ne promeut rien (ce test), et une
        # identité inconnue de la base n'est plus auto-créée (voir auth.auto_provision_users).
        assert exc_info.value.detail == {"code": "NOT_PROVISIONED"}
        db_session.refresh(pending_idp)
        assert pending_idp.provider_key == "pending"      # jamais promue

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

        assert result == {
            "id": user.id,
            "display_name": "A Dmin", "email": "a@example.fr", "is_admin": True,
            "must_change_password": False,
            # Plafond d'envoi servi à l'IHM par cette même route plutôt que recopié en dur
            # côté frontend (voir core/upload_limits.py, widgets/BinaryFileField.vue).
            "max_upload_mb": settings.server.max_upload_mb,
        }

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


class TestDatabasesForIdentity:
    """
    `GET /api/instance/my-databases` (voir instance_admin.py::databases_for_identity) — remplace
    l'ancienne route publique qui énumérait tous les établissements hébergés pour n'importe quel
    anonyme.
    """

    def test_a_local_identity_only_sees_the_database_it_was_verified_against(self, monkeypatch):
        """Corollaire direct de la liaison identité locale/base (voir InstanceSession.db_slug) :
        il ne peut y en avoir qu'une, et la connaître ne révèle rien de plus que ce que
        l'utilisateur vient lui-même de saisir au formulaire de connexion."""
        monkeypatch.setattr("backend.app.core.db_registry.is_known_slug", lambda slug: True)
        session = InstanceSession(provider_key="local", subject="a@example.fr", db_slug="college-a")

        assert databases_for_identity(session) == ["college-a"]

    def test_a_federated_identity_sees_only_the_databases_where_it_has_an_account(self, db_session, monkeypatch):
        user = User.create(db_session, {"first_name": "O", "last_name": "Idc", "email": "o@example.fr"})
        UserIdentityProvider.create(db_session, {
            "user_id": user.id, "provider_key": "educonnect", "external_subject": "sub-1",
        })
        db_session.commit()

        monkeypatch.setattr("backend.app.core.db_registry.known_slugs", lambda: {"college-a", "college-b"})
        # Seule "college-a" est branchée sur la base de test ; "college-b" reste vide.
        empty_engine = make_test_engine()
        EmptySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=empty_engine)
        Base.metadata.create_all(bind=empty_engine)
        monkeypatch.setattr(
            "backend.app.core.db_registry.sessionmaker_for",
            lambda slug: TestSessionLocal if slug == "college-a" else EmptySessionLocal,
        )
        session = InstanceSession(provider_key="educonnect", subject="sub-1")

        assert databases_for_identity(session) == ["college-a"]

    def test_the_master_password_identity_sees_nothing(self, monkeypatch):
        """Identité fantôme, refusée sur toute donnée applicative (voir current_db_user) : lui
        proposer une base serait une impasse."""
        monkeypatch.setattr("backend.app.core.db_registry.known_slugs", lambda: {"college-a"})
        session = InstanceSession(provider_key=MASTER_PROVIDER_KEY, subject=MASTER_SUBJECT)

        assert databases_for_identity(session) == []
