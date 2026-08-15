"""
Contexte de base courante pour les logs (voir architecture.md §16.F, multi-base) : posé par
`DbSlugContextMiddleware` (ci-dessous) au niveau ASGI, lu par `DbContextFilter` pour préfixer
chaque ligne de log par `[db=<slug>]` — y compris les logs d'accès uvicorn (voir `main.py`,
configuration du logger `uvicorn.access`). Un `ContextVar` (pas une variable globale) pour rester
correctement isolé par requête même sous asyncio (une coroutine par requête, chacune avec son
propre contexte).

⚠️ Posé au niveau MIDDLEWARE, pas dans une dépendance FastAPI (`resolve_database`, l'endroit
initialement choisi) — corrigé après avoir trouvé, en vérifiant en conditions réelles, que le
`ContextVar` ne se propageait PAS : FastAPI exécute chaque dépendance SYNCHRONE (`def`, pas `async
def`) via `anyio.to_thread.run_sync`, qui copie le `contextvars.Context` ambiant dans un THREAD
SÉPARÉ à CHAQUE dépendance — une mutation faite via `ContextVar.set(...)` dans la copie utilisée par
une dépendance ne se propage donc JAMAIS à la copie (différente) utilisée par la dépendance/
l'endpoint suivant, même au sein d'une seule et même requête (vérifié empiriquement avec un cas
minimal avant d'écrire ce correctif : `Depends(dep_a)` qui appelle `.set(...)`, `dep_b` qui en
dépend et lit `.get()` juste après — retourne bien la valeur par défaut, pas celle posée par
`dep_a`). Un middleware ASGI, lui, reste dans un SEUL contexte asyncio cohérent pour toute la durée
d'une requête (vérifié de la même façon : `.set(...)` au niveau middleware, lu correctement par la
suite, sync ou async) — c'est le seul endroit qui garantisse la propagation.
"""
from contextvars import ContextVar
import logging

current_db_slug: ContextVar[str] = ContextVar("current_db_slug", default="-")


class DbContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.db_slug = current_db_slug.get()
        return True


class DbSlugContextMiddleware:
    """
    Middleware ASGI (pas `starlette.middleware.base.BaseHTTPMiddleware`, délibérément — un
    middleware ASGI "brut" comme `SessionMiddleware` déjà utilisé dans `main.py`, pour rester
    cohérent et éviter tout risque d'interaction avec les réponses en flux/tâches d'arrière-plan
    d'une `BaseHTTPMiddleware`, ex: `FileResponse` + `BackgroundTask` sur la sauvegarde de base,
    voir api/instance_endpoints.py::backup_database) : lit l'en-tête `X-Klepsydrix-Database` avant
    même la résolution des dépendances FastAPI et pose `current_db_slug` pour toute la durée de la
    requête.

    Ne fait AUCUNE validation d'EXISTENCE de la base (pas son rôle — `database.py::resolve_database`,
    une dépendance FastAPI, continue seule de porter cette responsabilité et de répondre 428/404) :
    seulement une validation de FORME (`db_registry.SLUG_PATTERN`) avant d'injecter la valeur dans
    les logs — sans ça, une valeur arbitraire dans cet en-tête (entièrement contrôlé par l'appelant)
    s'injecterait telle quelle dans chaque ligne de log.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", ()):
            if name == b"x-klepsydrix-database":
                from backend.app.core import db_registry
                slug = value.decode("latin-1")
                if db_registry.SLUG_PATTERN.match(slug):
                    current_db_slug.set(slug)
                break
        await self.app(scope, receive, send)


def attach_to_handlers(logger: logging.Logger) -> None:
    """
    Pose un `DbContextFilter` sur chaque HANDLER de `logger` — jamais sur `logger` lui-même. Un
    filtre posé via `logger.addFilter(...)` ne s'applique qu'aux enregistrements qui ORIGINENT de
    CE logger précis (`Logger.handle()` ne consulte `self.filters` que pour le logger appelé
    directement) — jamais à ceux propagés depuis un logger enfant qui atteignent ce logger via la
    hiérarchie (`Logger.callHandlers()` ne re-vérifie que les filtres des HANDLERS traversés, pas
    ceux des loggers ancêtres). Posé au mauvais endroit (`logger.addFilter`), ÇA NE LÈVE AUCUNE
    EXCEPTION VISIBLE (Python avale les erreurs de formatage de log, voir `Handler.handleError`) —
    mais chaque appel à `logging.getLogger(__name__).info/warning/exception(...)` PARTOUT AILLEURS
    dans le code (la quasi-totalité des appels réels) échoue silencieusement à se formater
    (`KeyError`/`ValueError` sur le champ manquant), remplaçant le message réellement utile par une
    trace de formatage — bug réel trouvé en vérifiant en conditions réelles, pas par pytest seul.
    """
    filter_instance = DbContextFilter()
    for handler in logger.handlers:
        handler.addFilter(filter_instance)
