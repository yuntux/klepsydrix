"""
Utilisateurs et fournisseurs d'identité (voir specs/, plan "Multi-SGBD, Multi-Base, Utilisateurs/
IDP, Droits, Console Admin"). `User` est le compte d'authentification, rattaché à au plus un
objet-personne (Teacher/NonTeachingStaff/Student/Parent, voir HasUserAccount ci-dessous) et à un ou
plusieurs `UserIdentityProvider` (une ligne par fournisseur d'identité utilisé pour se connecter).
"""
from datetime import datetime
from typing import Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from sqlalchemy import ForeignKey, String, JSON, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from backend.app.models.base import Base, constrains

# Argon2id (OWASP, argon2-cffi) : mémoire-difficile, résistant GPU/ASIC, sel et paramètres de coût
# gérés par la bibliothèque (jamais à gérer soi-même) — voir architecture.md, provider "local".
_password_hasher = PasswordHasher()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Nom"})
    first_name: Mapped[str] = mapped_column(String(50), nullable=False, info={"label": "Prénom"})
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, info={"label": "Email"})

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


class UserIdentityProvider(Base):
    __tablename__ = "user_identity_providers"
    __table_args__ = (
        UniqueConstraint("provider_key", "external_subject", name="uq_user_identity_provider_subject"),
    )

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

    user: Mapped["User"] = relationship("User", back_populates="identity_providers")

    @property
    def display_name(self) -> str:
        return f"{self.provider_key}:{self.external_subject}"

    @classmethod
    def register_local_password(cls, db: Session, user_id: int, external_subject: str, password: str) -> "UserIdentityProvider":
        """Crée la ligne d'identité du provider local (mot de passe) pour un User existant."""
        return cls.create(db, {
            "user_id": user_id,
            "provider_key": "local",
            "external_subject": external_subject,
            "password_hash": _password_hasher.hash(password),
        })

    @classmethod
    def verify_local_password(cls, db: Session, external_subject: str, password: str) -> Optional["UserIdentityProvider"]:
        """
        Vérifie un couple (identifiant, mot de passe) contre le provider local. Retourne la ligne
        d'identité en cas de succès (None sinon) — ne distingue jamais "identifiant inconnu" de
        "mot de passe incorrect" dans le message d'erreur côté appelant (énumération).
        """
        idp = db.query(cls).filter(cls.provider_key == "local", cls.external_subject == external_subject).first()
        if not idp or not idp.password_hash:
            return None
        try:
            _password_hasher.verify(idp.password_hash, password)
        except (VerifyMismatchError, InvalidHash):
            return None
        if _password_hasher.check_needs_rehash(idp.password_hash):
            # Paramètres de coût augmentés depuis le dernier hachage (matériel plus rapide) :
            # ré-empreinte silencieuse à la prochaine connexion réussie, sans action utilisateur.
            idp.update(db, {"password_hash": _password_hasher.hash(password)})
        return idp

    def set_local_password(self, db: Session, password: str) -> "UserIdentityProvider":
        return self.update(db, {"password_hash": _password_hasher.hash(password)})


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
