import logging
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from backend.app.core.config import settings
from backend.app.core.database import check_write_token, current_db_user
from backend.app.core.log_context import attach_to_handlers, DbSlugContextMiddleware
from backend.app.core.route_guard import assert_all_routes_scoped, system_scoped
from backend.app.core.error_handlers import register_exception_handlers

# Logs applicatifs contextualisés par base (voir architecture.md, "Architecture de routage HTTP",
# core/log_context.py::attach_to_handlers pour le détail du piège évité). Les logs d'accès uvicorn
# eux-mêmes ne sont pas encore reformatés (nécessiterait de surcharger la config de logging
# d'uvicorn) — limite connue, pas encore traitée à ce stade du chantier.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [db=%(db_slug)s] %(name)s: %(message)s",
)
attach_to_handlers(logging.getLogger())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Un mode exclusif encore actif en base au démarrage ne peut être que le résidu d'un arrêt
    # brutal du process précédent (kill, crash) pendant une résolution — puisqu'on vient tout
    # juste de démarrer, aucune résolution n'est réellement en cours. Sans ce nettoyage, ce résidu
    # bloquerait toute écriture indéfiniment. Ne touche PAS le jeton d'écriture : les données en
    # base n'ont pas changé du fait de ce redémarrage (voir core/exclusive_mode.py).
    # Uniquement la base par défaut mono-process (DEFAULT_DB_NAME) : les autres bases de l'instance
    # ne sont nettoyées qu'à la première requête qui les résout (voir get_db/resolve_database).
    from backend.app.core.database import SessionLocal
    from backend.app.core.exclusive_mode import clear_exclusive_mode
    db = SessionLocal()
    try:
        clear_exclusive_mode(db)
    finally:
        db.close()

    # Refuse de démarrer si une route n'est ni authentifiée ni marquée @system_scoped — voir
    # core/route_guard.py pour le pourquoi (une route qui oublie current_db_user ne plante pas,
    # elle répond en mode système avec toutes les données). Ici plutôt qu'au niveau module : les
    # include_router() ont déjà tous été exécutés à l'import, l'inventaire des routes est complet.
    assert_all_routes_scoped(app)

    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# Configuration du middleware CORS pour autoriser l'IHM Vue 3 (Vite)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # X-Write-Token/X-Klepsydrix-Database : sans expose_headers, le navigateur bloque
    # silencieusement la lecture de tout en-tête de réponse "custom" par le JS appelant (fetch),
    # même si la requête elle-même passe — allow_headers ne contrôle que les en-têtes de REQUÊTE
    # autorisés, pas ceux exposés en retour.
    expose_headers=["X-Write-Token", "X-Klepsydrix-Database"],
)

# Session Starlette dédiée à Authlib (state/nonce OIDC, voir core/oidc.py) — un cookie distinct de
# klepsydrix_session (notre propre session instance, voir core/instance_session.py) : celui-ci ne
# sert qu'à sécuriser l'aller-retour vers le fournisseur d'identité, pas à authentifier l'usager.
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")

# Pose current_db_slug tôt, au niveau ASGI — voir core/log_context.py::DbSlugContextMiddleware pour
# le pourquoi (un ContextVar posé dans une dépendance FastAPI synchrone ne se propage pas aux
# dépendances/l'endpoint suivants, voir architecture.md §16.F).
app.add_middleware(DbSlugContextMiddleware)

# Un refus du moteur de droits doit être un 403 partout, y compris sur les chemins qu'aucun
# try/except n'enveloppe (voir core/error_handlers.py) — sans quoi il remonterait en 500.
register_exception_handlers(app)

# Point d'entrée de santé (Healthcheck) et de bienvenue de l'API — portée instance, aucune base
# résolue (voir architecture.md, "Architecture de routage HTTP").
@app.get("/")
@system_scoped("Healthcheck : doit répondre sans aucune session, y compris à une sonde de supervision. Ne sert aucune donnée de base.")
def read_root():
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "version": "0.1.0",
        "documentation": f"{settings.API_V1_STR}/docs"
    }

from backend.app.api.endpoints import router as api_router
from backend.app.api.generic import router as generic_router
from backend.app.api.ui_endpoints import router as ui_router
from backend.app.api.instance_endpoints import router as instance_router
from backend.app.api.auth_endpoints import router as auth_router

# current_db_user exige une session instance valide (Depends(require_instance_session)) ET résout/
# crée le User de la base courante ; check_write_token exige l'en-tête X-Klepsydrix-Database (via
# get_db) et fait respecter le jeton d'écriture. Les poser en dépendances de routeur suffit à
# imposer les deux sur TOUTES les routes applicatives, générique comme non-générique (RPC,
# /timetable/*), sans rien écrire par endpoint — remplace l'ancien WriteTokenMiddleware (voir
# architecture.md). ui_router (menus) déclare sa propre dépendance current_db_user par route (pas
# check_write_token, non concerné par le jeton d'écriture) — voir ui_endpoints.py::get_menus, dont
# le filtrage par droits (lot menu/droits) a justement besoin de connaître l'utilisateur.
app.include_router(api_router, dependencies=[Depends(current_db_user), Depends(check_write_token)])
app.include_router(generic_router, dependencies=[Depends(current_db_user), Depends(check_write_token)])
app.include_router(ui_router)
app.include_router(instance_router)
app.include_router(auth_router)
