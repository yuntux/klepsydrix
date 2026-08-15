"""
Envoi d'emails sortants (réinitialisation de mot de passe, voir architecture.md §17.G) — enveloppe
fastapi-mail. `smtp:` (instance.yaml) absente ou incomplète = envoi IMPOSSIBLE, erreur explicite
levée ici plutôt qu'un repli silencieux (ex: journaliser le lien à la place enverrait un signal
dangereux si oublié actif en production) — voir SmtpConfig, config.py.
"""
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from backend.app.core.config import settings


def _connection_config() -> ConnectionConfig:
    cfg = settings.smtp
    if not (cfg.host and cfg.user and cfg.password and cfg.from_address):
        raise RuntimeError(
            "Envoi d'email impossible : la section smtp: de instance.yaml est absente ou "
            "incomplète (host/user/password/from_address requis)."
        )
    return ConnectionConfig(
        MAIL_USERNAME=cfg.user,
        MAIL_PASSWORD=cfg.password,
        MAIL_FROM=cfg.from_address,
        MAIL_PORT=cfg.port,
        MAIL_SERVER=cfg.host,
        MAIL_STARTTLS=cfg.use_tls,
        MAIL_SSL_TLS=not cfg.use_tls,
        USE_CREDENTIALS=True,
    )


async def send_password_reset_email(to_email: str, reset_url: str) -> None:
    message = MessageSchema(
        subject="Klepsydrix — Réinitialisation de votre mot de passe",
        recipients=[to_email],
        body=(
            "Une réinitialisation de mot de passe a été demandée pour ce compte.\n\n"
            f"{reset_url}\n\n"
            f"Ce lien expire dans {settings.auth.password_reset_ttl_minutes} minutes. "
            "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email."
        ),
        subtype=MessageType.plain,
    )
    await FastMail(_connection_config()).send_message(message)
