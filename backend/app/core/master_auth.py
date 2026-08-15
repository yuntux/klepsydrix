"""
Authentification par mot de passe maître pour la console d'administration d'instance — voir
architecture.md §19.A, config.py::MasterAuthConfig. Pas juste un filet de secours occasionnel : sur
une instance sans fournisseur OIDC fédéré actif, c'est la SEULE voie vers le statut super-admin (voir
§19.A, provider_key "local" refusé dans super_admins). Chapitre volontairement défensif malgré tout :
c'est un secret PARTAGÉ (contrairement aux paires nommées de `super_admins`, individuellement
attribuables), avec un rayon d'action large (créer/supprimer n'importe quelle base) — traité avec la
même prudence qu'un compte root cloud : identité fantôme jamais confondue avec un vrai utilisateur,
journalisation systématique et bien visible, restriction IP optionnelle.

⚠️ AUCUN verrouillage anti-brute-force applicatif ici (retiré délibérément — voir architecture.md
§19.A pour la décision et son raisonnement complet) : la protection contre le brute-force est
ENTIÈREMENT déléguée à fail2ban (`deploy/fail2ban/klepsydrix-master-auth.conf`), qui lit les lignes
`WARNING` journalisées ci-dessous. Un test dédié (`backend/tests/test_fail2ban_filter_contracts.py`)
vérifie que le format de ces lignes correspond bien au filtre fail2ban RÉELLEMENT déployé — sans ce
test, un changement de message ici casserait fail2ban en silence.
"""
import ipaddress
import logging
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from fastapi import HTTPException, Request

from backend.app.core.config import settings
from backend.app.core.client_ip import client_ip as _client_ip

logger = logging.getLogger(__name__)

_password_hasher = PasswordHasher()

# Provider_key réservé, jamais produit par un vrai fournisseur configuré (identity_providers ne
# permet pas cette valeur en pratique — voir set_session_cookie) : la session issue du mot de passe
# maître ne peut donc jamais être confondue avec un vrai UserIdentityProvider dans aucune base.
MASTER_PROVIDER_KEY = "__master__"
MASTER_SUBJECT = "master"


def _ip_allowed(ip: str) -> bool:
    """Liste vide = aucune restriction (choix explicite, documenté dans instance.example.yaml) —
    sinon l'IP doit correspondre à au moins une entrée (adresse exacte ou bloc CIDR)."""
    allowlist = settings.master_db_local_auth.ip_allowlist
    if not allowlist:
        return True
    try:
        client_addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in allowlist:
        try:
            if client_addr in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def verify_master_password(request: Request, password: str) -> None:
    """
    Lève HTTPException (404 si le mode est désactivé — ne révèle même pas que la route existe ;
    403 si IP non autorisée ; 401 si mot de passe incorrect) ou ne retourne rien en cas de succès.
    Journalise TOUTE tentative à un niveau impossible à manquer (WARNING) — c'est CE journal, lu par
    fail2ban, qui porte la protection anti-brute-force (voir docstring du module).
    """
    cfg = settings.master_db_local_auth
    ip = _client_ip(request)

    if not cfg.enabled:
        raise HTTPException(status_code=404)

    if not _ip_allowed(ip):
        logger.warning("Authentification maître refusée (IP hors liste autorisée) depuis %s", ip)
        raise HTTPException(status_code=403, detail="Accès refusé.")

    if not cfg.password_hash:
        logger.warning("Authentification maître activée sans db_master_password_hash configuré — refusée depuis %s", ip)
        raise HTTPException(status_code=403, detail="Accès refusé.")

    try:
        _password_hasher.verify(cfg.password_hash, password)
    except (VerifyMismatchError, InvalidHash):
        logger.warning("Échec d'authentification maître depuis %s", ip)
        raise HTTPException(status_code=401, detail="Mot de passe incorrect.")

    logger.warning("Authentification maître RÉUSSIE depuis %s — accès complet à la console d'administration", ip)
