"""
En-têtes de sécurité posés sur chaque réponse de l'API.

⚠️ **Portée réelle, à ne pas surestimer** : cette application sert une API, jamais la page HTML de
l'IHM (Vite en développement, un serveur de fichiers statiques ou le reverse proxy en production —
voir architecture.md §20.C). Or les en-têtes qui protègent un UTILISATEUR contre du HTML hostile
(au premier rang desquels `Content-Security-Policy`) ne valent que pour le DOCUMENT dans lequel le
script s'exécuterait : les poser ici ne protège pas l'IHM. La CSP qui compte pour l'IHM doit être
servie avec `index.html`, donc configurée là où il est servi — la valeur recommandée est documentée
dans architecture.md §20.C, elle n'a pas d'équivalent côté code Python.

Ce qui est posé ici garde malgré tout un sens propre aux réponses d'API :
- `X-Content-Type-Options: nosniff` — empêche un navigateur de RE-DEVINER le type d'une réponse
  (un JSON dont le contenu commence par du HTML, un PDF de rapport…) et de l'exécuter comme un
  document. C'est le seul de la liste qui protège directement quelque chose que nous servons.
- `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'` — la
  politique correcte pour une ressource qui n'est PAS un document : si une réponse d'API finissait
  malgré tout interprétée comme du HTML, elle ne pourrait charger ni script, ni image, ni feuille
  de style. `frame-ancestors` interdit en outre de l'encadrer (clickjacking), ce que
  `X-Frame-Options` ne dit plus que pour les navigateurs anciens.
- `Referrer-Policy: same-origin` — une URL d'API porte des identifiants de ressources ; elle n'a
  aucune raison de fuiter vers un site tiers via l'en-tête `Referer`.

**Exception `/api/docs`** : Swagger UI et ReDoc sont de VRAIES pages HTML, servies par FastAPI, qui
chargent leurs scripts et feuilles de style depuis un CDN. `default-src 'none'` les rendrait
blanches. Elles sont donc exclues de la CSP (et d'elles seules) — la documentation interactive est
un outil de travail quotidien du projet, la casser pour un gain nul serait un mauvais échange.
"""
from backend.app.core.config import settings

# Une ressource qui n'est pas un document : rien à charger, rien à encadrer, aucune URL de base.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

SECURITY_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"referrer-policy": b"same-origin",
    # Doublon volontaire de `frame-ancestors` pour les navigateurs qui ne lisent pas la CSP.
    b"x-frame-options": b"DENY",
}

_DOCS_PATHS = {
    f"{settings.API_V1_STR}/docs",
    f"{settings.API_V1_STR}/redoc",
    f"{settings.API_V1_STR}/docs/oauth2-redirect",
}


class SecurityHeadersMiddleware:
    """Middleware ASGI « brut » — même choix que DbSlugContextMiddleware/OriginCheckMiddleware, voir
    core/log_context.py pour le raisonnement."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        with_csp = scope.get("path") not in _DOCS_PATHS

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                existing = {name.lower() for name, _ in headers}
                for name, value in SECURITY_HEADERS.items():
                    if name not in existing:
                        headers.append((name, value))
                if with_csp and b"content-security-policy" not in existing:
                    headers.append((b"content-security-policy", API_CSP.encode("latin-1")))
            await send(message)

        await self.app(scope, receive, send_with_headers)
