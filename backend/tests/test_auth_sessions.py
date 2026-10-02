"""PostgreSQL tests for opaque server-side authentication sessions."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, text

from app.models.auth import AuthRateLimit, SecurityAuditEvent, UserSession
from app.services.auth_session_service import AuthSessionService


HMAC_SECRET = "integration-test-hmac-secret-at-least-32-bytes"


async def _bootstrap_active_user(session) -> object:
    user_id = uuid4()
    workspace_id = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO users (id, normalized_login, display_name, status, password_hash)
            VALUES (:user_id, :login, 'Session owner', 'active', :password_hash)
            """
        ),
        {
            "user_id": user_id,
            "login": f"{user_id}@example.com",
            "password_hash": "$argon2id$v=19$m=8192,t=1,p=1$fixture$fixture",
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO workspaces (id, kind, display_name, created_by_user_id, personal_owner_user_id)
            VALUES (:workspace_id, 'personal', 'Private', :user_id, :user_id)
            """
        ),
        {"workspace_id": workspace_id, "user_id": user_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO workspace_memberships (id, workspace_id, user_id, role)
            VALUES (:membership_id, :workspace_id, :user_id, 'owner')
            """
        ),
        {"membership_id": uuid4(), "workspace_id": workspace_id, "user_id": user_id},
    )
    await session.execute(
        text("UPDATE users SET personal_workspace_id = :workspace_id WHERE id = :user_id"),
        {"workspace_id": workspace_id, "user_id": user_id},
    )
    await session.commit()
    return user_id


async def test_auth_schema_is_registered_and_privacy_minimized():
    assert UserSession.__table__.c.token_hmac.type.length == 32
    assert UserSession.__table__.c.csrf_secret.type.length == 32
    assert AuthRateLimit.__table__.c.bucket_hmac.type.length == 32
    assert SecurityAuditEvent.__table__.c.event_type.nullable is False
    assert "password_hash" in UserSession.metadata.tables["users"].c


async def test_session_persists_only_hmac_and_honors_idle_and_absolute_expiry(test_sessionmaker):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    service = AuthSessionService(
        hmac_secret=HMAC_SECRET,
        idle_lifetime=timedelta(minutes=30),
        absolute_lifetime=timedelta(hours=8),
    )
    async with test_sessionmaker() as session:
        user_id = await _bootstrap_active_user(session)
        issued = await service.issue(session, user_id=user_id, now=now)
        await session.commit()

        record = (await session.execute(select(UserSession))).scalar_one()
        assert issued.session_token.encode() not in bytes(record.token_hmac)
        assert issued.csrf_token.encode() not in bytes(record.csrf_secret)
        assert record.idle_expires_at == now + timedelta(minutes=30)
        assert record.absolute_expires_at == now + timedelta(hours=8)

        resolved = await service.resolve(session, token=issued.session_token, now=now + timedelta(minutes=20))
        assert resolved is not None
        assert resolved.id == record.id
        assert resolved.last_seen_at == now + timedelta(minutes=20)
        assert resolved.idle_expires_at == now + timedelta(minutes=50)
        assert service.verify_csrf(resolved, issued.csrf_token) is True

        assert await service.resolve(session, token=issued.session_token, now=now + timedelta(hours=9)) is None


async def test_revocation_and_rotation_invalidate_old_session(test_sessionmaker):
    now = datetime(2026, 1, 2, tzinfo=UTC)
    service = AuthSessionService(
        hmac_secret=HMAC_SECRET,
        idle_lifetime=timedelta(minutes=30),
        absolute_lifetime=timedelta(hours=8),
    )
    async with test_sessionmaker() as session:
        user_id = await _bootstrap_active_user(session)
        first = await service.issue(session, user_id=user_id, now=now)
        first_record = await service.resolve(session, token=first.session_token, now=now)
        rotated = await service.rotate(session, current=first_record, user_id=user_id, now=now + timedelta(minutes=1))
        await session.commit()

        assert first_record.revoked_at == now + timedelta(minutes=1)
        assert await service.resolve(session, token=first.session_token, now=now + timedelta(minutes=2)) is None
        assert await service.resolve(session, token=rotated.session_token, now=now + timedelta(minutes=2)) is not None

        rotated_record = await service.resolve(session, token=rotated.session_token, now=now + timedelta(minutes=3))
        service.revoke(rotated_record, now=now + timedelta(minutes=3))
        await session.commit()
        assert await service.resolve(session, token=rotated.session_token, now=now + timedelta(minutes=4)) is None
