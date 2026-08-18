"""
Traduction en réponses HTTP des exceptions métier de la couche modèle (voir architecture.md §18.J).
La couche modèle ne connaît pas FastAPI : `base.py` lève `ValueError`, `AccessDeniedError`,
`UnsupportedOperationError`… jamais `HTTPException` — c'est ici que le statut est décidé, une fois
pour toutes les routes.

**Pourquoi centraliser plutôt qu'un try/except par endpoint** : chaque endpoint générique répétait
la même cascade de branches, terminée par un `except Exception` fourre-tout qui transformait
N'IMPORTE QUELLE exception en 400. Un `AttributeError`, un `KeyError`, une erreur SQLAlchemy —
c'est-à-dire un BUG SERVEUR — était annoncé au client comme « votre requête est invalide », sans
trace dans les logs, sans 500 pour la supervision, avec le texte de l'exception interne renvoyé tel
quel. Les vrais défauts se déguisaient en erreurs de saisie.

Ici, seules les exceptions qui SIGNIFIENT quelque chose côté client sont traduites. Tout le reste
remonte en 500 avec sa traceback, ce qui est le comportement correct pour un bug.

`ValueError` = erreur de validation métier : convention explicite du projet (une centaine
d'occurrences dans `backend/app/models/`, voir aussi la docstring d'`AccessDeniedError`), pas une
interception opportuniste.
"""
import logging

from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from backend.app.models.base import AccessDeniedError, UnsupportedOperationError
from backend.app.models.composition_mode import CompositionError
from backend.app.core.exclusive_mode import ExclusiveModeActiveError

logger = logging.getLogger(__name__)

# (exception, statut) — l'ordre ne compte pas, Starlette résout par la classe la plus spécifique.
BUSINESS_EXCEPTIONS = [
    (AccessDeniedError, 403),          # moteur de droits (base.py, browse(), @requires_access)
    (UnsupportedOperationError, 405),  # opération interdite sur ce modèle (ex: création d'un TransientModel)
    (ExclusiveModeActiveError, 423),   # écriture pendant une résolution du solveur
    (CompositionError, 400),           # composition de cours invalide (models/composition_mode.py)
    (ValueError, 400),                 # validation métier — convention du projet
]


def _make_handler(status_code: int):
    async def handler(request, exc):
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})
    return handler


async def integrity_error_handler(request, exc: IntegrityError):
    """
    Violation de contrainte SQL (unicité, clé étrangère). `str(exc)` contient la requête et ses
    paramètres : journalisé, jamais renvoyé au client — un message d'erreur ne doit pas exposer le
    schéma. 400 plutôt que 409, pour ne pas changer le contrat déjà connu du frontend.
    """
    logger.warning("Violation de contrainte d'intégrité sur %s : %s", request.url.path, exc)
    return JSONResponse(
        status_code=400,
        content={"detail": "Cette opération viole une contrainte d'unicité ou de référence en base."},
    )


def register_exception_handlers(app) -> None:
    """Appelé une fois depuis main.py. Fonction séparée pour être testable sur une app jetable."""
    for exception_class, status_code in BUSINESS_EXCEPTIONS:
        app.add_exception_handler(exception_class, _make_handler(status_code))
    app.add_exception_handler(IntegrityError, integrity_error_handler)
