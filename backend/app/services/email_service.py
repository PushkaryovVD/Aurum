"""Outgoing mail: workspace invitations and password-reset links.

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


async def _deliver(settings: Settings, message: EmailMessage, kind: str) -> bool:
    """Returns True only when the SMTP server accepted the message."""
    try:
        await asyncio.to_thread(_send_blocking, settings, message)
    except (OSError, smtplib.SMTPException) as exc:
        # The exception text never contains the password; tokens are not logged.
        logger.warning("%s e-mail was not sent: %s", kind, type(exc).__name__)
        return False
    return True


async def send_invitation_email(settings: Settings, invite: InvitationEmail) -> bool:
    """Returns True only when the SMTP server accepted the message."""
    if not settings.smtp_enabled or not looks_like_email(invite.recipient):
        return False
    return await _deliver(settings, build_invitation_message(settings, invite), "Invitation")


def password_reset_link(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/reset-password#token={quote(token, safe='')}"


@dataclass(frozen=True)
class PasswordResetEmail:
    recipient: str
    display_name: str
    link: str
    expires_at: datetime


def build_password_reset_message(settings: Settings, reset: PasswordResetEmail) -> EmailMessage:
    expires = reset.expires_at.strftime("%Y-%m-%d %H:%M UTC")
    message = EmailMessage()
    message["Subject"] = "Восстановление пароля Aurum / Aurum password reset"
    message["From"] = settings.smtp_sender
    message["To"] = reset.recipient
    message.set_content(
        f"Здравствуйте, {reset.display_name}!\n\n"
        "Кто-то запросил сброс пароля для вашего аккаунта Aurum. Чтобы задать новый пароль, "
        f"откройте ссылку:\n{reset.link}\n\n"
        f"Ссылка действует до {expires} и перестаёт работать после смены пароля. "
        "После сброса все ваши сеансы будут завершены.\n"
        "Если вы не запрашивали сброс, просто проигнорируйте письмо — пароль не изменится.\n\n"
        "---\n\n"
        f"Hello {reset.display_name},\n\n"
        f"Someone asked to reset the password of your Aurum account. To set a new one, open:\n{reset.link}\n\n"
        f"The link is valid until {expires} and stops working once the password changes. "
        "Resetting signs you out everywhere.\n"
        "If you did not ask for this, ignore this e-mail and your password stays the same.\n"
    )
    link = escape(reset.link, quote=True)
    name = escape(reset.display_name)
    button = (
        f'<p><a href="{link}" style="display:inline-block;padding:12px 20px;border-radius:8px;'
        f'background:#111;color:#fff;text-decoration:none">{{label}}</a></p>'
    )
    message.add_alternative(
        "<!doctype html><html><body style=\"font-family:-apple-system,Segoe UI,Roboto,sans-serif;"
        "line-height:1.5;color:#111\">"
        f"<p>Здравствуйте, {name}!</p>"
        "<p>Кто-то запросил сброс пароля для вашего аккаунта Aurum.</p>"
        + button.format(label="Задать новый пароль")
        + f"<p style=\"color:#666;font-size:13px\">Ссылка действует до {expires}. Если вы не запрашивали "
        "сброс, проигнорируйте письмо — пароль не изменится.</p>"
        "<hr style=\"border:none;border-top:1px solid #ddd\">"
        f"<p>Hello {name}, someone asked to reset your Aurum password.</p>"
        + button.format(label="Set a new password")
        + f"<p style=\"color:#666;font-size:13px\">Valid until {expires}. If you did not ask for this, "
        "ignore this e-mail.</p>"
        f"<p style=\"color:#666;font-size:12px;word-break:break-all\">{link}</p>"
        "</body></html>",
        subtype="html",
    )
    return message


async def send_password_reset_email(settings: Settings, reset: PasswordResetEmail) -> bool:
    if not settings.smtp_enabled or not looks_like_email(reset.recipient):
        return False
    return await _deliver(settings, build_password_reset_message(settings, reset), "Password reset")
