"""Direct PostgreSQL tests for identity/workspace schema invariants."""
import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def _bootstrap_personal_workspace(
    session: AsyncSession,
    *,
    login: str,
) -> tuple[UUID, UUID, UUID]:
    user_id = uuid4()
    workspace_id = uuid4()
    membership_id = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO users (id, normalized_login, display_name, status)
            VALUES (:user_id, :login, :login, 'active')
            """
        ),
        {"user_id": user_id, "login": login},
    )
    await session.execute(
        text(
            """
            INSERT INTO workspaces (
                id, kind, display_name, created_by_user_id, personal_owner_user_id
            )
            VALUES (:workspace_id, 'personal', :login, :user_id, :user_id)
            """
        ),
        {"workspace_id": workspace_id, "user_id": user_id, "login": login},
    )
    await session.execute(
        text(
            """
            INSERT INTO workspace_memberships (id, workspace_id, user_id, role)
            VALUES (:membership_id, :workspace_id, :user_id, 'owner')
            """
        ),
        {
            "membership_id": membership_id,
            "workspace_id": workspace_id,
            "user_id": user_id,
        },
    )
    await session.execute(
        text("UPDATE users SET personal_workspace_id = :workspace_id WHERE id = :user_id"),
        {"workspace_id": workspace_id, "user_id": user_id},
    )
    await session.commit()
    return user_id, workspace_id, membership_id


async def _create_household(
    session: AsyncSession,
    *,
    creator_id: UUID,
    owner_ids: list[UUID],
) -> UUID:
    workspace_id = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO workspaces (id, kind, display_name, created_by_user_id)
            VALUES (:workspace_id, 'household', 'Household', :creator_id)
            """
        ),
        {"workspace_id": workspace_id, "creator_id": creator_id},
    )
    for owner_id in owner_ids:
        await session.execute(
            text(
                """
                INSERT INTO workspace_memberships (id, workspace_id, user_id, role)
                VALUES (:membership_id, :workspace_id, :user_id, 'owner')
                """
            ),
            {
                "membership_id": uuid4(),
                "workspace_id": workspace_id,
                "user_id": owner_id,
            },
        )
    await session.commit()
    return workspace_id


async def test_atomic_personal_workspace_bootstrap_is_valid(test_sessionmaker):
    async with test_sessionmaker() as session:
        user_id, workspace_id, membership_id = await _bootstrap_personal_workspace(
            session,
            login="owner@example.com",
        )
        result = await session.execute(
            text(
                """
                SELECT u.personal_workspace_id, w.personal_owner_user_id, m.role
                FROM users u
                JOIN workspaces w ON w.id = u.personal_workspace_id
                JOIN workspace_memberships m
                  ON m.workspace_id = w.id AND m.user_id = u.id
                WHERE u.id = :user_id AND m.id = :membership_id
                """
            ),
            {"user_id": user_id, "membership_id": membership_id},
        )

    personal_workspace_id, personal_owner_user_id, role = result.one()
    assert personal_workspace_id == workspace_id
    assert personal_owner_user_id == user_id
    assert role == "owner"


async def test_active_user_without_personal_workspace_is_rejected(test_sessionmaker):
    async with test_sessionmaker() as session:
        await session.execute(
            text(
                """
                INSERT INTO users (id, normalized_login, display_name, status)
                VALUES (:id, 'orphan@example.com', 'Orphan', 'active')
                """
            ),
            {"id": uuid4()},
        )
        with pytest.raises(DBAPIError, match="active user must have exactly one personal workspace"):
            await session.commit()


async def test_second_personal_workspace_is_rejected(test_sessionmaker):
    async with test_sessionmaker() as session:
        user_id, _, _ = await _bootstrap_personal_workspace(session, login="single@example.com")
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    INSERT INTO workspaces (
                        id, kind, display_name, created_by_user_id, personal_owner_user_id
                    )
                    VALUES (:id, 'personal', 'Second', :user_id, :user_id)
                    """
                ),
                {"id": uuid4(), "user_id": user_id},
            )


async def test_second_active_personal_membership_is_rejected(test_sessionmaker):
    async with test_sessionmaker() as session:
        _, workspace_id, _ = await _bootstrap_personal_workspace(session, login="first@example.com")
        extra_user_id = uuid4()
        await session.execute(
            text(
                """
                INSERT INTO users (id, normalized_login, display_name, status)
                VALUES (:id, 'extra@example.com', 'Extra', 'disabled')
                """
            ),
            {"id": extra_user_id},
        )
        await session.execute(
            text(
                """
                INSERT INTO workspace_memberships (id, workspace_id, user_id, role)
                VALUES (:id, :workspace_id, :user_id, 'viewer')
                """
            ),
            {"id": uuid4(), "workspace_id": workspace_id, "user_id": extra_user_id},
        )
        with pytest.raises(DBAPIError, match="personal workspace must have exactly one active owner membership"):
            await session.commit()


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM workspace_memberships WHERE id = :membership_id",
        "UPDATE workspace_memberships SET revoked_at = now() WHERE id = :membership_id",
    ],
    ids=["removed", "revoked"],
)
async def test_personal_owner_membership_cannot_be_removed_or_revoked(
    test_sessionmaker,
    statement: str,
):
    async with test_sessionmaker() as session:
        _, _, membership_id = await _bootstrap_personal_workspace(session, login="member@example.com")
        await session.execute(text(statement), {"membership_id": membership_id})
        with pytest.raises(DBAPIError, match="personal workspace must have exactly one active owner membership"):
            await session.commit()


@pytest.mark.parametrize(
    "assignment",
    ["kind = 'household'", "personal_owner_user_id = NULL"],
    ids=["kind", "owner"],
)
async def test_personal_workspace_kind_and_owner_are_immutable(test_sessionmaker, assignment: str):
    async with test_sessionmaker() as session:
        _, workspace_id, _ = await _bootstrap_personal_workspace(session, login="immutable@example.com")
        with pytest.raises(DBAPIError, match="personal workspace kind and owner are immutable"):
            await session.execute(
                text(f"UPDATE workspaces SET {assignment} WHERE id = :workspace_id"),
                {"workspace_id": workspace_id},
            )


async def test_personal_workspace_pointer_is_immutable_after_bootstrap(test_sessionmaker):
    async with test_sessionmaker() as session:
        user_id, _, _ = await _bootstrap_personal_workspace(session, login="pointer@example.com")
        with pytest.raises(DBAPIError, match="personal workspace pointer is immutable"):
            await session.execute(
                text("UPDATE users SET personal_workspace_id = NULL WHERE id = :user_id"),
                {"user_id": user_id},
            )


async def test_household_final_owner_removal_is_rejected(test_sessionmaker):
    async with test_sessionmaker() as session:
        user_id, _, _ = await _bootstrap_personal_workspace(session, login="household@example.com")
        household_id = await _create_household(session, creator_id=user_id, owner_ids=[user_id])
        await session.execute(
            text(
                """
                UPDATE workspace_memberships
                SET revoked_at = now()
                WHERE workspace_id = :workspace_id AND user_id = :user_id
                """
            ),
            {"workspace_id": household_id, "user_id": user_id},
        )
        with pytest.raises(DBAPIError, match="household workspace must have an active owner"):
            await session.commit()


async def test_concurrent_household_owner_removals_serialize_on_workspace_lock(
    test_sessionmaker: async_sessionmaker[AsyncSession],
):
    async with test_sessionmaker() as setup:
        first_id, _, _ = await _bootstrap_personal_workspace(setup, login="first-owner@example.com")
        second_id, _, _ = await _bootstrap_personal_workspace(setup, login="second-owner@example.com")
        household_id = await _create_household(
            setup,
            creator_id=first_id,
            owner_ids=[first_id, second_id],
        )

    second_has_lock = asyncio.Event()

    async def remove_second_owner() -> None:
        async with test_sessionmaker() as second:
            await second.execute(
                text("SELECT id FROM workspaces WHERE id = :id FOR UPDATE"),
                {"id": household_id},
            )
            second_has_lock.set()
            await second.execute(
                text(
                    """
                    UPDATE workspace_memberships SET revoked_at = now()
                    WHERE workspace_id = :workspace_id AND user_id = :user_id
                    """
                ),
                {"workspace_id": household_id, "user_id": second_id},
            )
            with pytest.raises(DBAPIError, match="household workspace must have an active owner"):
                await second.commit()

    async with test_sessionmaker() as first:
        await first.execute(
            text("SELECT id FROM workspaces WHERE id = :id FOR UPDATE"),
            {"id": household_id},
        )
        await first.execute(
            text(
                """
                UPDATE workspace_memberships SET revoked_at = now()
                WHERE workspace_id = :workspace_id AND user_id = :user_id
                """
            ),
            {"workspace_id": household_id, "user_id": first_id},
        )
        competing_removal = asyncio.create_task(remove_second_owner())
        await asyncio.sleep(0.1)
        assert not second_has_lock.is_set()
        await first.commit()

    await competing_removal
