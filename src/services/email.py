"""
Email sending service - uses sendmail (Hostinger-compatible)
"""

import subprocess
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional

from config.config import get_settings

settings = get_settings()

SENDMAIL_PATH = "/usr/sbin/sendmail"


def _send_via_sendmail(recipient: str, subject: str, html_body: str, from_addr: Optional[str] = None) -> bool:
    if not from_addr:
        from_addr = settings.MAIL_FROM or "noreply@agriintel360.lsgrouptogo.com"

    msg = MIMEMultipart('alternative')
    msg['From'] = from_addr
    msg['To'] = recipient
    msg['Subject'] = subject

    html_part = MIMEText(html_body, 'html', 'utf-8')
    msg.attach(html_part)

    try:
        proc = subprocess.run(
            [SENDMAIL_PATH, "-t"],
            input=msg.as_string(),
            text=True,
            capture_output=True,
            timeout=15
        )
        if proc.returncode != 0:
            print(f"Sendmail error: {proc.stderr}")
            return False
        return True
    except Exception as e:
        print(f"Sendmail exception: {e}")
        return False


async def send_email(email: List[str], subject: str, body: str):
    for recipient in email:
        ok = _send_via_sendmail(recipient, subject, body)
        if ok:
            print(f"Email sent to {recipient}: {subject}")
        else:
            print(f"Failed to send email to {recipient}")


async def send_verification_email(email: str, token: str):
    verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"

    subject = f"Verifiez votre compte {settings.PROJECT_NAME}"
    body = f"""
    <p>Merci de vous etre inscrit sur {settings.PROJECT_NAME}.</p>
    <p>Veuillez cliquer sur le lien ci-dessous pour verifier votre compte :</p>
    <p><a href="{verification_link}">{verification_link}</a></p>
    <p>Si vous n'avez pas cree de compte, veuillez ignorer cet email.</p>
    """

    ok = _send_via_sendmail(email, subject, body)
    if ok:
        print(f"Verification email sent to {email}")
    else:
        print(f"Failed to send verification email to {email}")


async def send_password_reset_email(email: str, token: str):
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"

    subject = f"Reinitialisation de votre mot de passe pour {settings.PROJECT_NAME}"
    body = f"""
    <p>Vous avez demande une reinitialisation de mot de passe.</p>
    <p>Veuillez cliquer sur le lien ci-dessous pour reinitialiser votre mot de passe :</p>
    <p><a href="{reset_link}">{reset_link}</a></p>
    <p>Ce lien expirera dans 1 heure.</p>
    <p>Si vous n'avez pas demande cette reinitialisation, veuillez ignorer cet email.</p>
    """

    ok = _send_via_sendmail(email, subject, body)
    if ok:
        print(f"Password reset email sent to {email}")
    else:
        print(f"Failed to send password reset email to {email}")
