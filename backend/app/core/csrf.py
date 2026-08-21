"""
Contrôle d'origine sur les méthodes d'écriture — protection CSRF EXPLICITE (voir architecture.md,
"Architecture de routage HTTP").

Avant ce module, l'application n'était pas vulnérable au CSRF, mais par accumulation d'effets de
bord plutôt que par intention : trois barrières héritées d'autres décisions, dont aucune n'était
testée en tant que protection.

1. `SameSite=Lax` sur le cookie de session (instance_session.py) — angle mort : un attaquant
   « same-site » (autre sous-domaine du même domaine enregistrable, cas courant en hébergement
   mutualisé) n'est pas concerné par cette restriction, et un déploiement en HTTP clair non plus.
2. L'en-tête `X-Klepsydrix-Database`, obligatoire sur toutes les routes applicatives : un en-tête
   personnalisé force un préflight CORS qu'une origine étrangère ne passe pas. Mais les routes
   d'instance et d'authentification ne l'exigent pas.
3. Le corps JSON : FastAPI ne désérialise un corps que si `Content-Type: application/json`, un type
   non « simple » qui force lui aussi un préflight — un `<form>` HTML ne peut donc pas livrer de
   charge utile. Sauf aux routes sans corps (`/logout`) ou à paramètres d'URL.

Ce middleware transforme ces coïncidences en règle unique et vérifiable : sur toute méthode
d'écriture, l'origine de l'appelant doit être connue. Il ne remplace aucune des trois barrières —
il les rend explicites, testables (`tests/test_csrf.py`), et indépendantes du détail de chaque
route.

**Absence d'`Origin` ET de `Referer` : la requête PASSE.** Un navigateur envoie systématiquement
`Origin` sur une méthode d'écriture — c'est précisément le cas qu'on veut arbitrer. Une requête sans
ni l'un ni l'autre ne vient donc pas d'un navigateur (curl, script d'intégration, sonde, TestClient),
c'est-à-dire d'un contexte où le CSRF n'a aucun sens : il n'y a pas de cookie ambiant qu'un tiers
pourrait faire jouer à son profit. Refuser ici casserait tout l'outillage sans rien protéger.
"""
from urllib.parse import urlparse

from starlette.responses import JSONResponse

from backend.app.core.config import settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _origin_of(url: str) -> str | None:
    """« https://hote:port » d'une URL absolue, ou None si elle n'en est pas une."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def is_allowed_origin(origin: str, host_header: str | None, tls: bool) -> bool:
    """
    Origines acceptées : celles configurées pour le CORS (`server.allowed_origins`, qui refuse déjà
    le joker — voir config.py::ServerConfig) **et** l'origine de l'application elle-même, reconstruite
    depuis l'en-tête `Host` de la requête.

    Pourquoi ajouter `Host` : en développement comme derrière un reverse proxy, l'IHM et l'API sont
    servies sur la MÊME origine (Vite proxifie `/api`, voir vite.config.ts) — cette origine-là n'a
    aucune raison d'être listée dans `allowed_origins`, dont le rôle est d'autoriser les origines
    TIERCES. Sans cette reconstruction, le fonctionnement normal serait refusé.

    `Host` est fourni par le client et donc falsifiable — sans conséquence ici : un attaquant qui
    contrôle `Host` contrôle déjà `Origin`, et le navigateur de la VICTIME, lui, envoie toujours le
    `Host` réel du site visité. Ce n'est pas ce champ qui porte la décision de sécurité.
    """
    allowed = set(settings.server.allowed_origins)
    if host_header:
        allowed.add(f"{'https' if tls else 'http'}://{host_header}")
        # Le proxy peut terminer le TLS et parler http en interne (voir architecture.md §20.C) :
        # le navigateur, lui, a bien vu https. Les deux formes sont acceptées pour le même hôte.
        allowed.add(f"https://{host_header}")
    return origin in allowed


class OriginCheckMiddleware:
    """
    Middleware ASGI « brut » (même choix que `DbSlugContextMiddleware`, voir log_context.py pour le
    raisonnement : pas de `BaseHTTPMiddleware`, pour ne rien perturber des réponses en flux et des
    tâches d'arrière-plan, ex. `FileResponse` + `BackgroundTask` de la sauvegarde de base).
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        headers = {name.decode("latin-1").lower(): value.decode("latin-1") for name, value in scope.get("headers", ())}
        # `Origin` d'abord ; `Referer` seulement en repli (certains navigateurs anciens ne posent pas
        # `Origin`), et réduit à sa seule origine — le chemin complet n'est pas notre affaire.
        origin = headers.get("origin") or _origin_of(headers.get("referer", ""))
        if origin is None:
            await self.app(scope, receive, send)  # requête non-navigateur, voir docstring du module
            return

        if not is_allowed_origin(origin, headers.get("host"), tls=scope.get("scheme") == "https"):
            response = JSONResponse(
                status_code=403,
                content={"detail": {"code": "CROSS_ORIGIN_REFUSED"}},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
