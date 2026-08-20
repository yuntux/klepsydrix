from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from backend.app.core import db_registry
from backend.app.core.db_registry import DEFAULT_DB_NAME
from backend.app.core.instance_session import require_instance_session, InstanceSession

engine = db_registry.engine_for(DEFAULT_DB_NAME)
SessionLocal = db_registry.sessionmaker_for(DEFAULT_DB_NAME)


def resolve_database(request: Request, response: Response) -> str:
    """
    Dépendance FastAPI résolvant la base courante depuis l'en-tête `X-Klepsydrix-Database` — voir
    architecture.md. `get_db` en dépend explicitement (`Depends(resolve_database)`), donc aucun
    ordre implicite à retenir à part la contextualisation des LOGS par base, posée plus tôt, au
    niveau middleware ASGI (voir core/log_context.py::DbSlugContextMiddleware, architecture.md
    §16.F) — une dépendance FastAPI synchrone comme celle-ci ne s'y prête pas (le `ContextVar` posé
    ici ne se propagerait pas aux dépendances/l'endpoint suivants).
    """
    slug = request.headers.get("x-klepsydrix-database")
    if not slug:
        raise HTTPException(status_code=428, detail={"code": "DATABASE_REQUIRED"})
    if not db_registry.is_known_slug(slug):
        raise HTTPException(status_code=404, detail={"code": "DATABASE_UNKNOWN"})
    response.headers["X-Klepsydrix-Database"] = slug
    request.state.db_slug = slug
    return slug


def get_db(slug: str = Depends(resolve_database)):
    db = db_registry.sessionmaker_for(slug)()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_write_token(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    """
    Remplace l'ancien `WriteTokenMiddleware` (voir architecture.md, "Architecture de routage
    HTTP") : même comportement (rejet 409 si un jeton d'écriture périmé est envoyé sur une
    méthode d'écriture, écho du jeton courant sur toute réponse), mais comme dépendance FastAPI
    plutôt que comme middleware — testable/surchargeable via `app.dependency_overrides`, et opère
    sur la session déjà résolue pour la bonne base (`Depends(get_db)`) plutôt que d'en ouvrir une
    à part.
    """
    from backend.app.core.exclusive_mode import get_write_token

    current_token = get_write_token(db)
    incoming_token = request.headers.get("x-write-token")

    write_methods = {"POST", "PUT", "PATCH", "DELETE"}
    if (
        request.method in write_methods
        and incoming_token
        and current_token
        and incoming_token != current_token
    ):
        raise HTTPException(
            status_code=409,
            detail="Les données ont été modifiées depuis votre dernier chargement "
                   "(ex: une résolution automatique vient de se terminer). Rechargez la page avant de réessayer.",
            headers={"X-Write-Token": current_token},
        )

    if current_token:
        response.headers["X-Write-Token"] = current_token


# Routes exemptées du blocage `PASSWORD_CHANGE_REQUIRED` ci-dessous (must_change_password) : la
# route qui permet à l'utilisateur de sortir de cet état, et `whoami`, seule route lue par le
# frontend pour DÉTECTER l'état et déclencher la redirection (NotebooksTree.vue) — sans cette
# exemption, whoami elle-même serait bloquée et le frontend n'aurait aucun moyen de savoir pourquoi.
_PASSWORD_CHANGE_GATE_EXEMPT_PATHS = {"/api/ui/whoami", "/api/auth/password/change"}


def current_db_user(
    request: Request,
    session: InstanceSession = Depends(require_instance_session),
    db: Session = Depends(get_db),
):
    """
    Résout (ou crée) le `User` de la base courante pour l'identité déjà vérifiée au niveau
    instance (`require_instance_session`) — un `User` vit par base, une session instance non. Pose
    le drapeau ambiant `db.klepsydrix_user_id` (même idiome que `db.filter_discipline_id`,
    architecture.md §15.V) : lu par le moteur de droits (lot suivant), absent = mode système. Un
    utilisateur inconnu de cette base est créé à la volée SANS aucun droit (voir
    UserIdentityProvider) — visible nulle part tant qu'aucun `ResGroup` ne lui est assigné.

    L'identité fantôme du mot de passe maître (voir core/master_auth.py) est explicitement
    REJETÉE ici : elle ne doit jamais atteindre les données applicatives d'une base (seulement la
    console d'administration, `instance_router`) — sans ce garde-fou, un utilisateur inconnu
    portant ce provider_key serait silencieusement auto-créé comme n'importe quelle autre identité.
    `code: "MASTER_IDENTITY_FORBIDDEN"` structuré (comme `NOT_AUTHENTICATED`/`DATABASE_REQUIRED`,
    voir `resolve_database`) — reconnu par `apiFetch()` (frontend) pour renvoyer vers `/login` : le
    mot de passe maître ne correspondra jamais à un vrai compte dans aucune base (ce n'est pas un
    compte, juste un mot de passe partagé), rester sur l'appli dans cet état serait une impasse.

    Deux autres rejets structurés, résolus une fois `idp`/`idp.user` connus (voir fin de fonction) :
    `USER_INACTIVE` (`User.active == False`, local OU OIDC — ce point est le SEUL traversé par les
    deux, voir `models/user.py`) et `PASSWORD_CHANGE_REQUIRED` (`UserIdentityProvider.
    must_change_password`, local uniquement, sauf sur les routes exemptées ci-dessus).
    """
    from backend.app.core.master_auth import MASTER_PROVIDER_KEY
    if session.provider_key == MASTER_PROVIDER_KEY:
        raise HTTPException(status_code=403, detail={"code": "MASTER_IDENTITY_FORBIDDEN"})

    from backend.app.models.user import User, UserIdentityProvider
    from datetime import datetime, timezone

    idp = db.query(UserIdentityProvider).filter(
        UserIdentityProvider.provider_key == session.provider_key,
        UserIdentityProvider.external_subject == session.subject,
    ).first()

    if idp is None:
        # Pré-appariement par email (voir architecture.md §20, console d'administration —
        # "créer une base") : à la création d'une base, l'admin désigné n'a pas encore de `sub`
        # OIDC connu (identifiant opaque, jamais deviné à l'avance) — un User + UserIdentityProvider
        # "en attente" (provider_key="pending", external_subject=email) est créé à sa place. Ici,
        # première VRAIE connexion dont l'email correspond : la ligne "en attente" est promue avec
        # le provider/sub réels, plutôt que de créer un second User en double.
        pending = None
        if session.email:
            pending = db.query(UserIdentityProvider).filter(
                UserIdentityProvider.provider_key == "pending",
                UserIdentityProvider.external_subject == session.email,
            ).first()

        if pending:
            idp = pending.update(db, {
                "provider_key": session.provider_key, "external_subject": session.subject,
                "first_login_at": session.logged_in_at, "last_login_at": session.logged_in_at,
            })
        else:
            user = User.create(db, {
                "first_name": session.first_name or "?",
                "last_name": session.last_name or "?",
                "email": session.email,
            })
            idp = UserIdentityProvider.create(db, {
                "user_id": user.id, "provider_key": session.provider_key, "external_subject": session.subject,
                "first_login_at": session.logged_in_at, "last_login_at": session.logged_in_at,
            })
    else:
        # Identité déjà connue de cette base : `last_login_at` doit avancer une fois PAR VRAI LOGIN
        # (session.logged_in_at, fixé une seule fois à la connexion — voir instance_session.py),
        # jamais à chaque requête (voir architecture.md §9.I — le bug d'origine, et pourquoi
        # `login_local` ne le fait plus elle-même : ce mécanisme générique suffit désormais pour
        # local ET OIDC, qui n'ont donc plus besoin d'un traitement séparé chacun de leur côté).
        # DateTime "naïve" en base (voir password_reset_token.py::_as_utc, même piège) : toujours
        # écrite en UTC ici, donc toujours sûr de réattacher tzinfo=utc avant de comparer.
        current = idp.last_login_at
        if current is not None and current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        if current is None or current < session.logged_in_at:
            idp.update(db, {"last_login_at": session.logged_in_at})

    if not idp.user.active:
        raise HTTPException(status_code=403, detail={"code": "USER_INACTIVE"})

    if (
        idp.provider_key == "local"
        and idp.must_change_password
        and request.url.path not in _PASSWORD_CHANGE_GATE_EXEMPT_PATHS
    ):
        raise HTTPException(status_code=403, detail={"code": "PASSWORD_CHANGE_REQUIRED"})

    db.klepsydrix_user_id = idp.user_id
    return idp.user
