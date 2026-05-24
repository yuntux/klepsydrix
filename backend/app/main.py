from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc"
)

# Configuration du middleware CORS pour autoriser l'IHM Vue 3 (Vite)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(api_router)
app.include_router(generic_router)

@app.get("/test-openapi")
def test_openapi():
    try:
        return app.openapi()
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}
