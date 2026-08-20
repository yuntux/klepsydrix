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
from backend.app.core.database import get_db, current_db_user
from backend.app.core import db_registry
from backend.app.core.client_ip import client_ip
from backend.app.core.instance_session import set_session_cookie, clear_session_cookie
from backend.app.core.oidc import oauth, claim_mapping_for
from backend.app.core.route_guard import system_scoped
from backend.app.core.mailer import send_password_reset_email
from backend.app.models.user import UserIdentityProvider
from backend.app.models.password_reset_token import PasswordResetToken

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth")


@router.get("/providers")
@system_scoped("Affiché sur l'écran de connexion, avant toute session. Ne renvoie que les fournisseurs actifs, jamais leurs secrets.")
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
@system_scoped("Authentification : on ne peut pas exiger un utilisateur déjà résolu pour se connecter.")
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

    # Rejet immédiat, avant même de poser la session — meilleure UX qu'attendre le premier appel
    # applicatif (bloqué de toute façon par database.py::current_db_user, protection faisant
    # autorité pour les sessions déjà ouvertes et pour OIDC, que ce contrôle précoce ne couvre pas).
    # Pas de log WARNING ici (contrairement à l'échec de mot de passe ci-dessus) : le mot de passe
    # était CORRECT, ce n'est pas un signal de brute-force à faire remonter à fail2ban.
    if not idp.user.active:
        raise HTTPException(status_code=403, detail="Ce compte est désactivé.")

    # last_login_at n'est PAS mise à jour ici — mécanisme générique désormais commun à local ET
    # OIDC (voir database.py::current_db_user, architecture.md §9.I) : dès la prochaine requête sur
    # cette base (le rechargement de page qui suit immédiatement ce login), current_db_user la fait
    # avancer à session.logged_in_at, fixé par set_session_cookie ci-dessous.

    # identifier sert aussi d'email pour le pré-appariement par email (voir database.py::
    # current_db_user) : convention du provider local, ses identifiants sont par nature des emails.
    set_session_cookie(response, provider_key="local", subject=payload.identifier, email=payload.identifier)
    response.set_cookie("klepsydrix_db", slug, httponly=False, samesite="lax", path="/")
    return {"status": "success"}


class PasswordResetRequestPayload(BaseModel):
    identifier: str


@router.post("/password-reset/request")
@system_scoped("Réinitialisation de mot de passe : par nature accessible à qui ne peut PAS se connecter. Réponse générique, aucune donnée renvoyée.")
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
@system_scoped("Suite de /password-reset/request : le jeton à usage unique EST l'authentification (voir PasswordResetToken.consume).")
def password_reset_confirm(payload: PasswordResetConfirmPayload, db: Session = Depends(get_db)):
    """Jeton invalide/expiré/déjà utilisé : un seul message générique (voir PasswordResetToken.consume,
    ne distingue jamais la raison précise — même principe d'énumération que /password-reset/request)."""
    idp = PasswordResetToken.consume(db, payload.token)
    if idp is None:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré.")
    idp.set_local_password(db, payload.new_password)
    db.commit()
    return {"status": "success"}


class PasswordChangePayload(BaseModel):
    current_password: str
    new_password: str


@router.post("/password/change")
def password_change(payload: PasswordChangePayload, user=Depends(current_db_user), db: Session = Depends(get_db)):
    """
    Changement de mot de passe par un utilisateur DÉJÀ connecté — contrairement à
    /password-reset/*, qui ne suppose aucune session (identifiant + jeton à usage unique en tenant
    lieu). Exempté du blocage `PASSWORD_CHANGE_REQUIRED` posé par `current_db_user` (voir
    database.py) : c'est justement la route qui permet d'en sortir, elle doit rester atteignable
    tant que le flag est posé.

    Bypass DÉLIBÉRÉ et ÉTROIT du moteur de droits (db.klepsydrix_user_id, voir models/base.py) : la
    plupart des utilisateurs (un enseignant, par ex.) n'ont aucun droit d'écriture sur
    user_identity_providers — ce n'est pas censé être le cas, changer SON PROPRE mot de passe doit
    rester possible quel que soit le profil de droits. La légitimité de cette écriture précise est
    déjà entièrement vérifiée par le code ci-dessous (idp.user_id == user.id, mot de passe actuel
    contrôlé) AVANT le bypass — même idiome que HasUserAccount._sync_user_account
    (db._syncing_user_account), un drapeau ambiant restauré dans un `finally`.
    """
    idp = db.query(UserIdentityProvider).filter(
        UserIdentityProvider.provider_key == "local",
        UserIdentityProvider.user_id == user.id,
    ).first()
    if idp is None:
        raise HTTPException(status_code=400, detail="Aucun compte local associé à cet utilisateur.")

    previous_user_id = getattr(db, "klepsydrix_user_id", None)
    db.klepsydrix_user_id = None
    try:
        if not idp.verify_password(db, payload.current_password):
            raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect.")
        idp.set_local_password(db, payload.new_password)
    finally:
        db.klepsydrix_user_id = previous_user_id

    db.commit()
    return {"status": "success"}


@router.get("/oidc/login/{provider_key}")
@system_scoped("Départ vers le fournisseur d'identité : c'est le point d'entrée de l'authentification elle-même.")
async def oidc_login(provider_key: str, request: Request, next: str = "/"):
    client = oauth.create_client(provider_key)
    if client is None:
        raise HTTPException(status_code=404, detail="Fournisseur d'identité inconnu.")
    redirect_uri = str(request.url_for("oidc_callback", provider_key=provider_key)) + f"?next={next}"
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/oidc/callback/{provider_key}", name="oidc_callback")
@system_scoped("Retour du fournisseur d'identité : atteint par une redirection navigateur, qui ne peut porter ni session ni en-tête (voir docstring).")
async def oidc_callback(provider_key: str, request: Request, response: Response, next: str = "/"):
    """
    ⚠️ Non vérifié contre un vrai fournisseur OIDC (EduConnect n'est configuré qu'avec des
    paramètres fictifs dans instance.example.yaml, voir architecture.md) — implémentation Authlib
    standard (échange de code, validation id_token), à valider dès qu'un vrai fournisseur est
    disponible.

    Pas de dépendance `db`/`get_db` ici (contrairement à login_local) — délibéré, pas un oubli :
    ce callback opère au niveau INSTANCE, avant tout choix de base (voir architecture.md §17.F),
    donc n'a besoin de résoudre aucune base. Une version antérieure déclarait
    `db: Session = Depends(get_db)` sans jamais l'utiliser dans son corps — vestige qui exigeait
    l'en-tête X-Klepsydrix-Database (voir database.py::resolve_database) alors que ce callback est
    atteint par une redirection NAVIGATEUR classique (retour du fournisseur d'identité), qui ne
    peut porter aucun en-tête personnalisé. Corrigé : ce chemin est désormais réellement atteignable
    (voir architecture.md §9.I pour l'historique complet de ce correctif, trouvé en creusant le
    décalage last_login_at entre local et OIDC, pas par un test dédié).
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
@system_scoped("Authentification par mot de passe maître. N'ouvre que la console d'instance : current_db_user rejette explicitement cette identité sur toute route applicative.")
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
@system_scoped("Déconnecter quelqu'un de déjà déconnecté doit rester un no-op réussi, pas une 401 (voir docstring du module).")
def logout(response: Response):
    clear_session_cookie(response)
    return {"status": "success"}
