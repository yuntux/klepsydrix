"""
Plafond de taille des corps de requête (voir instance.example.yaml, `server.max_upload_mb`).

**Le problème couvert.** L'application accepte des fichiers par deux chemins, et n'en bornait aucun :
- les champs binaires génériques (`type: "binary"` — photo d'enseignant, fichier STS-web…),
  transmis dans le corps JSON sous la forme `{filename, mime_type, data_base64}` (voir
  components/widgets/BinaryFileField.vue) ;
- la restauration d'une base (api/instance_endpoints.py), désormais du JSON base64 elle aussi.
Une « photo » de 500 Mo était donc stockée en base64 dans la base (≈ +33 %) puis rechargée en
mémoire à chaque lecture de la fiche. Aucune malveillance nécessaire : un fichier déposé par erreur
suffit.

**Un seul point de contrôle** (`ContentLengthLimitMiddleware`) plutôt qu'une vérification par
endpoint : il agit AVANT que le corps soit lu, couvre les deux chemins ci-dessus et tout endpoint
futur, et ne peut pas être oublié à l'écriture d'une nouvelle route. Le contrôle par champ, lui,
n'existe que pour produire un message compréhensible (voir `assert_within_limit`) — jamais comme
protection de dernier ressort.

La restauration a son propre plafond (`max_restore_upload_mb`) : une sauvegarde d'établissement
pèse légitimement des centaines de mégaoctets, une photo de trombinoscope non.
"""
from starlette.responses import JSONResponse

from backend.app.core.config import settings

_MB = 1024 * 1024
# La restauration est la seule opération dont le volume légitime se compte en centaines de Mo.
_RESTORE_PATH_SUFFIX = "/restore"


def limit_bytes_for(path: str) -> int:
    mb = settings.server.max_restore_upload_mb if path.endswith(_RESTORE_PATH_SUFFIX) else settings.server.max_upload_mb
    return mb * _MB


def assert_within_limit(data: bytes, label: str = "Ce fichier") -> bytes:
    """
    Contrôle de CONFORT sur une charge utile déjà décodée (voir docstring du module) : produit un
    message que l'utilisateur peut comprendre et corriger, là où le middleware ne peut renvoyer
    qu'un 413 générique. Lève `ValueError` (traduite en 400, voir core/error_handlers.py).
    """
    limit = settings.server.max_upload_mb * _MB
    if len(data) > limit:
        raise ValueError(
            f"{label} dépasse la taille maximale autorisée "
            f"({settings.server.max_upload_mb} Mo, voir server.max_upload_mb)."
        )
    return data


class ContentLengthLimitMiddleware:
    """Middleware ASGI « brut » — même choix que les autres middlewares du projet (voir
    core/log_context.py pour le raisonnement)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = None
        for name, value in scope.get("headers", ()):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = None
                break

        # `Content-Length` absent (corps en `chunked`) : rien à contrôler ici sans consommer le
        # flux. Limite connue et assumée — le client de l'application ne l'emploie jamais (fetch
        # avec un corps JSON pose toujours Content-Length), et un reverse proxy en production a
        # ses propres plafonds (`client_max_body_size` / `request_body_limit`, voir §20.C).
        if declared is not None and declared > limit_bytes_for(scope.get("path", "")):
            limit_mb = limit_bytes_for(scope.get("path", "")) // _MB
            response = JSONResponse(
                status_code=413,
                content={"detail": f"Requête trop volumineuse (maximum {limit_mb} Mo)."},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
