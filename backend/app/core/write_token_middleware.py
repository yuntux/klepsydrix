"""
Middleware HTTP du mécanisme "jeton d'écriture" (voir core/exclusive_mode.py, architecture.md) :
- Attache le jeton d'écriture COURANT à chaque réponse (lecture ET écriture), dans l'en-tête
  `X-Write-Token` — permet au frontend de détecter, sur n'importe quelle requête (pas seulement
  une écriture), que ses données locales sont devenues périmées (ex: une résolution automatique
  vient de se terminer et a déplacé des cours), et de se recharger silencieusement AVANT même de
  tenter une écriture qui serait, elle, rejetée.
- Pour les méthodes d'écriture (POST/PUT/PATCH/DELETE), rejette la requête (409) avant même
  qu'elle n'atteigne le handler si le jeton envoyé par le navigateur ne correspond pas au jeton
  courant — évite tout travail inutile (et toute écriture basée sur une hypothèse fausse sur
  l'état des données) pour une requête qu'on sait déjà périmée.

Un jeton absent de la requête (client qui ne participe pas encore à ce mécanisme, script interne,
tests) n'est PAS rejeté : seul un jeton présent MAIS différent du jeton courant déclenche un rejet
— ce mécanisme est un filet de sécurité additif, pas une authentification obligatoire.

Complémentaire, pas redondant, avec le blocage ORM (before_flush, exclusive_mode.py) : le jeton
détecte "vos données sont périmées", le mode exclusif bloque "une résolution tourne là, maintenant,
peu importe la fraîcheur de votre jeton" (utile pour la requête déjà en vol au moment où une
résolution démarre).
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from backend.app.core.database import SessionLocal
from backend.app.core.exclusive_mode import get_write_token

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_SKIP_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/api/openapi.json")


class WriteTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith(_SKIP_PREFIXES):
            return await call_next(request)

        db = SessionLocal()
        try:
            current_token = get_write_token(db)
        finally:
            db.close()

        incoming_token = request.headers.get("x-write-token")

        if (
            request.method in WRITE_METHODS
            and incoming_token
            and current_token
            and incoming_token != current_token
        ):
            response = JSONResponse(
                status_code=409,
                content={
                    "detail": "Les données ont été modifiées depuis votre dernier chargement "
                              "(ex: une résolution automatique vient de se terminer). Rechargez la page avant de réessayer."
                },
            )
            response.headers["X-Write-Token"] = current_token
            return response

        response = await call_next(request)
        if current_token:
            response.headers["X-Write-Token"] = current_token
        return response
