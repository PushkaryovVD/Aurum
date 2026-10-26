"""The bot must always say which space a quick entry lands in, and switching
spaces must respect current memberships."""
from uuid import UUID

import pytest

from app import telegram_bot
from app.models.account import Account
from app.models.auth import TelegramIdentity
from app.models.enums import AccountType
from app.models.workspace import WorkspaceMembership, WorkspaceRole
from app.services.workspace_service import create_household
from tests.test_auth_api import _bootstrap_user

TELEGRAM_USER = 424242


@pytest.fixture
def bot(test_sessionmaker, monkeypatch):
    # The bot opens its own sessions; point them at the disposable test database.
    monkeypatch.setattr(telegram_bot, "AsyncSessionLocal", test_sessionmaker)
    instance = object.__new__(telegram_bot.TelegramBot)
    instance.webapp_url = ""
    return instance


async def _linked_owner(test_sessionmaker) -> tuple[UUID, UUID, UUID]:
    user_id, personal_id, _ = await _bootstrap_user(test_sessionmaker)
    async with test_sessionmaker() as session:
        family, _ = await create_household(session, creator_id=user_id, display_name="Family")
        session.add(Account(workspace_id=personal_id, name="Kaspi", type=AccountType.DEBIT_CARD, currency="KZT"))
        session.add(Account(workspace_id=family.id, name="Family card", type=AccountType.DEBIT_CARD, currency="KZT"))
        session.add(TelegramIdentity(user_id=user_id, default_workspace_id=personal_id, telegram_user_id=TELEGRAM_USER))
        await session.commit()
        return user_id, personal_id, family.id


async def test_switching_space_moves_quick_entry_and_picks_its_only_account(bot, test_sessionmaker):
    _, _, family_id = await _linked_owner(test_sessionmaker)

    async with test_sessionmaker() as session:
        # A new family space may come with its own starter account; keep one.
        from sqlalchemy import delete

        await session.execute(delete(Account).where(Account.workspace_id == family_id, Account.name != "Family card"))
        await session.commit()

    answer = await bot.select_space(TELEGRAM_USER, family_id.hex)

    assert answer == "Пространство: Family\nСчёт: Family card · KZT"
    async with test_sessionmaker() as session:
        identity = await session.get(TelegramIdentity, (await _identity_id(session)))
        assert identity.default_workspace_id == family_id
        account = await session.get(Account, identity.default_account_id)
        assert account.workspace_id == family_id
    help_text = await bot.help_text(TELEGRAM_USER)
    assert "пространство «Family», счёт «Family card · KZT»" in help_text


async def test_switching_to_a_space_with_several_accounts_asks_to_pick_one(bot, test_sessionmaker):
    _, _, family_id = await _linked_owner(test_sessionmaker)
    async with test_sessionmaker() as session:
        session.add(Account(workspace_id=family_id, name="Family cash", type=AccountType.CASH, currency="KZT"))
        await session.commit()

    answer = await bot.select_space(TELEGRAM_USER, family_id.hex)

    assert answer == "Пространство: Family\nВыберите счёт командой /accounts."
    async with test_sessionmaker() as session:
        identity = await session.get(TelegramIdentity, (await _identity_id(session)))
        # The old account belonged to another space and must not be reused.
        assert identity.default_account_id is None


async def test_a_space_without_membership_cannot_be_selected(bot, test_sessionmaker):
    _, personal_id, _ = await _linked_owner(test_sessionmaker)
    stranger_id, _, _ = await _bootstrap_user(test_sessionmaker, identifier="stranger@example.com")
    async with test_sessionmaker() as session:
        foreign, _ = await create_household(session, creator_id=stranger_id, display_name="Not yours")
        await session.commit()

    assert await bot.select_space(TELEGRAM_USER, foreign.id.hex) == "Пространство недоступно"
    assert await bot.select_space(TELEGRAM_USER, "not-a-uuid") == "Пространство недоступно"
    async with test_sessionmaker() as session:
        identity = await session.get(TelegramIdentity, (await _identity_id(session)))
        assert identity.default_workspace_id == personal_id


async def test_viewer_space_is_selectable_but_says_it_is_read_only(bot, test_sessionmaker):
    user_id, _, _ = await _linked_owner(test_sessionmaker)
    owner_id, _, _ = await _bootstrap_user(test_sessionmaker, identifier="parent@example.com")
    async with test_sessionmaker() as session:
        parents, _ = await create_household(session, creator_id=owner_id, display_name="Parents")
        session.add(WorkspaceMembership(workspace_id=parents.id, user_id=user_id, role=WorkspaceRole.VIEWER))
        await session.commit()

    answer = await bot.select_space(TELEGRAM_USER, parents.id.hex)

    assert answer.startswith("Пространство: Parents")
    assert "только просмотр" in answer


async def _identity_id(session) -> UUID:
    from sqlalchemy import select

    return (await session.execute(select(TelegramIdentity.id).where(TelegramIdentity.telegram_user_id == TELEGRAM_USER))).scalar_one()
