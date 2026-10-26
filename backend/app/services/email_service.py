"""Outgoing mail (currently only workspace invitations).

Sending is best effort: an invitation is valid whether or not the e-mail went
out, and the inviter always gets the link to share by other means. SMTP runs
in a worker thread so a slow mail server never blocks the event loop.
"""
import asyncio
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from html import escape
from urllib.parse import quote

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Deliberately simple: the recipient is already a normalized login. This only
# decides whether the login looks like a mailbox worth sending to.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def looks_like_email(value: str) -> bool:
    return bool(_EMAIL_PATTERN.fullmatch(value.strip()))


def invitation_link(base_url: str, token: str) -> str:
    """Same shape as the frontend's link: the code sits in the URL fragment,
    which browsers never send to the server or to proxy logs."""
    return f"{base_url.rstrip('/')}/login#invite={quote(token, safe='')}"


@dataclass(frozen=True)
class InvitationEmail:
    recipient: str
    workspace_name: str
    inviter_name: str
    role: str
    link: str
    expires_at: datetime


_ROLE_LABELS = {
    "editor": ("редактор", "editor"),
    "viewer": ("наблюдатель", "viewer"),
}


def build_invitation_message(settings: Settings, invite: InvitationEmail) -> EmailMessage:
    role_ru, role_en = _ROLE_LABELS.get(invite.role, (invite.role, invite.role))
    expires = invite.expires_at.strftime("%Y-%m-%d %H:%M UTC")
    message = EmailMessage()
    message["Subject"] = f"Приглашение в Aurum: {invite.workspace_name} / Aurum invitation"
    message["From"] = settings.smtp_sender
    message["To"] = invite.recipient
    message.set_content(
        f"{invite.inviter_name} приглашает вас в пространство «{invite.workspace_name}» в Aurum "
        f"(роль: {role_ru}).\n\n"
        f"Откройте ссылку и создайте аккаунт с логином {invite.recipient}:\n{invite.link}\n\n"
        f"Приглашение одноразовое и действует до {expires}.\n\n"
        "---\n\n"
        f"{invite.inviter_name} invited you to the \"{invite.workspace_name}\" workspace in Aurum "
        f"(role: {role_en}).\n\n"
        f"Open the link and create an account with the login {invite.recipient}:\n{invite.link}\n\n"
        f"The invitation is single-use and valid until {expires}.\n\n"
        "Если вы не ждали этого письма, просто удалите его. / "
        "If you were not expecting this, you can ignore it.\n"
    )
    link = escape(invite.link, quote=True)
    workspace = escape(invite.workspace_name)
    inviter = escape(invite.inviter_name)
    recipient = escape(invite.recipient)
    button = (
        f'<p><a href="{link}" style="display:inline-block;padding:12px 20px;border-radius:8px;'
        f'background:#111;color:#fff;text-decoration:none">{{label}}</a></p>'
    )
    message.add_alternative(
        "<!doctype html><html><body style=\"font-family:-apple-system,Segoe UI,Roboto,sans-serif;"
        "line-height:1.5;color:#111\">"
        f"<p><b>{inviter}</b> приглашает вас в пространство «<b>{workspace}</b>» в Aurum "
        f"(роль: {role_ru}).</p>"
        f"<p>Создайте аккаунт с логином <b>{recipient}</b>.</p>"
        + button.format(label="Принять приглашение")
        + f"<p style=\"color:#666;font-size:13px\">Приглашение одноразовое и действует до {expires}.</p>"
        "<hr style=\"border:none;border-top:1px solid #ddd\">"
        f"<p><b>{inviter}</b> invited you to the <b>{workspace}</b> workspace in Aurum "
        f"(role: {role_en}). Create an account with the login <b>{recipient}</b>.</p>"
        + button.format(label="Accept invitation")
        + f"<p style=\"color:#666;font-size:13px\">Single-use, valid until {expires}.</p>"
        f"<p style=\"color:#666;font-size:12px;word-break:break-all\">{link}</p>"
        "</body></html>",
        subtype="html",
    )
    return message


def _send_blocking(settings: Settings, message: EmailMessage) -> None:
    host = settings.smtp_host.strip()
    timeout = settings.smtp_timeout_seconds
    password = settings.smtp_password.get_secret_value()
    context = ssl.create_default_context()
    if settings.smtp_security == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(host, settings.smtp_port, timeout=timeout, context=context)
    else:
        client = smtplib.SMTP(host, settings.smtp_port, timeout=timeout)
    with client:
        if settings.smtp_security == "starttls":
            client.starttls(context=context)
        if settings.smtp_username.strip() and password:
            client.login(settings.smtp_username.strip(), password)
        client.send_message(message)


async def send_invitation_email(settings: Settings, invite: InvitationEmail) -> bool:
    """Returns True only when the SMTP server accepted the message."""
    if not settings.smtp_enabled or not looks_like_email(invite.recipient):
        return False
    message = build_invitation_message(settings, invite)
    try:
        await asyncio.to_thread(_send_blocking, settings, message)
    except (OSError, smtplib.SMTPException) as exc:
        # The exception text never contains the password; the token is not logged.
        logger.warning("Invitation e-mail was not sent: %s", type(exc).__name__)
        return False
    return True
