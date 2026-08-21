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

    # MODE SYSTÈME assumé : autorisation de PORTÉE INSTANCE, évaluée sur une base qui n'est pas
    # celle de la requête en cours (la console d'administration n'en a aucune). L'utilisateur n'y
    # est par définition pas encore résolu — c'est ce que cette fonction cherche à établir. Lecture
    # seule, limitée aux identités et aux groupes.
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


def identity_exists_in(session: InstanceSession, slug: str) -> bool:
    """
    Cette identité a-t-elle un compte dans la base `slug` ? Pendant de `is_db_admin` sans la
    condition d'appartenance au groupe "Admin" — sert au sélecteur de base (voir
    `databases_for_identity`), qui répond à « où puis-je travailler ? », pas « où suis-je admin ? ».
    """
    if session.provider_key == MASTER_PROVIDER_KEY:
        return False
    from backend.app.core import db_registry
    from backend.app.models.user import UserIdentityProvider

    # MODE SYSTÈME assumé, même raison que is_db_admin ci-dessus : question de portée instance
    # posée à une base qui n'est pas celle de la requête. Lecture seule d'une seule ligne, dont on
    # ne renvoie qu'un booléen — jamais de donnée applicative.
    db = db_registry.sessionmaker_for(slug)()
    try:
        return db.query(UserIdentityProvider).filter(
            UserIdentityProvider.provider_key == session.provider_key,
            UserIdentityProvider.external_subject == session.subject,
        ).first() is not None
    finally:
        db.close()


def databases_for_identity(session: InstanceSession) -> list[str]:
    """
    Bases proposées au sélecteur (`GET /api/instance/my-databases`).

    ⚠️ Remplace l'ancienne route PUBLIQUE `GET /api/instance/databases`, qui renvoyait la liste
    brute de tous les établissements hébergés à n'importe quel anonyme. Cette route était née d'une
    contrainte réelle (voir architecture.md §17.F : le mot de passe du provider local vit dans UNE
    base, il faut donc l'avoir choisie avant de pouvoir s'authentifier) — mais la contrainte ne
    portait que sur le FORMULAIRE de connexion, où la base est un champ SAISI, connu de
    l'utilisateur par ailleurs. Rien n'obligeait à publier la liste.

    Trois cas, tous fermés par construction :
    - identité locale : elle ne vaut que dans la base où son mot de passe a été vérifié
      (`db_slug`, voir instance_session.py) — la liste ne peut donc contenir qu'elle ;
    - identité fédérée : les bases où un compte existe réellement, une session ouverte par base
      (même coût O(n) qu'`administrable_databases`, même limite assumée) ;
    - mot de passe maître : rien. Cette identité fantôme est refusée sur toute donnée applicative
      (voir database.py::current_db_user) ; lui proposer une base serait une impasse.
    """
    from backend.app.core import db_registry

    if session.provider_key == MASTER_PROVIDER_KEY:
        return []
    if session.provider_key == "local":
        return [session.db_slug] if session.db_slug and db_registry.is_known_slug(session.db_slug) else []
    return [slug for slug in sorted(db_registry.known_slugs()) if identity_exists_in(session, slug)]


def require_admin_of(slug: str, session: InstanceSession = Depends(require_instance_session)) -> InstanceSession:
    if not is_super_admin(session) and not is_db_admin(session, slug):
        raise HTTPException(status_code=403, detail=f"Vous n'êtes pas administrateur de la base « {slug} ».")
    return session
