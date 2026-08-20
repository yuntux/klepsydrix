"""
Utilisateurs et fournisseurs d'identité (voir specs/, plan "Multi-SGBD, Multi-Base, Utilisateurs/
IDP, Droits, Console Admin"). `User` est le compte d'authentification, rattaché à au plus un
objet-personne (Teacher/NonTeachingStaff/Student/Parent, voir HasUserAccount ci-dessous) et à un ou
plusieurs `UserIdentityProvider` (une ligne par fournisseur d'identité utilisé pour se connecter).
"""
import re
from datetime import datetime
from typing import Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from sqlalchemy import ForeignKey, String, JSON, DateTime, Boolean, UniqueConstraint, true as sa_true, false as sa_false
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from backend.app.models.base import Base, constrains

# Argon2id (OWASP, argon2-cffi) : mémoire-difficile, résistant GPU/ASIC, sel et paramètres de coût
# gérés par la bibliothèque (jamais à gérer soi-même) — voir architecture.md, provider "local".
_password_hasher = PasswordHasher()


def _validate_password_strength(password: str) -> None:
    """
    Politique de robustesse des mots de passe locaux (AuthConfig.password_min_length,
    core/config.py) : longueur minimale ET diversité de caractères — la longueur seule laisserait
    passer des mots de passe triviaux ("aaaaaaaa"). Point d'application UNIQUE
    (register_local_password/set_local_password ci-dessous) : tout appelant (reset par email,
    changement connecté, création du compte admin initial d'une base) passe forcément par l'un des
    deux, jamais de vérification dupliquée endpoint par endpoint.
    """
    from backend.app.core.config import settings

    min_length = settings.auth.password_min_length
    if len(password) < min_length:
        raise ValueError(f"Le mot de passe doit contenir au moins {min_length} caractères.")

    classes_present = sum([
        bool(re.search(r"[a-z]", password)),
        bool(re.search(r"[A-Z]", password)),
        bool(re.search(r"[0-9]", password)),
        bool(re.search(r"[^a-zA-Z0-9]", password)),
    ])
    if classes_present < 3:
        raise ValueError(
            "Le mot de passe doit combiner au moins 3 des 4 catégories suivantes : majuscules, "
            "minuscules, chiffres, caractères spéciaux."
        )


class User(Base):
    __tablename__ = "users"
    # Gestion des comptes/de la sécurité, orthogonale aux données de planning que le mode exclusif
    # protège (voir core/exclusive_mode.py::_check_exclusive_mode, architecture.md §16.G) — une
    # création/mise à jour de compte ne doit jamais être bloquée par une résolution en cours ailleurs.
    __exclusive_mode_exempt__ = True

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom"})
    first_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Prénom"})
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Email"})
    # Désactivation d'un compte (local OU fédéré OIDC — voir database.py::current_db_user, seul
    # point traversé par les deux) sans le supprimer : conserve l'historique/les rattachements
    # (Teacher, cours, vœux...) tout en coupant l'accès. Jamais géré par un simple "supprimer
    # l'identité" (UserIdentityProvider) : un compte OIDC n'a pas de mot de passe à invalider, la
    # seule coupure possible est ici, au niveau du User.
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=sa_true(), info={"label": "Actif"})

    identity_providers: Mapped[list["UserIdentityProvider"]] = relationship(
        "UserIdentityProvider", back_populates="user", cascade="all, delete-orphan",
        info={"label": "Fournisseurs d'identité"},
    )
    groups: Mapped[list["ResGroup"]] = relationship("ResGroup", secondary="res_group_users", back_populates="users", info={"label": "Groupes"})

    # Réciproques de HasUserAccount.user (voir plus bas) — accès direct "quel Teacher/Student/...
    # correspond à ce User", utilisé notamment par les valeurs magiques de domaine (voir
    # core/access_control.py, ex: "user.teacher.id"). uselist=False : au plus un objet-personne par
    # User (garanti par HasUserAccount._check_user_not_already_linked).
    teacher: Mapped[Optional["Teacher"]] = relationship("Teacher", back_populates="user", uselist=False, viewonly=True)
    non_teaching_staff: Mapped[Optional["NonTeachingStaff"]] = relationship("NonTeachingStaff", back_populates="user", uselist=False, viewonly=True)
    student: Mapped[Optional["Student"]] = relationship("Student", back_populates="user", uselist=False, viewonly=True)
    parent: Mapped[Optional["Parent"]] = relationship("Parent", back_populates="user", uselist=False, viewonly=True)

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def update(self, db: Session, vals: dict):
        """
        Deux garde-fous, vérifiés contre l'état AVANT délégation (donc contre l'ancienne valeur) :
        - l'email ne peut jamais être vidé une fois posé (canal de réinitialisation de mot de passe,
          voir auth_endpoints.py) — seul son remplacement par une autre valeur est permis.
        - si `group_ids` fait partie de la mise à jour (retrait possible du groupe "Admin"), le
          groupe Admin ne doit jamais se retrouver sans aucun membre après coup (voir
          access.py::_admin_group, même invariant que ResGroup.update/User.delete ci-dessous).
        """
        if 'email' in vals and not vals['email'] and self.email:
            raise ValueError("Impossible de supprimer l'adresse email d'un utilisateur.")

        # Capturé AVANT l'appel à super() : CRUDMixin.update() retire ("pop") les clés de relation
        # collection (dont group_ids) du dict `vals` PENDANT son propre traitement — vals étant
        # passé par référence, un test après coup verrait toujours 'group_ids' absent, qu'il ait
        # ou non fait partie de la requête initiale.
        group_ids_changed = 'group_ids' in vals

        instance = super().update(db, vals)

        if group_ids_changed:
            from backend.app.models.access import _admin_group
            admin_group = _admin_group(db)
            if admin_group is not None and not admin_group.users:
                raise ValueError("Impossible de retirer le dernier utilisateur du groupe Admin.")

        return instance

    def delete(self, db: Session):
        """Refuse de supprimer le dernier membre du groupe "Admin" — même invariant que
        ResGroup.update/User.update ci-dessus, pour le chemin "suppression du compte" (direct ou en
        cascade via HasUserAccount.delete, voir plus bas)."""
        from backend.app.models.access import _admin_group
        admin_group = _admin_group(db)
        if admin_group is not None and self in admin_group.users and len(admin_group.users) == 1:
            raise ValueError("Impossible de supprimer le dernier utilisateur du groupe Admin.")
        return super().delete(db)


class UserIdentityProvider(Base):
    __tablename__ = "user_identity_providers"
    __table_args__ = (
        UniqueConstraint("provider_key", "external_subject", name="uq_user_identity_provider_subject"),
    )
    # Voir User.__exclusive_mode_exempt__ ci-dessus — couvre notamment last_login_at, mis à jour à
    # CHAQUE requête authentifiée (voir database.py::current_db_user), y compris pendant une
    # résolution automatique en cours sur cette même base.
    __exclusive_mode_exempt__ = True

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, info={"label": "Utilisateur"})
    provider_key: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Fournisseur", "placeholder": "ex: educonnect"})
    external_subject: Mapped[str] = mapped_column(String(255), nullable=False, info={"label": "Identifiant externe"})
    first_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, info={"label": "Première connexion"})
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, info={"label": "Dernière connexion"})
    params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, info={"label": "Paramètres"})
    # Provider "local" uniquement — jamais lu/écrit par l'API générique (voir generic.py,
    # info={"private": True}, architecture.md). Argon2id (argon2-cffi), jamais en clair.
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, info={"private": True})
    # Provider "local" uniquement (comme password_hash) : force un changement de mot de passe à la
    # prochaine connexion (posé par un admin, ex: après création d'un compte ou incident de
    # sécurité) — bloqué jusque-là par current_db_user (voir database.py), sauf sur les routes de
    # changement de mot de passe elles-mêmes. Toujours purgé par set_local_password ci-dessous, quel
    # que soit le chemin qui pose effectivement un nouveau mot de passe (auto-service, reset par
    # email, ou admin) : la seule chose qui compte est qu'un nouveau mot de passe ait été choisi.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false(),
        info={"label": "Doit changer son mot de passe à la prochaine connexion"},
    )

    user: Mapped["User"] = relationship("User", back_populates="identity_providers")

    @property
    def display_name(self) -> str:
        return f"{self.provider_key}:{self.external_subject}"

    @classmethod
    def register_local_password(cls, db: Session, user_id: int, external_subject: str, password: str) -> "UserIdentityProvider":
        """Crée la ligne d'identité du provider local (mot de passe) pour un User existant."""
        _validate_password_strength(password)
        return cls.create(db, {
            "user_id": user_id,
            "provider_key": "local",
            "external_subject": external_subject,
            "password_hash": _password_hasher.hash(password),
        })

    def verify_password(self, db: Session, password: str) -> bool:
        """
        Vérifie `password` contre `password_hash` sur CETTE identité déjà résolue — factorisé hors
        de `verify_local_password` ci-dessous pour être réutilisable par un appelant qui a déjà son
        `UserIdentityProvider` en main (ex: changement de mot de passe d'un utilisateur connecté,
        voir auth_endpoints.py, où l'identité vient de `current_db_user`, pas d'un identifiant saisi
        à vérifier depuis zéro).
        """
        if not self.password_hash:
            return False
        try:
            _password_hasher.verify(self.password_hash, password)
        except (VerifyMismatchError, InvalidHash):
            return False
        if _password_hasher.check_needs_rehash(self.password_hash):
            # Paramètres de coût augmentés depuis le dernier hachage (matériel plus rapide) :
            # ré-empreinte silencieuse à la prochaine vérification réussie, sans action utilisateur.
            self.update(db, {"password_hash": _password_hasher.hash(password)})
        return True

    @classmethod
    def verify_local_password(cls, db: Session, external_subject: str, password: str) -> Optional["UserIdentityProvider"]:
        """
        Vérifie un couple (identifiant, mot de passe) contre le provider local. Retourne la ligne
        d'identité en cas de succès (None sinon) — ne distingue jamais "identifiant inconnu" de
        "mot de passe incorrect" dans le message d'erreur côté appelant (énumération).
        """
        idp = db.query(cls).filter(cls.provider_key == "local", cls.external_subject == external_subject).first()
        if not idp or not idp.verify_password(db, password):
            return None
        return idp

    def set_local_password(self, db: Session, password: str) -> "UserIdentityProvider":
        _validate_password_strength(password)
        # Purge systématique de must_change_password : toute pose effective d'un nouveau mot de
        # passe (auto-service, reset par email, ou ici) satisfait l'obligation, quel que soit le
        # chemin emprunté — voir la colonne ci-dessus pour le détail.
        return self.update(db, {"password_hash": _password_hasher.hash(password), "must_change_password": False})


class HasUserAccount:
    """
    Mixin pour un modèle-personne relié à un compte `User` (Teacher, NonTeachingStaff, Student,
    Parent — voir architecture.md). Le modèle qui l'utilise doit déclarer :
    - `user_id` : FK optionnelle vers `users.id`, `ondelete="RESTRICT"`, `unique=True`
    - `user` : relationship("User")
    - `first_name`/`last_name`/`email` : mêmes noms que sur `User` (utilisés tels quels par la
      synchro ci-dessous)
    Déclarer AVANT `Base` dans les bases de la classe (`class Teacher(HasUserAccount, Base)`) pour
    que `super().update()`/`super().delete()` délèguent correctement à `CRUDMixin`.
    """
    # Champs synchronisés vers le User rattaché — filtré par sous-classe : Student, par exemple,
    # ne porte pas de colonne email (contact via son tuteur/ses parents), donc n'en synchronise pas.
    _USER_MIRROR_FIELDS_CANDIDATES = ("first_name", "last_name", "email")

    @classmethod
    def _user_mirror_fields(cls):
        return [f for f in cls._USER_MIRROR_FIELDS_CANDIDATES if hasattr(cls, f)]

    @constrains("user_id")
    def _check_user_not_already_linked(self, db: Session):
        """Un `User` ne peut être pointé que par AU PLUS un objet-personne (toutes classes confondues)."""
        if not self.user_id:
            return
        from backend.app.models.teacher import Teacher
        from backend.app.models.non_teaching_staff import NonTeachingStaff
        from backend.app.models.student import Student
        from backend.app.models.parent import Parent

        for model in (Teacher, NonTeachingStaff, Student, Parent):
            if model is self.__class__:
                continue
            existing = db.query(model).filter(model.user_id == self.user_id).first()
            if existing:
                raise ValueError(
                    f"Cet utilisateur est déjà rattaché à {model.__name__} #{existing.id} — "
                    f"un même compte utilisateur ne peut être rattaché qu'à un seul enregistrement."
                )

    def _sync_user_account(self, db: Session, vals: dict, mirror_fields: list):
        # Ne propage jamais None : certaines colonnes source (ex: Teacher.first_name) sont
        # nullable alors que User.first_name ne l'est pas — un champ non renseigné côté
        # objet-personne ne doit pas écraser une valeur déjà connue côté User.
        if getattr(db, "_syncing_user_account", False):
            return
        if not self.user_id or not any(f in vals for f in mirror_fields):
            return
        to_sync = {f: v for f in mirror_fields if (v := getattr(self, f)) is not None}
        if not to_sync:
            return
        db._syncing_user_account = True
        try:
            self.user.update(db, to_sync)
        finally:
            db._syncing_user_account = False

    @classmethod
    def create(cls, db: Session, vals: dict):
        """Même synchro qu'update() ci-dessous, pour la création (symétrie délibérée)."""
        instance = super().create(db, vals)
        instance._sync_user_account(db, vals, cls._user_mirror_fields())
        return instance

    def update(self, db: Session, vals: dict):
        """Synchro nom/prénom/email vers le User rattaché (sens unique : l'objet-personne écrase le User)."""
        instance = super().update(db, vals)
        instance._sync_user_account(db, vals, self._user_mirror_fields())
        return instance

    def delete(self, db: Session):
        """Supprimer l'objet-personne supprime son compte User (jamais l'inverse)."""
        user = self.user
        result = super().delete(db)
        if user:
            user.delete(db)
        return result
