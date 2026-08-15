"""
Autorisation de la console d'administration d'instance (voir architecture.md §19) : super-admin
(paire nommée `super_admins` OU mot de passe maître, voir master_auth.py) vs. admin d'une base
précise (membre du groupe "Admin" DANS cette base — voir access_control.py).
"""
from fastapi import Depends, HTTPException

from backend.app.core.config import settings
from backend.app.core.instance_session import InstanceSession, require_instance_session
from backend.app.core.master_auth import MASTER_PROVIDER_KEY


def is_super_admin(session: InstanceSession) -> bool:
    if session.provider_key == MASTER_PROVIDER_KEY:
        return True
    return any(
        pair.provider_key == session.provider_key and pair.subject == session.subject
        for pair in settings.super_admins
    )


def require_super_admin(session: InstanceSession = Depends(require_instance_session)) -> InstanceSession:
    if not is_super_admin(session):
        raise HTTPException(status_code=403, detail="Réservé aux super-administrateurs.")
    return session


def is_db_admin(session: InstanceSession, slug: str) -> bool:
    """
    Appartenance au groupe "Admin" DANS la base `slug` pour cette identité — ouvre une session
    dédiée sur cette base (indépendante de la base éventuellement déjà résolue pour la requête en
    cours, puisque la console d'administration n'a par nature aucune base "courante").
    """
    if session.provider_key == MASTER_PROVIDER_KEY:
        return False  # le mot de passe maître donne un accès super-admin, jamais une appartenance de groupe locale
    from backend.app.core import db_registry
    from backend.app.models.user import UserIdentityProvider
    from backend.app.core.access_control import resolve_effective_group_objects

    db = db_registry.sessionmaker_for(slug)()
    try:
        idp = db.query(UserIdentityProvider).filter(
            UserIdentityProvider.provider_key == session.provider_key,
            UserIdentityProvider.external_subject == session.subject,
        ).first()
        if not idp:
            return False
        return any(g.name == "Admin" for g in resolve_effective_group_objects(idp.user))
    finally:
        db.close()


def administrable_databases(session: InstanceSession) -> list[str]:
    """Bases que cette identité peut administrer : toutes si super-admin, sinon celles où elle est
    membre du groupe "Admin". ⚠️ O(n) sessions ouvertes (une par base découverte) pour un admin
    non-super — acceptable pour des dizaines de bases, à surveiller au-delà (voir architecture.md)."""
    from backend.app.core import db_registry

    all_slugs = sorted(db_registry.known_slugs())
    if is_super_admin(session):
        return all_slugs
    return [slug for slug in all_slugs if is_db_admin(session, slug)]


def require_admin_of(slug: str, session: InstanceSession = Depends(require_instance_session)) -> InstanceSession:
    if not is_super_admin(session) and not is_db_admin(session, slug):
        raise HTTPException(status_code=403, detail=f"Vous n'êtes pas administrateur de la base « {slug} ».")
    return session
