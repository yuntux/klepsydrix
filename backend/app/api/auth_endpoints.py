"""
Routes d'authentification au niveau instance — voir architecture.md, "Architecture de routage
HTTP". Toutes publiques (aucune session requise) sauf /logout, qui accepte l'absence de session
sans erreur (déconnecter un utilisateur déjà déconnecté doit rester un no-op réussi, pas une 401).
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core import db_registry
from backend.app.core.client_ip import client_ip
from backend.app.core.instance_session import set_session_cookie, clear_session_cookie
from backend.app.core.oidc import oauth, claim_mapping_for
from backend.app.core.mailer import send_password_reset_email
from backend.app.models.user import UserIdentityProvider
from backend.app.models.password_reset_token import PasswordResetToken

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth")


@router.get("/providers")
def list_providers():
    """Fournisseurs actifs de l'instance — jamais `params` (secrets client OIDC)."""
    return [
        {"key": p.key, "label": p.label, "logo": p.logo, "protocol": p.protocol}
        for p in settings.identity_providers if p.active
    ]


class LocalLoginPayload(BaseModel):
    identifier: str
    password: str


@router.post("/login/local")
def login_local(payload: LocalLoginPayload, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Connexion au provider "local", propre à UNE base (voir architecture.md : contrairement à un
    provider OIDC fédéré, le mot de passe local vit dans `user_identity_providers` de la base
    ciblée — le frontend envoie donc explicitement l'en-tête X-Klepsydrix-Database, ici depuis le
    champ "base" du formulaire, pas depuis le cookie klepsydrix_db habituel). Succès : pose la
    session instance ET le cookie de base en une seule réponse (l'utilisateur a déjà choisi les
    deux dans le même formulaire, inutile de le refaire passer par /select-database).

    Journalise chaque ÉCHEC en WARNING (voir architecture.md §17.H, deploy/fail2ban/klepsydrix-
    local-login.conf) — la protection anti-brute-force est ENTIÈREMENT déléguée à fail2ban, qui lit
    ce journal (aucun verrouillage applicatif ici, décision explicite — voir §17.H pour le
    raisonnement). Pas de log pour un SUCCÈS (contrairement au mot de passe maître) : une connexion
    locale réussie est le flux normal et quotidien de l'application, pas un évènement rare à haut
    privilège — la journaliser en WARNING noierait le signal utile.
    """
    ip = client_ip(request)
    slug = db_registry.slug_for_session(db)

    idp = UserIdentityProvider.verify_local_password(db, payload.identifier, payload.password)
    if idp is None:
        logger.warning("Échec de connexion locale depuis %s (base : %s, identifiant : %s)", ip, slug, payload.identifier)
        raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect.")

    # identifier sert aussi d'email pour le pré-appariement par email (voir database.py::
    # current_db_user) : convention du provider local, ses identifiants sont par nature des emails.
    set_session_cookie(response, provider_key="local", subject=payload.identifier, email=payload.identifier)
    response.set_cookie("klepsydrix_db", slug, httponly=False, samesite="lax", path="/")
    return {"status": "success"}


class PasswordResetRequestPayload(BaseModel):
    identifier: str


@router.post("/password-reset/request")
async def password_reset_request(payload: PasswordResetRequestPayload, db: Session = Depends(get_db)):
    """
    Provider "local" uniquement (voir architecture.md §17.G) — toujours la même réponse générique,
    que l'identifiant corresponde à un compte réel ou non (énumération) : un email n'est envoyé QUE
    si un compte local correspondant existe vraiment, mais l'appelant ne peut jamais le déduire de
    la réponse HTTP elle-même.
    """
    idp = db.query(UserIdentityProvider).filter(
        UserIdentityProvider.provider_key == "local",
        UserIdentityProvider.external_subject == payload.identifier,
    ).first()
    if idp:
        _, raw_token = PasswordResetToken.issue(db, idp.id, settings.auth.password_reset_ttl_minutes)
        db.commit()
        slug = db_registry.slug_for_session(db)
        reset_url = f"{settings.server.public_base_url}/password-reset/confirm?token={raw_token}&db={slug}"
        try:
            await send_password_reset_email(idp.external_subject, reset_url)
        except Exception:
            logger.exception("Échec d'envoi de l'email de réinitialisation de mot de passe (identifiant : %s)", payload.identifier)
    return {"status": "success"}


class PasswordResetConfirmPayload(BaseModel):
    token: str
    new_password: str


@router.post("/password-reset/confirm")
def password_reset_confirm(payload: PasswordResetConfirmPayload, db: Session = Depends(get_db)):
    """Jeton invalide/expiré/déjà utilisé : un seul message générique (voir PasswordResetToken.consume,
    ne distingue jamais la raison précise — même principe d'énumération que /password-reset/request)."""
    idp = PasswordResetToken.consume(db, payload.token)
    if idp is None:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré.")
    idp.set_local_password(db, payload.new_password)
    db.commit()
    return {"status": "success"}


@router.get("/oidc/login/{provider_key}")
async def oidc_login(provider_key: str, request: Request, next: str = "/"):
    client = oauth.create_client(provider_key)
    if client is None:
        raise HTTPException(status_code=404, detail="Fournisseur d'identité inconnu.")
    redirect_uri = str(request.url_for("oidc_callback", provider_key=provider_key)) + f"?next={next}"
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/oidc/callback/{provider_key}", name="oidc_callback")
async def oidc_callback(provider_key: str, request: Request, response: Response, next: str = "/", db: Session = Depends(get_db)):
    """
    ⚠️ Non vérifié contre un vrai fournisseur OIDC (EduConnect n'est configuré qu'avec des
    paramètres fictifs dans instance.example.yaml, voir architecture.md) — implémentation Authlib
    standard (échange de code, validation id_token), à valider dès qu'un vrai fournisseur est
    disponible.
    """
    client = oauth.create_client(provider_key)
    if client is None:
        raise HTTPException(status_code=404, detail="Fournisseur d'identité inconnu.")
    token = await client.authorize_access_token(request)
    claims = token.get("userinfo") or {}

    # claim_mapping (instance.yaml) : {nom_du_claim_fournisseur: notre_champ}, ex.
    # {"sub": "external_subject", "given_name": "first_name", ...} — voir claim_mapping_for.
    mapped = {our_field: claims.get(claim_key) for claim_key, our_field in claim_mapping_for(provider_key).items()}
    external_subject = mapped.get("external_subject")
    first_name = mapped.get("first_name")
    last_name = mapped.get("last_name")
    email = mapped.get("email")

    if not external_subject:
        raise HTTPException(status_code=400, detail="Le fournisseur d'identité n'a pas renvoyé d'identifiant exploitable.")

    set_session_cookie(response, provider_key=provider_key, subject=external_subject, first_name=first_name, last_name=last_name, email=email)
    from starlette.responses import RedirectResponse
    redirect = RedirectResponse(url=next)
    redirect.headers.update(response.headers)
    return redirect


class MasterLoginPayload(BaseModel):
    password: str


@router.post("/login/master")
def login_master(payload: MasterLoginPayload, request: Request, response: Response):
    """
    Authentification par mot de passe maître pour la console d'administration (voir
    core/master_auth.py, architecture.md §19.A) — désactivée par défaut, jamais liée à une base. Ne
    donne accès qu'à `instance_router` (console) : `database.py::current_db_user` rejette
    explicitement cette identité fantôme pour toute route applicative.
    """
    from backend.app.core.master_auth import verify_master_password, MASTER_PROVIDER_KEY, MASTER_SUBJECT

    verify_master_password(request, payload.password)
    set_session_cookie(response, provider_key=MASTER_PROVIDER_KEY, subject=MASTER_SUBJECT)
    return {"status": "success"}


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"status": "success"}
