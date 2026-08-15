"""
Jetons de réinitialisation de mot de passe (provider "local" uniquement — voir architecture.md
§17.G) : jeton haché (jamais en clair en base, même logique défensive qu'Argon2 pour les mots de
passe eux-mêmes — même si ici un simple SHA-256 suffit, le jeton est un aléatoire cryptographique de
256 bits, pas un secret à faible entropie qu'il faudrait ralentir pour résister au brute-force),
expiration, usage unique.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import ForeignKey, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from backend.app.models.base import Base


def _as_utc(dt: datetime) -> datetime:
    """SQLite (et PostgreSQL avec une colonne DateTime "naïve", le choix fait ici) ne retiennent pas
    l'info de fuseau horaire au sein d'une même colonne — une valeur écrite avec `tzinfo=utc` revient
    naïve à la lecture. Toujours écrite en UTC ici (voir `issue`/`consume`), donc toujours sûr de
    la réattacher explicitement avant de comparer à un autre datetime "aware" (sinon `TypeError:
    can't compare offset-naive and offset-aware datetimes`, vérifié)."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_identity_provider_id: Mapped[int] = mapped_column(
        ForeignKey("user_identity_providers.id", ondelete="CASCADE"), nullable=False,
        info={"label": "Identité"},
    )
    # Jamais exposé par l'API générique (info={"private": True}, même mécanisme que
    # UserIdentityProvider.password_hash) — un admin de base a pourtant perm_read/write sur ce
    # modèle comme sur tout autre (voir seed_admin_access), donc rien d'autre ne l'en empêcherait.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, info={"private": True})
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, info={"label": "Expire le"})
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, info={"label": "Utilisé le"})

    identity_provider: Mapped["UserIdentityProvider"] = relationship("UserIdentityProvider")

    @property
    def display_name(self) -> str:
        return f"Jeton #{self.id} (identité #{self.user_identity_provider_id})"

    @classmethod
    def issue(cls, db: Session, user_identity_provider_id: int, ttl_minutes: int) -> tuple["PasswordResetToken", str]:
        """Crée un jeton et retourne (l'enregistrement, le jeton EN CLAIR) — le jeton en clair
        n'existe que le temps de cet appel, jamais persisté sous cette forme nulle part."""
        raw_token = secrets.token_urlsafe(32)
        record = cls.create(db, {
            "user_identity_provider_id": user_identity_provider_id,
            "token_hash": hashlib.sha256(raw_token.encode()).hexdigest(),
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
        })
        return record, raw_token

    @classmethod
    def consume(cls, db: Session, raw_token: str):
        """Valide un jeton (haché, non expiré, non déjà utilisé) et le marque utilisé — retourne
        l'`UserIdentityProvider` ciblé si valide, `None` sinon (une seule réponse générique côté
        appelant HTTP, ne distingue jamais la raison précise — pas d'énumération)."""
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        record = db.query(cls).filter(cls.token_hash == token_hash).first()
        if not record or record.used_at is not None:
            return None
        if _as_utc(record.expires_at) < datetime.now(timezone.utc):
            return None
        record.update(db, {"used_at": datetime.now(timezone.utc)})
        return record.identity_provider
