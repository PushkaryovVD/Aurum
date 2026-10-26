from datetime import UTC, datetime

from app.core.config import Settings
from app.services.email_service import (
    InvitationEmail,
    build_invitation_message,
    invitation_link,
    looks_like_email,
)


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, smtp_host="smtp.test.invalid", smtp_username="sender@example.com", **overrides)


def test_smtp_is_disabled_without_host_and_sender_defaults_to_username() -> None:
    assert Settings(_env_file=None).smtp_enabled is False
    assert _settings().smtp_enabled is True
    assert _settings().smtp_sender == "sender@example.com"
    assert _settings(smtp_from="Aurum <noreply@example.com>").smtp_sender == "Aurum <noreply@example.com>"


def test_smtp_password_is_never_rendered() -> None:
    settings = _settings(smtp_password="test-only-app-password")
    assert "test-only-app-password" not in repr(settings)
    assert "test-only-app-password" not in str(settings.model_dump())


def test_only_mailbox_shaped_logins_are_mailed() -> None:
    assert looks_like_email("member@example.com")
    assert not looks_like_email("plain-login")
    assert not looks_like_email("two@@example.com")


def test_link_keeps_the_code_in_the_fragment() -> None:
    assert invitation_link("http://aurum.test:3000/", "a/b+c") == "http://aurum.test:3000/login#invite=a%2Fb%2Bc"


def test_message_escapes_names_in_html_and_includes_link() -> None:
    message = build_invitation_message(
        _settings(),
        InvitationEmail(
            recipient="member@example.com",
            workspace_name="<Family>",
            inviter_name="Owner & Co",
            role="viewer",
            link="http://aurum.test/login#invite=code",
            expires_at=datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
        ),
    )
    html = message.get_body(preferencelist=("html",)).get_content()
    plain = message.get_body(preferencelist=("plain",)).get_content()
    assert "&lt;Family&gt;" in html and "<Family>" not in html
    assert "Owner &amp; Co" in html
    assert "http://aurum.test/login#invite=code" in plain
    assert "наблюдатель" in plain and "viewer" in plain
