"""
Email sending service
"""

from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from typing import List, Optional
import os

from config.config import get_settings

settings = get_settings()

# Mail connection config - make it optional
conf: Optional[ConnectionConfig] = None
if settings.MAIL_USERNAME and settings.MAIL_PASSWORD and settings.MAIL_SERVER and settings.MAIL_FROM:
    conf = ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME or "",
        MAIL_PASSWORD=settings.MAIL_PASSWORD or "",
        MAIL_FROM=settings.MAIL_FROM or "",
        MAIL_PORT=settings.MAIL_PORT,
        MAIL_SERVER=settings.MAIL_SERVER or "",
        MAIL_STARTTLS=settings.MAIL_STARTTLS,
        MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True
    )


async def send_email(email: List[EmailStr], subject: str, body: str):
    """Send an email"""
    # If email is not configured, just return
    if conf is None:
        print("Email not configured, skipping email send")
        return
    
    message = MessageSchema(
        subject=subject,
        recipients=email,
        body=body,
        subtype="html"
    )
    
    fm = FastMail(conf)
    await fm.send_message(message)


async def send_verification_email(email: EmailStr, token: str):
    """Send email verification email"""
    # If email is not configured, just return
    if conf is None:
        print("Email not configured, skipping verification email")
        return
    
    verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    
    subject = f"Vérifiez votre compte {settings.PROJECT_NAME}"
    body = f"""
    <p>Merci de vous être inscrit sur {settings.PROJECT_NAME}.</p>
    <p>Veuillez cliquer sur le lien ci-dessous pour vérifier votre compte :</p>
    <p><a href="{verification_link}">{verification_link}</a></p>
    <p>Si vous n'avez pas créé de compte, veuillez ignorer cet email.</p>
    """
    
    await send_email([email], subject, body)


async def send_password_reset_email(email: EmailStr, token: str):
    """Send password reset email"""
    # If email is not configured, just return
    if conf is None:
        print("Email not configured, skipping password reset email")
        return
    
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    
    subject = f"Réinitialisation de votre mot de passe pour {settings.PROJECT_NAME}"
    body = f"""
    <p>Vous avez demandé une réinitialisation de mot de passe.</p>
    <p>Veuillez cliquer sur le lien ci-dessous pour réinitialiser votre mot de passe :</p>
    <p><a href="{reset_link}">{reset_link}</a></p>
    <p>Ce lien expirera dans 1 heure.</p>
    <p>Si vous n'avez pas demandé cette réinitialisation, veuillez ignorer cet email.</p>
    """
    
    await send_email([email], subject, body)