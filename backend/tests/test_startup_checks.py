"""
Gardes de configuration au démarrage (core/startup_checks.py) et refus du joker CORS
(core/config.py::ServerConfig). Deux mécanismes distincts, réunis ici parce qu'ils protègent la
même chose : une instance réellement exposée qui aurait gardé une configuration de développement.
"""
import logging
import pytest
from pydantic import ValidationError

from backend.app.core.config import DEMO_SECRET_KEY, ServerConfig, settings
from backend.app.core.startup_checks import ConfigurationError, assert_safe_configuration


@pytest.fixture(autouse=True)
def _restore_settings():
    """`settings` est un singleton process-wide (voir conftest.py::override_settings pour le même
    principe) — chaque test restaure ce qu'il a modifié."""
    original_secret = settings.secret_key
    original_server = settings.server
    original_master = settings.master_db_local_auth
    yield
    settings.secret_key = original_secret
    settings.server = original_server
    settings.master_db_local_auth = original_master


def _serve_on(url: str):
    settings.server = ServerConfig(public_base_url=url)


class TestDemoSecretKey:
    def test_refuses_to_start_when_exposed(self):
        """La valeur de démonstration est publique (elle est dans le dépôt) : la connaître suffit à
        forger une session pour n'importe quelle identité, mot de passe maître compris."""
        settings.secret_key = DEMO_SECRET_KEY
        _serve_on("https://klepsydrix.exemple.fr")

        with pytest.raises(ConfigurationError, match="secret_key"):
            assert_safe_configuration()

    def test_is_tolerated_but_warned_about_on_a_local_host(self, caplog):
        settings.secret_key = DEMO_SECRET_KEY
        _serve_on("http://localhost:3000")

        with caplog.at_level(logging.WARNING, logger="backend.app.core.startup_checks"):
            assert_safe_configuration()  # ne lève pas : le poste de développement doit démarrer

        assert any("secret_key" in r.message for r in caplog.records)

    def test_a_real_secret_key_passes_anywhere(self):
        settings.secret_key = "une-vraie-cle-de-signature-tres-longue"
        _serve_on("https://klepsydrix.exemple.fr")

        assert_safe_configuration()  # ne lève rien


class TestMasterPasswordExposure:
    def test_warns_when_enabled_without_ip_allowlist_in_production(self, caplog):
        settings.secret_key = "une-vraie-cle-de-signature-tres-longue"
        _serve_on("https://klepsydrix.exemple.fr")
        settings.master_db_local_auth = type(settings.master_db_local_auth)(
            enabled=True, password_hash="$argon2id$peu-importe", ip_allowlist=[],
        )

        with caplog.at_level(logging.WARNING, logger="backend.app.core.startup_checks"):
            assert_safe_configuration()

        assert any("ip_allowlist" in r.message for r in caplog.records)


class TestAllowedOriginsValidation:
    def test_wildcard_is_refused(self):
        """Avec allow_credentials=True, Starlette renvoie l'ORIGINE APPELANTE au lieu de '*' —
        n'importe quel site pourrait lire l'API avec le cookie de session de la victime."""
        with pytest.raises(ValidationError, match=r"\*"):
            ServerConfig(allowed_origins=["*"])

    def test_origin_without_scheme_is_refused(self):
        with pytest.raises(ValidationError, match="schéma"):
            ServerConfig(allowed_origins=["klepsydrix.exemple.fr"])

    def test_explicit_origins_are_accepted(self):
        config = ServerConfig(allowed_origins=["https://klepsydrix.exemple.fr", "http://localhost:3000"])
        assert len(config.allowed_origins) == 2
