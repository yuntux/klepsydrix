"""
Limitation de débit applicative sur les points d'entrée d'authentification (voir architecture.md
§17.H et §19.A).

**Ce que ce module change par rapport à la décision antérieure.** Jusqu'ici, la protection
anti-brute-force était ENTIÈREMENT déléguée à fail2ban : l'application se contentait de journaliser
chaque échec dans un format que le filtre déployé sait lire (`deploy/fail2ban/`, contrat vérifié par
`tests/test_fail2ban_filter_contracts.py`), et n'opposait elle-même aucune limite. La décision était
raisonnée — fail2ban bannit au niveau réseau, ce qui coûte moins cher et protège toute la machine —
mais elle était BINAIRE : là où fail2ban n'est pas déployé, il ne restait rien. Or ces cas sont
ordinaires : conteneur sans accès aux journaux de l'hôte, instance de démonstration, hébergement
sans main sur le pare-feu, ou simple erreur d'installation — laquelle ne se voit pas, un service
sans anti-brute-force se comportant exactement comme un service protégé.

Ce limiteur ne remplace donc pas fail2ban (toujours préférable : plus tôt dans la pile, et il couvre
tous les services de la machine) : il garantit un plancher qui suit le code partout où il tourne.
Les deux cohabitent sans se gêner — les journaux restent émis à l'identique.

**Portée assumée** : compteur EN MÉMOIRE du process. Un redémarrage remet les compteurs à zéro, et
plusieurs process (répartition de charge) auraient chacun le leur. C'est la même limite que
`SolverState` (voir architecture.md §16.C) et elle est acceptable pour la même raison : l'hypothèse
d'un process unique par déploiement. Un attaquant ne peut pas provoquer ce redémarrage.
"""
import logging
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# {(seau, clé): deque des horodatages des tentatives retenues}
_attempts: dict[tuple[str, str], deque] = defaultdict(deque)


def reset_all() -> None:
    """Vide les compteurs — réservé aux tests (l'état est process-wide, il fuirait d'un test à
    l'autre)."""
    _attempts.clear()


def _window_seconds() -> int:
    return settings.auth.rate_limit_window_minutes * 60


def _prune(key: tuple[str, str], now: float) -> deque:
    timestamps = _attempts[key]
    horizon = now - _window_seconds()
    while timestamps and timestamps[0] < horizon:
        timestamps.popleft()
    return timestamps


def enforce(bucket: str, key: str, *, ip: str = "?") -> None:
    """
    Refuse (429) si `key` a déjà épuisé son quota dans la fenêtre glissante. À appeler AVANT de
    faire le travail coûteux (vérification Argon2, envoi d'email).

    `bucket` sépare les compteurs par usage (une tentative de connexion ne doit pas consommer le
    quota de réinitialisation de mot de passe) ; `key` identifie l'auteur — en pratique l'IP,
    éventuellement combinée à l'identifiant visé, pour qu'un attaquant qui balaie mille comptes
    depuis une IP soit arrêté aussi vite que celui qui s'acharne sur un seul.
    """
    if settings.auth.rate_limit_attempts <= 0:  # 0 = désactivé (voir instance.example.yaml)
        return
    timestamps = _prune((bucket, key), time.monotonic())
    if len(timestamps) >= settings.auth.rate_limit_attempts:
        logger.warning(
            "Limite de débit atteinte sur %s depuis %s — requête refusée (429)", bucket, ip,
        )
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives. Réessayez dans quelques minutes.",
        )


def record(bucket: str, key: str) -> None:
    """Enregistre une tentative retenue. Appelé APRÈS coup pour les connexions (seuls les ÉCHECS
    comptent — une session légitime qui se reconnecte souvent ne doit pas s'auto-bloquer), et à
    chaque appel pour ce qui n'a pas de notion d'échec (réinitialisation de mot de passe, dont la
    réponse est toujours la même par construction)."""
    if settings.auth.rate_limit_attempts <= 0:
        return
    now = time.monotonic()
    _prune((bucket, key), now).append(now)
