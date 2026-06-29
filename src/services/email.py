"""
Email sending service - uses fastapi-mail (SMTP) or sendmail fallback
"""

import subprocess
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from config.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Configuration SMTP pour fastapi-mail
mail_conf = ConnectionConfig(
    MAIL_USERNAME=settings.SMTP_USERNAME or "",
    MAIL_PASSWORD=settings.SMTP_PASSWORD or "",
    MAIL_FROM=settings.MAIL_FROM or settings.SMTP_USERNAME or "noreply@agriintel360.lsgrouptogo.com",
    MAIL_PORT=settings.SMTP_PORT or 587,
    MAIL_SERVER=settings.SMTP_HOST or "localhost",
    MAIL_STARTTLS=settings.SMTP_TLS,
    MAIL_SSL_TLS=not settings.SMTP_TLS,
    USE_CREDENTIALS=bool(settings.SMTP_USERNAME),
    VALIDATE_CERTS=False
)


async def _send_email_robust(email: List[str], subject: str, body: str):
    """Envoie un mail via SMTP avec fallback sendmail"""
    
    # 1. Tentative via SMTP (fastapi-mail) si configuré
    if settings.SMTP_HOST and settings.SMTP_HOST != "localhost":
        try:
            fm = FastMail(mail_conf)
            message = MessageSchema(
                subject=subject,
                recipients=email,
                body=body,
                subtype=MessageType.html
            )
            await fm.send_message(message)
            logger.info("Email SMTP envoyé à %s", email)
            return True
        except Exception as e:
            logger.warning("Erreur SMTP: %s. Fallback vers sendmail...", e)

    # 2. Fallback via sendmail (système)
    SENDMAIL_PATH = "/usr/sbin/sendmail"
    if not os.path.exists(SENDMAIL_PATH):
        logger.error("sendmail introuvable sur ce système.")
        return False

    for recipient in email:
        msg = MIMEMultipart('alternative')
        msg['From'] = settings.MAIL_FROM or "noreply@agriintel360.lsgrouptogo.com"
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html', 'utf-8'))

        try:
            subprocess.run(
                [SENDMAIL_PATH, "-t"],
                input=msg.as_string(),
                text=True,
                capture_output=True,
                timeout=15
            )
            logger.info("Email envoyé via sendmail à %s", recipient)
        except Exception as e:
            logger.error("Erreur critique mail (%s): %s", recipient, e)
            return False
    return True


async def send_email(email: List[str], subject: str, body: str):
    await _send_email_robust(email, subject, body)


async def send_verification_email(email: str, token: str):
    verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    subject = f"Vérifiez votre compte {settings.PROJECT_NAME}"
    body = f"""
    <div style="font-family: sans-serif; padding: 20px; color: #333;">
        <h2>Bienvenue sur {settings.PROJECT_NAME}</h2>
        <p>Merci de vous être inscrit. Pour activer votre compte, veuillez cliquer sur le bouton ci-dessous :</p>
        <p style="margin: 30px 0;">
            <a href="{verification_link}" style="background: #10b981; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Vérifier mon compte
            </a>
        </p>
        <p>Ou copiez ce lien : <br> {verification_link}</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="font-size: 12px; color: #666;">Si vous n'avez pas créé de compte, ignorez cet email.</p>
    </div>
    """
    await _send_email_robust([email], subject, body)


async def send_password_reset_email(email: str, token: str):
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    subject = f"Réinitialisation de mot de passe - {settings.PROJECT_NAME}"
    body = f"""
    <div style="font-family: sans-serif; padding: 20px; color: #333;">
        <h2>Réinitialisation demandée</h2>
        <p>Vous avez demandé à réinitialiser votre mot de passe. Cliquez sur le bouton ci-dessous :</p>
        <p style="margin: 30px 0;">
            <a href="{reset_link}" style="background: #ef4444; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Réinitialiser mon mot de passe
            </a>
        </p>
        <p>Ce lien expirera dans 1 heure.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="font-size: 12px; color: #666;">Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.</p>
    </div>
    """
    await _send_email_robust([email], subject, body)
