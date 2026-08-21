"""
Contrôles de configuration passés au DÉMARRAGE (voir main.py::lifespan, à côté de
`route_guard.assert_all_routes_scoped` — même principe : ce qui peut être vérifié une fois pour
toutes au démarrage ne doit pas dépendre de la vigilance de qui déploie).

Deux niveaux, jamais confondus :
- **refus de démarrer** (`ConfigurationError`) pour ce qui rendrait l'authentification décorative
  dans un déploiement réellement exposé ;
- **avertissement journalisé** pour ce qui est légitime en développement mais douteux ailleurs.

Le critère qui sépare les deux n'est PAS une variable d'environnement à penser (un déploiement qui
l'oublie est exactement le cas qu'on veut couvrir) mais `server.public_base_url` : il porte déjà le
nom de domaine réel en production — sans lui, les liens de réinitialisation de mot de passe envoyés
par email sont inutilisables (voir core/mailer.py), il ne peut donc pas rester au défaut dans un
déploiement en service.
"""
import logging
from urllib.parse import urlparse

from backend.app.core.config import settings, DEMO_SECRET_KEY

logger = logging.getLogger(__name__)

# Hôtes considérés comme un poste de développement — voir docstring du module.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


class ConfigurationError(RuntimeError):
    """Configuration refusée au démarrage — jamais rattrapée, le process ne doit pas servir."""


def is_local_deployment() -> bool:
    host = (urlparse(settings.server.public_base_url).hostname or "").lower()
    return host in _LOCAL_HOSTS


def assert_safe_configuration() -> None:
    """Lève ConfigurationError, ou journalise, ou ne fait rien. Appelée par le lifespan."""
    local = is_local_deployment()

    # `secret_key` signe les cookies de session instance (itsdangerous, core/instance_session.py) :
    # quiconque connaît la valeur de démonstration — publique, elle est dans le dépôt — peut forger
    # une session pour n'importe quelle identité, Y COMPRIS `provider_key="__master__"`, donc la
    # console d'administration d'instance (créer/supprimer/restaurer n'importe quelle base). Le
    # commentaire de config.py avertissait déjà ; il ne servait à rien tant que le serveur démarrait
    # quand même.
    if settings.secret_key == DEMO_SECRET_KEY:
        if not local:
            raise ConfigurationError(
                "secret_key est resté à la valeur de démonstration, publique (voir "
                "instance.example.yaml) : n'importe qui peut forger une session, y compris celle "
                "du mot de passe maître. Renseignez `secret_key` dans instance.yaml (idéalement "
                "via ${env:KLEPSYDRIX_SECRET_KEY}) avant de servir sur "
                f"{settings.server.public_base_url}."
            )
        logger.warning(
            "secret_key est la valeur de démonstration — accepté ici parce que "
            "server.public_base_url pointe sur un poste local ; à changer IMPÉRATIVEMENT avant "
            "tout déploiement réel."
        )

    # Le mot de passe maître est un secret PARTAGÉ au rayon d'action très large (voir
    # core/master_auth.py) : sans restriction d'IP, il est atteignable depuis n'importe où sur
    # Internet. Avertissement seulement — c'est la seule voie vers le statut super-admin sur une
    # instance sans OIDC fédéré (§19.A), la refuser bloquerait des déploiements légitimes.
    master = settings.master_db_local_auth
    if master.enabled and not master.ip_allowlist and not local:
        logger.warning(
            "master_db_local_auth est actif sans ip_allowlist : le mot de passe maître est "
            "atteignable depuis n'importe quelle adresse. Restreignez-le, ou désactivez-le si un "
            "fournisseur OIDC fédéré assure déjà l'accès super-admin (voir architecture.md §19.A)."
        )

    # Cohérence transport : en https, les cookies partent avec `Secure` (voir
    # instance_session.py::cookies_secure) — l'inverse (prod en http clair) laisse le cookie de
    # session circuler en clair, et rend `SameSite=Lax` inopérant face à un attaquant réseau.
    if not local and not settings.server.public_base_url.lower().startswith("https://"):
        logger.warning(
            "server.public_base_url n'est pas en https : les cookies de session ne porteront pas "
            "l'attribut Secure et circuleront en clair (voir architecture.md §20.C)."
        )
