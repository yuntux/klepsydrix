"""
Endpoints de portée instance (pas de base résolue) — voir architecture.md §20, "Architecture de
routage HTTP". **Aucune route de ce module n'est publique** : `GET /my-databases` alimente le
sélecteur de base mais exige une session et ne renvoie que les bases où l'identité connectée a un
compte ; `/admin/*` est la console d'administration : super-admin (paire nommée ou mot de passe
maître) ou admin d'une base précise (membre du groupe "Admin" DANS cette base).

⚠️ `GET /databases`, qui servait la liste brute de TOUS les établissements hébergés à n'importe
quel anonyme, a été supprimée. Elle venait d'une contrainte réelle (§17.F : le mot de passe local
vit dans une base précise, il faut donc avoir choisi la base avant de pouvoir s'authentifier) mais
tirait une conclusion trop large : la contrainte ne portait que sur le FORMULAIRE de connexion, où
la base est un champ saisi — l'utilisateur connaît son établissement.
"""
import base64
import binascii
import logging
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.app.core import db_registry, db_admin_ops
from backend.app.core.config import settings
from backend.app.core.instance_session import InstanceSession, require_instance_session
from backend.app.core.instance_admin import (
    require_super_admin, require_admin_of, is_super_admin, administrable_databases,
    databases_for_identity,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/instance")


@router.get("/my-databases")
def list_my_databases(session: InstanceSession = Depends(require_instance_session)):
    """
    Bases où l'identité connectée a un compte — alimente le sélecteur (pages/SelectDatabase.vue).

    Remplace `GET /databases`, SUPPRIMÉE : elle servait la liste brute de tous les établissements
    hébergés à n'importe quel anonyme. Plus aucune ressource non authentifiée ne divulgue cette
    liste ; le formulaire de connexion locale n'en a jamais eu besoin, la base y est un champ saisi
    (voir core/instance_admin.py::databases_for_identity et architecture.md §16.D).
    """
    return {"databases": databases_for_identity(session)}


@router.get("/admin/databases")
def list_administrable_databases(session: InstanceSession = Depends(require_instance_session)):
    return {
        "databases": administrable_databases(session),
        "is_super_admin": is_super_admin(session),
    }


from pydantic import BaseModel


class CreateDatabasePayload(BaseModel):
    slug: str
    admin_email: str
    # Voir architecture.md §17.G — seulement significatif si le provider "local" est actif sur
    # l'instance (vérifié côté serveur ci-dessous, pas seulement côté IHM). Si vrai : au lieu du
    # pré-appariement habituel ("pending", promu à la première connexion RÉELLE quel qu'en soit le
    # fournisseur), crée directement un compte local (sans mot de passe) et envoie un lien de
    # réinitialisation à admin_email — seule façon pour l'admin désigné de se connecter si "local"
    # est le SEUL fournisseur de l'instance (aucune connexion self-service possible sinon, voir
    # UserIdentityProvider.verify_local_password : un compte local sans mot de passe ne peut jamais
    # authentifier personne).
    send_password_reset: bool = False


@router.post("/admin/databases")
async def create_database(payload: CreateDatabasePayload, session: InstanceSession = Depends(require_super_admin)):
    """
    Réservé aux super-admins (voir architecture.md §19) — pour éviter la multiplication incontrôlée
    du nombre de bases par des admins de base peu scrupuleux. Désigne l'admin de la nouvelle base
    par email — pré-appariement (voir database.py::current_db_user) par défaut, ou compte local +
    email de réinitialisation si `send_password_reset` (voir CreateDatabasePayload).
    """
    if not db_registry.SLUG_PATTERN.match(payload.slug):
        raise HTTPException(status_code=400, detail="Nom de base invalide (lettres, chiffres, tirets, underscores uniquement).")
    physical_slug = db_admin_ops.physical_slug_for_new_database(payload.slug)
    if db_registry.is_known_slug(physical_slug):
        raise HTTPException(status_code=409, detail="Cette base existe déjà.")
    if payload.send_password_reset and not any(p.protocol == "local_password" and p.active for p in settings.identity_providers):
        raise HTTPException(status_code=400, detail="Le fournisseur \"local\" n'est pas actif sur cette instance.")

    db_admin_ops.create_database(physical_slug)
    from backend.app.core.init_db import init_prod_data
    init_prod_data(slug=physical_slug)

    from backend.app.models.user import User, UserIdentityProvider
    from backend.app.models.access import ResGroup
    # MODE SYSTÈME assumé (aucun droit appliqué, voir models/base.py) : la base vient d'être créée,
    # elle n'a encore aucun utilisateur — personne ne peut donc y avoir de droits, et c'est
    # justement le premier compte que l'on écrit ici. Portée strictement limitée à ce bloc.
    db = db_registry.sessionmaker_for(physical_slug)()
    password_reset_email_sent = False
    try:
        user = User.create(db, {"first_name": "En attente", "last_name": "de première connexion", "email": payload.admin_email})
        if payload.send_password_reset:
            idp = UserIdentityProvider.create(db, {"user_id": user.id, "provider_key": "local", "external_subject": payload.admin_email})
        else:
            idp = UserIdentityProvider.create(db, {"user_id": user.id, "provider_key": "pending", "external_subject": payload.admin_email})
        admin_group = db.query(ResGroup).filter(ResGroup.name == "Admin").first()
        admin_group.update(db, {"user_ids": [user.id]})
        db.commit()

        if payload.send_password_reset:
            from backend.app.models.password_reset_token import PasswordResetToken
            from backend.app.core.mailer import send_password_reset_email
            _, raw_token = PasswordResetToken.issue(db, idp.id, settings.auth.password_reset_ttl_minutes)
            db.commit()
            reset_url = f"{settings.server.public_base_url}/password-reset/confirm?token={raw_token}&db={physical_slug}"
            try:
                await send_password_reset_email(payload.admin_email, reset_url)
                password_reset_email_sent = True
            except Exception:
                # La base ET le compte local sont déjà créés correctement à ce stade — un échec
                # d'ENVOI (SMTP mal configuré, indisponible...) ne doit jamais faire annuler la
                # création de la base elle-même, seulement être rapporté distinctement à l'appelant
                # (voir password_reset_email_sent ci-dessous) pour qu'un admin puisse relancer
                # l'envoi ou communiquer le lien autrement.
                logger.exception("Échec d'envoi de l'email de réinitialisation de mot de passe (base %s, %s)", physical_slug, payload.admin_email)
    finally:
        db.close()

    return {"status": "success", "slug": physical_slug, "password_reset_email_sent": password_reset_email_sent}


class DuplicateDatabasePayload(BaseModel):
    new_slug: str


@router.post("/admin/databases/{slug}/duplicate")
def duplicate_database(slug: str, payload: DuplicateDatabasePayload, session: InstanceSession = Depends(require_super_admin)):
    if not db_registry.is_known_slug(slug):
        raise HTTPException(status_code=404, detail="Base introuvable.")
    if not db_registry.SLUG_PATTERN.match(payload.new_slug):
        raise HTTPException(status_code=400, detail="Nom de base invalide (lettres, chiffres, tirets, underscores uniquement).")
    physical_new_slug = db_admin_ops.physical_slug_for_new_database(payload.new_slug)
    if db_registry.is_known_slug(physical_new_slug):
        raise HTTPException(status_code=409, detail="Cette base existe déjà.")
    db_admin_ops.duplicate_database(slug, physical_new_slug)
    return {"status": "success", "slug": physical_new_slug}


@router.get("/admin/databases/{slug}/backup")
def backup_database(slug: str, session: InstanceSession = Depends(require_admin_of)):
    if not db_registry.is_known_slug(slug):
        raise HTTPException(status_code=404, detail="Base introuvable.")
    path = db_admin_ops.backup_database(slug)
    extension = path.suffix
    return FileResponse(
        path=str(path),
        filename=f"{slug}{extension}",
        media_type="application/octet-stream",
        background=_cleanup_tmp_file(path),
    )


def _cleanup_tmp_file(path):
    from starlette.background import BackgroundTask
    return BackgroundTask(lambda: os.path.exists(path) and os.remove(path))


class BinaryPayload(BaseModel):
    """Champ binaire au format générique du produit — {filename, mime_type, data_base64}, voir
    models/teacher.py::photo et wizard_sts_import.py::sts_file, même objet côté frontend
    (components/widgets/BinaryFileField.vue)."""
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    data_base64: str


class RestoreDatabasePayload(BaseModel):
    confirm: str
    file: BinaryPayload


@router.post("/admin/databases/{slug}/restore")
def restore_database(slug: str, payload: RestoreDatabasePayload, session: InstanceSession = Depends(require_admin_of)):
    """
    "Annule et remplace" — aussi destructif qu'une suppression, donc même exigence de confirmation
    (voir architecture.md §20) : `confirm` doit correspondre EXACTEMENT au nom de la base, vérifié
    côté serveur (pas seulement une case à cocher côté client).

    ⚠️ Corps **JSON** (fichier en base64), pas un envoi multipart — décision de sécurité, pas une
    préférence de style. En multipart, cette route avait la forme exacte d'une cible CSRF : type de
    contenu "simple" (donc aucun préflight CORS déclenché), `confirm` en paramètre d'URL, aucun
    en-tête personnalisé requis — un simple `<form>` sur un site tiers suffisait à la déclencher
    avec le cookie de session de la victime, et son effet est le plus destructif de l'application.
    Le contrôle `confirm != slug` n'y changeait rien : il protège d'une erreur humaine, pas d'un
    attaquant, qui recopie simplement le slug. En JSON, le navigateur impose un préflight qu'une
    origine étrangère ne passe pas. Contrepartie assumée : ~33 % de volume en plus et le corps
    entier en mémoire — d'où le plafond dédié `server.max_restore_upload_mb`
    (core/upload_limits.py), qui n'est donc pas optionnel.
    """
    if not db_registry.is_known_slug(slug):
        raise HTTPException(status_code=404, detail="Base introuvable.")
    if payload.confirm != slug:
        raise HTTPException(status_code=400, detail="La confirmation ne correspond pas au nom de la base.")
    try:
        content = base64.b64decode(payload.file.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Fichier illisible (encodage base64 invalide).")
    db_admin_ops.restore_database(slug, content)
    return {"status": "success"}


@router.delete("/admin/databases/{slug}")
def delete_database(slug: str, confirm: str, session: InstanceSession = Depends(require_admin_of)):
    if not db_registry.is_known_slug(slug):
        raise HTTPException(status_code=404, detail="Base introuvable.")
    if confirm != slug:
        raise HTTPException(status_code=400, detail="La confirmation ne correspond pas au nom de la base.")
    db_admin_ops.delete_database(slug)
    return {"status": "success"}
