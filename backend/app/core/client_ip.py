"""
IP source d'une requête HTTP (voir architecture.md §19.A) — utilisé par tout mécanisme qui a besoin
de la VRAIE IP cliente pour une décision de sécurité (mot de passe maître, verrouillage anti-
brute-force sur la connexion locale...). Extrait de `core/master_auth.py` (premier appelant) dès
qu'un second appelant (`api/auth_endpoints.py::login_local`) en a eu besoin — même mécanisme, pas de
duplication.
"""
import ipaddress
from fastapi import Request

from backend.app.core.config import settings


def _is_trusted_proxy(ip: str) -> bool:
    trusted = settings.server.trusted_proxies
    if not trusted:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in trusted:
        try:
            if addr in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: Request) -> str:
    """
    Lit `X-Forwarded-For` UNIQUEMENT si la connexion TCP directe vient d'un proxy listé dans
    `server.trusted_proxies` (voir config.py), jamais sinon : cet en-tête est un simple en-tête
    HTTP, entièrement falsifiable par n'importe quel appelant si personne ne le filtre en amont — le
    lire sans condition rendrait tout contrôle basé sur l'IP contournable par quiconque en fixant
    lui-même cet en-tête.

    Hypothèse : un SEUL reverse proxy devant l'appli (voir architecture.md §20.C), configuré pour
    toujours ÉCRASER/fixer cet en-tête lui-même plutôt que de transmettre tel quel une valeur reçue du
    client (comportement par défaut de Caddy/nginx correctement configurés — voir §20.C) — la
    PREMIÈRE valeur de la liste (ce que CE proxy de confiance vient d'y écrire pour cette requête) est
    alors l'IP réelle du client, pas falsifiable par lui puisque le proxy de confiance l'a réécrite.
    """
    direct_ip = request.client.host if request.client else None
    if direct_ip and _is_trusted_proxy(direct_ip):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return direct_ip or "unknown"
