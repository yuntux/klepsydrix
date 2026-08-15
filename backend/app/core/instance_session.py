"""
Session au niveau instance (voir architecture.md, "Architecture de routage HTTP" / specs/) : prouve
QUI l'utilisateur prétend être (identité vérifiée par un fournisseur — OIDC ou provider local),
indépendamment de toute base. Un cookie signé (itsdangerous), pas une table — la session instance
n'a aucune raison de survivre à un redémarrage du process différemment d'un cookie expiré, et vit
au niveau instance alors que toutes les tables applicatives vivent par base.

Expiration par INACTIVITÉ (`auth.session_idle_timeout_minutes`, voir instance.example.yaml), pas
une durée fixe depuis la connexion : `require_instance_session` réémet le cookie (nouvel horodatage
signé) une fois que le jeton courant a plus de `_REFRESH_THRESHOLD_SECONDS` d'ancienneté — la
fenêtre glisse donc au fil de l'activité, et seule une période d'inactivité ininterrompue supérieure
au délai configuré force une reconnexion.

⚠️ Ne PAS réémettre à CHAQUE requête (une première version le faisait) : plusieurs requêtes
authentifiées peuvent être en vol au moment même où l'utilisateur clique sur "Se déconnecter"
(ex: chargement initial de la page encore en cours) — si l'une d'elles répond APRÈS que `/logout`
a supprimé le cookie, son propre `Set-Cookie` (un jeton encore valide) écraserait la suppression et
ressusciterait silencieusement la session. Trouvé par `frontend/e2e/auth.spec.ts` ("se déconnecter
efface la session..."), pas par un raisonnement a priori. En ne réémettant qu'après un seuil
(quelques minutes), un jeton tout juste émis à la connexion ne déclenche plus aucun `Set-Cookie`
lors des requêtes qui suivent immédiatement — la course ne peut plus se produire dans ce laps de
temps très court, tout en conservant un vrai comportement de fenêtre glissante sur la durée réelle
d'une session (le seuil est très petit devant `session_idle_timeout_minutes`, largement dominé).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import HTTPException, Request, Response

from backend.app.core.config import settings

COOKIE_NAME = "klepsydrix_session"
_REFRESH_THRESHOLD_SECONDS = 5 * 60

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="klepsydrix-instance-session")


def _max_age_seconds() -> int:
    # Lu à chaque appel (pas figé au chargement du module) — cohérent avec le reste de la config
    # (ex: master_auth.py lit settings.master_db_local_auth à chaque appel), pour qu'un changement
    # d'instance.yaml prenne effet dès le prochain redémarrage sans dépendre de l'ordre d'import.
    return settings.auth.session_idle_timeout_minutes * 60


@dataclass
class InstanceSession:
    provider_key: str
    subject: str
    # Connus au moment de la connexion (claims OIDC, ou None pour le provider local) — utilisés
    # UNIQUEMENT pour peupler un User nouvellement auto-créé sur une base qui ne le connaît pas
    # encore (voir database.py::current_db_user) ; jamais resynchronisés sur les requêtes suivantes.
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None


def set_session_cookie(
    response: Response, provider_key: str, subject: str,
    first_name: str | None = None, last_name: str | None = None, email: str | None = None,
) -> None:
    token = _serializer.dumps({
        "provider_key": provider_key, "subject": subject,
        "first_name": first_name, "last_name": last_name, "email": email,
    })
    response.set_cookie(
        COOKIE_NAME, token, max_age=_max_age_seconds(), httponly=True, samesite="lax", path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def require_instance_session(request: Request, response: Response) -> InstanceSession:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail={"code": "NOT_AUTHENTICATED"})
    try:
        data, issued_at = _serializer.loads(token, max_age=_max_age_seconds(), return_timestamp=True)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=401, detail={"code": "NOT_AUTHENTICATED"})
    session = InstanceSession(
        provider_key=data["provider_key"], subject=data["subject"],
        first_name=data.get("first_name"), last_name=data.get("last_name"), email=data.get("email"),
    )
    # Fenêtre glissante, mais throttlée (voir docstring du module) : ne réémet le cookie que si le
    # jeton courant a plus de _REFRESH_THRESHOLD_SECONDS d'ancienneté.
    age = datetime.now(timezone.utc) - issued_at
    if age > timedelta(seconds=_REFRESH_THRESHOLD_SECONDS):
        set_session_cookie(
            response, provider_key=session.provider_key, subject=session.subject,
            first_name=session.first_name, last_name=session.last_name, email=session.email,
        )
    return session
