"""
Tests pour la réinitialisation de mot de passe du provider "local" (voir architecture.md §17.G) :
jeton (PasswordResetToken), et les deux routes publiques (auth_endpoints.py). L'envoi d'email
lui-même (core/mailer.py, fastapi-mail) est toujours simulé (monkeypatch) — la config `smtp:` de
dev est volontairement fictive (voir instance.yaml), un test qui l'invoquerait réellement tenterait
une vraie connexion réseau et échouerait/traînerait en longueur pour rien.

`instance_endpoints.py::create_database` (case "envoyer un lien de réinitialisation" de la console
admin) n'est PAS testé ici : il crée un vrai fichier SQLite/une vraie base PostgreSQL, hors du
périmètre habituel de cette suite (voir test_instance_admin.py, même principe) — couvert
manuellement via curl/navigateur.
"""
import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from backend.app.models.base import Base
from backend.app.models import User, UserIdentityProvider, PasswordResetToken
from backend.tests.db_test_utils import make_test_engine
from backend.app.core.config import settings

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


def _run(coro):
    return asyncio.run(coro)


class TestPasswordResetToken:
    def test_issue_then_consume_returns_the_identity_provider(self, db_session):
        user = User.create(db_session, {"first_name": "A", "last_name": "Local", "email": "a@example.fr"})
        idp = UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "local", "external_subject": "a@example.fr"})
        db_session.commit()

        record, raw_token = PasswordResetToken.issue(db_session, idp.id, ttl_minutes=60)
        db_session.commit()

        assert record.used_at is None
        resolved = PasswordResetToken.consume(db_session, raw_token)
        assert resolved is not None
        assert resolved.id == idp.id

    def test_token_is_single_use(self, db_session):
        user = User.create(db_session, {"first_name": "A", "last_name": "Local", "email": "a@example.fr"})
        idp = UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "local", "external_subject": "a@example.fr"})
        db_session.commit()
        _, raw_token = PasswordResetToken.issue(db_session, idp.id, ttl_minutes=60)
        db_session.commit()

        assert PasswordResetToken.consume(db_session, raw_token) is not None
        # Deuxième tentative avec le MÊME jeton : déjà marqué utilisé, refusé.
        assert PasswordResetToken.consume(db_session, raw_token) is None

    def test_wrong_token_is_rejected(self, db_session):
        user = User.create(db_session, {"first_name": "A", "last_name": "Local", "email": "a@example.fr"})
        idp = UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "local", "external_subject": "a@example.fr"})
        db_session.commit()
        PasswordResetToken.issue(db_session, idp.id, ttl_minutes=60)
        db_session.commit()

        assert PasswordResetToken.consume(db_session, "un-jeton-invente-de-toutes-pieces") is None

    def test_expired_token_is_rejected(self, db_session):
        user = User.create(db_session, {"first_name": "A", "last_name": "Local", "email": "a@example.fr"})
        idp = UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "local", "external_subject": "a@example.fr"})
        db_session.commit()
        record, raw_token = PasswordResetToken.issue(db_session, idp.id, ttl_minutes=60)
        # Recule artificiellement l'expiration pour simuler un jeton périmé, sans attendre 60min.
        record.update(db_session, {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)})
        db_session.commit()

        assert PasswordResetToken.consume(db_session, raw_token) is None

    def test_expires_at_survives_a_round_trip_through_sqlite_naive_storage(self, db_session):
        """SQLite (et une colonne DateTime "naïve") perdent l'info de fuseau horaire au retour de
        lecture — voir _as_utc dans le modèle. Vérifie que la comparaison ne lève PAS TypeError."""
        user = User.create(db_session, {"first_name": "A", "last_name": "Local", "email": "a@example.fr"})
        idp = UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "local", "external_subject": "a@example.fr"})
        db_session.commit()
        _, raw_token = PasswordResetToken.issue(db_session, idp.id, ttl_minutes=60)
        db_session.commit()
        db_session.expire_all()  # force une relecture depuis la base, pas depuis l'identity map

        assert PasswordResetToken.consume(db_session, raw_token) is not None


class _FakeClient:
    def __init__(self, host="203.0.113.1"):
        self.host = host


class _FakeRequest:
    """`password_reset_request` lit l'IP de l'appelant (limitation de débit + journal pour
    fail2ban, voir core/rate_limit.py) — juste de quoi satisfaire client_ip()."""
    def __init__(self, host="203.0.113.1"):
        self.client = _FakeClient(host)
        self.headers = {}


class TestPasswordResetRequestEndpoint:
    def test_existing_local_account_gets_a_token_and_an_email(self, db_session, monkeypatch):
        from backend.app.api import auth_endpoints

        user = User.create(db_session, {"first_name": "A", "last_name": "Local", "email": "a@example.fr"})
        UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "local", "external_subject": "a@example.fr"})
        db_session.commit()

        sent = []
        async def fake_send(to_email, reset_url):
            sent.append((to_email, reset_url))
        monkeypatch.setattr(auth_endpoints, "send_password_reset_email", fake_send)

        payload = auth_endpoints.PasswordResetRequestPayload(identifier="a@example.fr")
        result = _run(auth_endpoints.password_reset_request(payload, _FakeRequest(), db=db_session))

        assert result == {"status": "success"}
        assert len(sent) == 1
        assert sent[0][0] == "a@example.fr"
        assert db_session.query(PasswordResetToken).count() == 1

    def test_unknown_identifier_gets_the_same_generic_response_but_no_email(self, db_session, monkeypatch):
        """Pas d'énumération : la réponse HTTP est identique, que le compte existe ou non."""
        from backend.app.api import auth_endpoints

        sent = []
        async def fake_send(to_email, reset_url):
            sent.append((to_email, reset_url))
        monkeypatch.setattr(auth_endpoints, "send_password_reset_email", fake_send)

        payload = auth_endpoints.PasswordResetRequestPayload(identifier="personne@example.fr")
        result = _run(auth_endpoints.password_reset_request(payload, _FakeRequest(), db=db_session))

        assert result == {"status": "success"}
        assert len(sent) == 0
        assert db_session.query(PasswordResetToken).count() == 0

    def test_email_send_failure_does_not_break_the_request(self, db_session, monkeypatch):
        """Un SMTP mal configuré (comme instance.yaml en dev, valeurs fictives) ne doit jamais faire
        échouer /password-reset/request avec une 500 — le jeton reste utilisable même si le mail
        n'est jamais arrivé (l'admin peut communiquer le lien autrement)."""
        from backend.app.api import auth_endpoints

        user = User.create(db_session, {"first_name": "A", "last_name": "Local", "email": "a@example.fr"})
        UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "local", "external_subject": "a@example.fr"})
        db_session.commit()

        async def failing_send(to_email, reset_url):
            raise RuntimeError("Connexion SMTP refusée (config fictive de dev)")
        monkeypatch.setattr(auth_endpoints, "send_password_reset_email", failing_send)

        payload = auth_endpoints.PasswordResetRequestPayload(identifier="a@example.fr")
        result = _run(auth_endpoints.password_reset_request(payload, _FakeRequest(), db=db_session))

        assert result == {"status": "success"}
        assert db_session.query(PasswordResetToken).count() == 1


class TestPasswordResetConfirmEndpoint:
    def test_valid_token_sets_the_new_password(self, db_session):
        from backend.app.api.auth_endpoints import PasswordResetConfirmPayload, password_reset_confirm

        user = User.create(db_session, {"first_name": "A", "last_name": "Local", "email": "a@example.fr"})
        idp = UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "local", "external_subject": "a@example.fr"})
        db_session.commit()
        _, raw_token = PasswordResetToken.issue(db_session, idp.id, ttl_minutes=60)
        db_session.commit()

        result = password_reset_confirm(PasswordResetConfirmPayload(token=raw_token, new_password="nouveau-mdp-1234"), db=db_session)

        assert result == {"status": "success"}
        assert UserIdentityProvider.verify_local_password(db_session, "a@example.fr", "nouveau-mdp-1234") is not None

    def test_invalid_token_returns_400(self, db_session):
        from backend.app.api.auth_endpoints import PasswordResetConfirmPayload, password_reset_confirm

        with pytest.raises(HTTPException) as exc_info:
            password_reset_confirm(PasswordResetConfirmPayload(token="jeton-invente", new_password="nouveau-mdp-1234"), db=db_session)
        assert exc_info.value.status_code == 400

    def test_token_cannot_be_reused(self, db_session):
        from backend.app.api.auth_endpoints import PasswordResetConfirmPayload, password_reset_confirm

        user = User.create(db_session, {"first_name": "A", "last_name": "Local", "email": "a@example.fr"})
        idp = UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "local", "external_subject": "a@example.fr"})
        db_session.commit()
        _, raw_token = PasswordResetToken.issue(db_session, idp.id, ttl_minutes=60)
        db_session.commit()

        password_reset_confirm(PasswordResetConfirmPayload(token=raw_token, new_password="premier-mdp-1234"), db=db_session)
        with pytest.raises(HTTPException) as exc_info:
            password_reset_confirm(PasswordResetConfirmPayload(token=raw_token, new_password="second-mdp-1234"), db=db_session)
        assert exc_info.value.status_code == 400
        # Le premier mot de passe défini reste actif — la seconde tentative n'a rien changé.
        assert UserIdentityProvider.verify_local_password(db_session, "a@example.fr", "premier-mdp-1234") is not None


class TestPasswordResetTokenPrivateField:
    def test_token_hash_never_serialized(self, db_session):
        from backend.app.api.generic import sqla_to_dict

        user = User.create(db_session, {"first_name": "A", "last_name": "Local", "email": "a@example.fr"})
        idp = UserIdentityProvider.create(db_session, {"user_id": user.id, "provider_key": "local", "external_subject": "a@example.fr"})
        db_session.commit()
        record, _ = PasswordResetToken.issue(db_session, idp.id, ttl_minutes=60)
        db_session.commit()

        assert "token_hash" not in sqla_to_dict(record)
