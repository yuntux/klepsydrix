from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.config import settings
from backend.app.core.write_token_middleware import WriteTokenMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Un mode exclusif encore actif en base au démarrage ne peut être que le résidu d'un arrêt
    # brutal du process précédent (kill, crash) pendant une résolution — puisqu'on vient tout
    # juste de démarrer, aucune résolution n'est réellement en cours. Sans ce nettoyage, ce résidu
    # bloquerait toute écriture indéfiniment. Ne touche PAS le jeton d'écriture : les données en
    # base n'ont pas changé du fait de ce redémarrage (voir core/exclusive_mode.py).
    from backend.app.core.database import SessionLocal
    from backend.app.core.exclusive_mode import clear_exclusive_mode
    db = SessionLocal()
    try:
        clear_exclusive_mode(db)
    finally:
        db.close()
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
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # X-Write-Token (voir core/write_token_middleware.py) : sans expose_headers, le navigateur
    # bloque silencieusement la lecture de tout en-tête de réponse "custom" par le JS appelant
    # (fetch), même si la requête elle-même passe — allow_headers ne contrôle que les en-têtes de
    # REQUÊTE autorisés, pas ceux exposés en retour.
    expose_headers=["X-Write-Token"],
)

# Mode exclusif + jeton d'écriture (voir core/exclusive_mode.py, core/write_token_middleware.py) :
# doit envelopper TOUTES les routes, générique comme non-générique (RPC, /timetable/*), d'où un
# middleware plutôt qu'une dépendance posée route par route.
app.add_middleware(WriteTokenMiddleware)

# Point d'entrée de santé (Healthcheck) et de bienvenue de l'API
@app.get("/")
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

app.include_router(api_router)
app.include_router(generic_router)
app.include_router(ui_router)

@app.get("/test-openapi")
def test_openapi():
    try:
        return app.openapi()
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}
