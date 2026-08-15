"""
Régression pour `core/log_context.py::DbSlugContextMiddleware` — voir architecture.md §16.F. Le
mécanisme qu'il remplace (`ContextVar.set(...)` posé dans `resolve_database`, une dépendance FastAPI
SYNCHRONE) ne se propageait PAS aux dépendances/l'endpoint suivants, même au sein d'une seule et
même requête : FastAPI exécute chaque dépendance synchrone via `anyio.to_thread.run_sync`, qui copie
le `contextvars.Context` ambiant dans un thread séparé À CHAQUE dépendance — une mutation faite dans
la copie utilisée par une dépendance ne se propage jamais à celle utilisée par la suivante. Reproduit
ci-dessous avec un cas minimal AVANT toute correction (`test_contextvar_set_in_a_sync_dependency_
does_not_propagate_to_the_next_one`), puis vérifié que `DbSlugContextMiddleware`, lui, corrige
précisément ce problème.
"""
from contextvars import ContextVar

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from backend.app.core.log_context import DbSlugContextMiddleware, current_db_slug
from backend.app.core.db_registry import SLUG_PATTERN


def test_contextvar_set_in_a_sync_dependency_does_not_propagate_to_the_next_one():
    """Reproduit le bug d'origine (voir docstring du module) — sert de garde-fou : si FastAPI/anyio
    changeaient un jour de comportement et que ce test se mettait à ÉCHOUER, ce serait le signal que
    le contournement par middleware n'est peut-être plus nécessaire."""
    probe: ContextVar[str] = ContextVar("probe", default="-")
    app = FastAPI()

    def dep_a(request: Request):
        probe.set("resolved-in-dep-a")
        return "a"

    def dep_b(a=Depends(dep_a)):
        return probe.get()

    @app.get("/test")
    def endpoint(b=Depends(dep_b)):
        return {"from_dep_b": b, "from_endpoint": probe.get()}

    client = TestClient(app)
    body = client.get("/test").json()

    assert body == {"from_dep_b": "-", "from_endpoint": "-"}


def test_middleware_makes_the_contextvar_visible_to_sync_dependencies_and_the_endpoint():
    app = FastAPI()
    app.add_middleware(DbSlugContextMiddleware)

    def dep_a(request: Request):
        return "a"  # ne pose plus rien lui-même — c'est le middleware qui s'en charge désormais

    def dep_b(a=Depends(dep_a)):
        return current_db_slug.get()

    @app.get("/test")
    def endpoint(b=Depends(dep_b)):
        return {"from_dep_b": b, "from_endpoint": current_db_slug.get()}

    client = TestClient(app)
    body = client.get("/test", headers={"X-Klepsydrix-Database": "timetable"}).json()

    assert body == {"from_dep_b": "timetable", "from_endpoint": "timetable"}


def test_missing_header_leaves_the_default_value():
    app = FastAPI()
    app.add_middleware(DbSlugContextMiddleware)

    @app.get("/test")
    def endpoint():
        return {"slug": current_db_slug.get()}

    client = TestClient(app)
    assert client.get("/test").json() == {"slug": "-"}


def test_malformed_header_is_rejected_not_injected_into_logs():
    """Défense contre l'injection de log : l'en-tête est entièrement contrôlé par l'appelant — une
    valeur qui ne respecte pas SLUG_PATTERN (ex: contenant un saut de ligne) ne doit jamais atteindre
    `current_db_slug`, sans quoi elle s'injecterait telle quelle dans chaque ligne de log."""
    app = FastAPI()
    app.add_middleware(DbSlugContextMiddleware)

    @app.get("/test")
    def endpoint():
        return {"slug": current_db_slug.get()}

    client = TestClient(app)
    malformed = "timetable\nFAKE LOG LINE INJECTED"
    assert not SLUG_PATTERN.match(malformed)  # confirme l'hypothèse du test avant de s'y fier
    body = client.get("/test", headers={"X-Klepsydrix-Database": malformed}).json()

    assert body == {"slug": "-"}


def test_non_http_scope_is_a_no_op():
    """Le middleware doit laisser passer un scope non-HTTP (ex: lifespan) sans tenter de lire des
    en-têtes qui n'existent pas dans ce type de scope."""
    calls = []

    async def inner_app(scope, receive, send):
        calls.append(scope["type"])

    middleware = DbSlugContextMiddleware(inner_app)

    import asyncio
    asyncio.run(middleware({"type": "lifespan"}, None, None))

    assert calls == ["lifespan"]
