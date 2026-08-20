"""
Vérifie que les lignes de log RÉELLEMENT générées par l'application correspondent aux filtres
fail2ban DÉPLOYÉS (`deploy/fail2ban/*.conf`) — voir architecture.md §16.F/§17.H/§19.A : la
protection anti-brute-force de Klepsydrix repose ENTIÈREMENT sur fail2ban (aucun verrouillage
applicatif, décision assumée et documentée). Un filtre qui cesse de matcher — parce que le message
de log a changé sans que quelqu'un pense à mettre à jour le fichier `.conf` correspondant — ne
produit AUCUNE erreur visible : fail2ban continue de tourner, ignore juste silencieusement les
tentatives. La dérive est totalement muette, c'est exactement ce que cette suite doit attraper.

Ce test lit les VRAIS fichiers `.conf` déployés (jamais une copie du regex dupliquée ici, qui
pourrait dériver indépendamment du filtre réel) et les confronte à de vraies lignes de log produites
en appelant le code applicatif (`verify_master_password`, `login_local`) tel quel — pas une
approximation du format, exactement le même `Formatter`/`Filter` que `main.py`.
"""
import configparser
import io
import logging
import re
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import settings
from backend.app.core.log_context import DbContextFilter
from backend.app.core import master_auth
from backend.app.api.auth_endpoints import LocalLoginPayload, login_local
from backend.app.models.base import Base
from backend.app.models import User, UserIdentityProvider
from backend.tests.db_test_utils import make_test_engine

FAIL2BAN_DIR = Path(__file__).resolve().parents[2] / "deploy" / "fail2ban"
# Même format que main.py::logging.basicConfig — un test qui utiliserait un format différent ne
# vérifierait rien de réel.
LOG_FORMAT = "%(asctime)s %(levelname)s [db=%(db_slug)s] %(name)s: %(message)s"
# <HOST> : substitution volontairement simplifiée (IPv4/IPv6 en chiffres/deux-points) — cette suite
# ne teste PAS la vraie substitution fail2ban elle-même (fail2ban n'est pas installé sur cette
# machine, voir architecture.md §19.A), seulement que le RESTE du motif matche du texte réel produit
# par l'application.
_HOST_PLACEHOLDER = r"(?P<host>[0-9a-fA-F:.]+)"


def _parse_filter(filename: str):
    path = FAIL2BAN_DIR / filename
    cp = configparser.ConfigParser()
    read = cp.read(path)
    assert read, f"filtre fail2ban introuvable : {path}"
    failregex = [
        line.replace("<HOST>", _HOST_PLACEHOLDER)
        for line in cp.get("Definition", "failregex").split("\n") if line.strip()
    ]
    ignore_raw = cp.get("Definition", "ignoreregex", fallback="")
    ignoreregex = [
        line.replace("<HOST>", _HOST_PLACEHOLDER)
        for line in ignore_raw.split("\n") if line.strip()
    ]
    return failregex, ignoreregex


@contextmanager
def _capture(logger_name: str):
    """Capture ce qu'un logger applicatif écrirait RÉELLEMENT en production — même `Formatter`,
    même `DbContextFilter` (voir main.py) — sans dépendre de l'état du logger RACINE (que d'autres
    fichiers de test peuvent muter, voir test_logging.py) ni du niveau effectif hérité (pytest peut
    l'avoir relevé, voir test_logging.py::test_a_log_call_formats_without_error_once_attached pour
    le même piège déjà rencontré)."""
    logger = logging.getLogger(logger_name)
    capture = io.StringIO()
    handler = logging.StreamHandler(capture)
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(DbContextFilter())
    original_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        yield capture
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)


def _lines(capture: io.StringIO):
    return [line for line in capture.getvalue().splitlines() if line.strip()]


def _matches_one_of(line: str, patterns) -> bool:
    return any(re.match(p, line) for p in patterns)


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, host):
        self.client = _FakeClient(host)
        self.headers = {}


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


@pytest.fixture(autouse=True)
def _reset_master_settings():
    original = settings.master_db_local_auth
    yield
    settings.master_db_local_auth = original


class TestMasterAuthFilterContract:
    """deploy/fail2ban/klepsydrix-master-auth.conf — les 3 lignes d'échec + la ligne de succès."""

    def test_failed_password_line_matches_failregex(self):
        failregex, _ = _parse_filter("klepsydrix-master-auth.conf")
        password_hash = master_auth._password_hasher.hash("correct-horse-battery-staple")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(enabled=True, password_hash=password_hash)

        with _capture("backend.app.core.master_auth") as capture:
            with pytest.raises(HTTPException):
                master_auth.verify_master_password(_FakeRequest("203.0.113.42"), "wrong-password")

        lines = _lines(capture)
        assert len(lines) == 1
        assert _matches_one_of(lines[0], failregex), f"ne matche aucune failregex : {lines[0]!r}"

    def test_ip_not_allowed_line_matches_failregex(self):
        failregex, _ = _parse_filter("klepsydrix-master-auth.conf")
        password_hash = master_auth._password_hasher.hash("correct-horse-battery-staple")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(
            enabled=True, password_hash=password_hash, ip_allowlist=["10.0.0.0/8"],
        )

        with _capture("backend.app.core.master_auth") as capture:
            with pytest.raises(HTTPException):
                master_auth.verify_master_password(_FakeRequest("203.0.113.42"), "whatever")

        lines = _lines(capture)
        assert len(lines) == 1
        assert _matches_one_of(lines[0], failregex), f"ne matche aucune failregex : {lines[0]!r}"

    def test_missing_password_hash_line_matches_failregex(self):
        failregex, _ = _parse_filter("klepsydrix-master-auth.conf")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(enabled=True, password_hash=None)

        with _capture("backend.app.core.master_auth") as capture:
            with pytest.raises(HTTPException):
                master_auth.verify_master_password(_FakeRequest("203.0.113.42"), "whatever")

        lines = _lines(capture)
        assert len(lines) == 1
        assert _matches_one_of(lines[0], failregex), f"ne matche aucune failregex : {lines[0]!r}"

    def test_success_line_matches_ignoreregex_and_never_failregex(self):
        """Le piège que ce filtre doit éviter à tout prix : bannir un super-admin légitime après
        une connexion RÉUSSIE (voir architecture.md §19.A)."""
        failregex, ignoreregex = _parse_filter("klepsydrix-master-auth.conf")
        password_hash = master_auth._password_hasher.hash("correct-horse-battery-staple")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(enabled=True, password_hash=password_hash)

        with _capture("backend.app.core.master_auth") as capture:
            master_auth.verify_master_password(_FakeRequest("203.0.113.42"), "correct-horse-battery-staple")

        lines = _lines(capture)
        assert len(lines) == 1
        assert _matches_one_of(lines[0], ignoreregex), f"ne matche pas ignoreregex : {lines[0]!r}"
        assert not _matches_one_of(lines[0], failregex), f"matche failregex à tort : {lines[0]!r}"


class TestLocalLoginFilterContract:
    """deploy/fail2ban/klepsydrix-local-login.conf"""

    def _make_local_account(self, db, identifier="a@example.fr", password="CorrectHorse8!"):
        user = User.create(db, {"first_name": "A", "last_name": "Local", "email": identifier})
        UserIdentityProvider.register_local_password(db, user.id, identifier, password)
        db.commit()

    def test_failed_login_line_matches_failregex(self, db_session):
        failregex, _ = _parse_filter("klepsydrix-local-login.conf")
        self._make_local_account(db_session)

        with _capture("backend.app.api.auth_endpoints") as capture:
            with pytest.raises(HTTPException):
                login_local(
                    LocalLoginPayload(identifier="a@example.fr", password="wrong"),
                    _FakeRequest("203.0.113.42"), Response(), db_session,
                )

        lines = _lines(capture)
        assert len(lines) == 1
        assert _matches_one_of(lines[0], failregex), f"ne matche aucune failregex : {lines[0]!r}"

    def test_successful_login_produces_no_matchable_line(self, db_session):
        """Rien à ignorer côté fail2ban pour la connexion locale (contrairement au mot de passe
        maître) : un succès n'est simplement jamais journalisé — voir login_local."""
        self._make_local_account(db_session)

        with _capture("backend.app.api.auth_endpoints") as capture:
            login_local(
                LocalLoginPayload(identifier="a@example.fr", password="CorrectHorse8!"),
                _FakeRequest("203.0.113.42"), Response(), db_session,
            )

        assert _lines(capture) == []
