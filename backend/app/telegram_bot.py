"""Small long-polling Telegram bot for linking and launching the Aurum Mini App."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import logging
import re
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from app.api.deps import RequestWorkspace
from app.api.routes.transactions import _apply_categorization_rule, _currency_fields
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.account import Account
from app.models.auth import TelegramIdentity, TelegramTransactionDraft
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.models.workspace import User, UserStatus, Workspace, WorkspaceMembership, WorkspaceRole
from app.services.telegram_service import consume_link_code

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
TRANSACTION_RE = re.compile(r"^([+-])\s*(\d+(?:[.,]\d{1,2})?)\s+(.{1,255})$", re.DOTALL)


def parse_quick_transaction(text: str) -> tuple[TransactionType, Decimal, str] | None:
    match = TRANSACTION_RE.fullmatch(text.strip())
    if match is None:
        return None
    try:
        amount = Decimal(match.group(2).replace(",", ".")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    description = match.group(3).strip()
    if amount <= 0 or amount >= Decimal("1000000000000") or not description:
        return None
    tx_type = TransactionType.EXPENSE if match.group(1) == "-" else TransactionType.INCOME
    return tx_type, amount, description


class TelegramBot:
    def __init__(self) -> None:
        settings = get_settings()
        self.token = settings.telegram_bot_token.get_secret_value()
        self.webapp_url = settings.telegram_webapp_url.rstrip("/")
        self.hmac_secret = settings.auth_hmac_secret.get_secret_value()
        if not self.token:
            raise RuntimeError("AURUM_TELEGRAM_BOT_TOKEN is not configured")
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    async def api(self, client: httpx.AsyncClient, method: str, payload: dict) -> dict:
        response = await client.post(f"{self.base_url}/{method}", json=payload)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API method {method} failed")
        return body

    async def send(self, client: httpx.AsyncClient, chat_id: int, text: str, *, open_app: bool = False) -> None:
        payload: dict = {"chat_id": chat_id, "text": text}
        if open_app and self.webapp_url:
            payload["reply_markup"] = {
                "inline_keyboard": [[{
                    "text": "Открыть Aurum",
                    "web_app": {"url": self.webapp_url},
                }]]
            }
        await self.api(client, "sendMessage", payload)

    async def linked_context(self, session, telegram_user_id: int):
        return (
            await session.execute(
                select(TelegramIdentity, User, WorkspaceMembership, Workspace)
                .join(User, User.id == TelegramIdentity.user_id)
                .join(
                    WorkspaceMembership,
                    (WorkspaceMembership.user_id == User.id)
                    & (WorkspaceMembership.workspace_id == TelegramIdentity.default_workspace_id),
                )
                .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
                .where(
                    TelegramIdentity.telegram_user_id == telegram_user_id,
                    User.status == UserStatus.ACTIVE,
                    WorkspaceMembership.revoked_at.is_(None),
                )
            )
        ).one_or_none()

    async def draft_from_message(self, client: httpx.AsyncClient, chat_id: int, sender_id: int, text: str) -> bool:
        parsed = parse_quick_transaction(text)
        if parsed is None:
            return False
        tx_type, amount, description = parsed
        async with AsyncSessionLocal() as session:
            linked = await self.linked_context(session, sender_id)
            if linked is None:
                await self.send(client, chat_id, "Сначала привяжите аккаунт командой /link КОД.")
                return True
            identity, user, membership, workspace = linked
            if membership.role == WorkspaceRole.VIEWER:
                await self.send(client, chat_id, "В этой рабочей области у вас доступ только для просмотра.")
                return True
            account = (
                await session.execute(
                    select(Account)
                    .where(Account.workspace_id == workspace.id, Account.is_archived.is_(False))
                    .order_by(Account.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if account is None:
                await self.send(client, chat_id, "Сначала создайте активный счёт в Aurum.", open_app=True)
                return True
            draft = TelegramTransactionDraft(
                identity_id=identity.id,
                user_id=user.id,
                workspace_id=workspace.id,
                account_id=account.id,
                transaction_type=tx_type.value,
                amount=amount,
                description=description,
                transaction_date=datetime.now(UTC).date(),
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
            session.add(draft)
            await session.commit()
            await session.refresh(draft)
        kind = "Расход" if tx_type == TransactionType.EXPENSE else "Доход"
        payload = {
            "chat_id": chat_id,
            "text": f"{kind}: {amount} {account.currency}\n{description}\nСчёт: {account.name}\n\nЗаписать транзакцию?",
            "reply_markup": {"inline_keyboard": [[
                {"text": "✅ Записать", "callback_data": f"tx:{draft.id.hex}:ok"},
                {"text": "Отмена", "callback_data": f"tx:{draft.id.hex}:no"},
            ]]},
        }
        await self.api(client, "sendMessage", payload)
        return True

    async def handle_callback(self, client: httpx.AsyncClient, callback: dict) -> None:
        callback_id = callback.get("id")
        sender = callback.get("from") or {}
        data = str(callback.get("data") or "")
        match = re.fullmatch(r"tx:([0-9a-f]{32}):(ok|no)", data)
        if not isinstance(callback_id, str) or not isinstance(sender.get("id"), int) or match is None:
            return
        answer = "Черновик уже недоступен"
        async with AsyncSessionLocal() as session:
            try:
                draft_id = UUID(hex=match.group(1))
                row = (
                    await session.execute(
                        select(TelegramTransactionDraft, TelegramIdentity, User, WorkspaceMembership, Workspace)
                        .join(TelegramIdentity, TelegramIdentity.id == TelegramTransactionDraft.identity_id)
                        .join(User, User.id == TelegramTransactionDraft.user_id)
                        .join(Workspace, Workspace.id == TelegramTransactionDraft.workspace_id)
                        .join(
                            WorkspaceMembership,
                            (WorkspaceMembership.user_id == User.id)
                            & (WorkspaceMembership.workspace_id == Workspace.id),
                        )
                        .where(
                            TelegramTransactionDraft.id == draft_id,
                            TelegramIdentity.telegram_user_id == sender["id"],
                            TelegramTransactionDraft.consumed_at.is_(None),
                            TelegramTransactionDraft.expires_at > datetime.now(UTC),
                            User.status == UserStatus.ACTIVE,
                            WorkspaceMembership.revoked_at.is_(None),
                        )
                        .with_for_update()
                    )
                ).one_or_none()
                if row is not None:
                    draft, _identity, user, membership, workspace = row
                    draft.consumed_at = datetime.now(UTC)
                    if match.group(2) == "no":
                        answer = "Отменено"
                    elif membership.role == WorkspaceRole.VIEWER:
                        answer = "Нет права на запись"
                    else:
                        context = RequestWorkspace(user=user, workspace=workspace, membership=membership)
                        fields = {
                            "account_id": draft.account_id,
                            "category_id": None,
                            "transfer_account_id": None,
                            "type": TransactionType(draft.transaction_type),
                            "amount": draft.amount,
                            "description": draft.description,
                            "merchant": None,
                            "notes": "Добавлено через Telegram",
                            "date": draft.transaction_date,
                        }
                        fields = await _currency_fields(session, fields, context)
                        await _apply_categorization_rule(session, fields, context)
                        transaction = Transaction(
                            **fields,
                            workspace_id=workspace.id,
                            author_user_id=user.id,
                        )
                        session.add(transaction)
                        await session.flush()
                        answer = f"Записано: транзакция #{transaction.id}"
                    await session.commit()
            except (HTTPException, ValueError):
                await session.rollback()
                answer = "Не удалось записать. Проверьте счёт и курс валюты в Aurum."
        await self.api(client, "answerCallbackQuery", {"callback_query_id": callback_id, "text": answer})
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        if isinstance(chat.get("id"), int) and isinstance(message.get("message_id"), int):
            await self.api(client, "editMessageText", {
                "chat_id": chat["id"],
                "message_id": message["message_id"],
                "text": answer,
            })

    async def handle_message(self, client: httpx.AsyncClient, message: dict) -> None:
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        text = str(message.get("text") or "").strip()
        if chat.get("type") != "private" or not isinstance(sender.get("id"), int):
            return
        chat_id = chat.get("id")
        if not isinstance(chat_id, int):
            return
        if text.lower().startswith("/link "):
            code = text.split(maxsplit=1)[1]
            async with AsyncSessionLocal() as session:
                identity = await consume_link_code(
                    session,
                    code=code,
                    telegram_user_id=sender["id"],
                    telegram_username=sender.get("username"),
                    hmac_secret=self.hmac_secret,
                )
                if identity is None:
                    await session.rollback()
                    await self.send(client, chat_id, "Код неверный или уже истёк. Создайте новый код в настройках Aurum.")
                    return
                await session.commit()
            await self.send(client, chat_id, "Telegram привязан. Теперь Aurum открывается без дополнительного пароля.", open_app=True)
            return
        if await self.draft_from_message(client, chat_id, sender["id"], text):
            return
        await self.send(
            client,
            chat_id,
            "Быстрый ввод: отправьте «-2500 кофе» для расхода или «+500000 зарплата» для дохода.\n\nЧтобы привязать аккаунт: откройте Настройки → Telegram в Aurum, создайте код и отправьте сюда /link КОД.",
            open_app=True,
        )

    async def run(self) -> None:
        offset = 0
        timeout = httpx.Timeout(40, connect=10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            while True:
                try:
                    body = await self.api(
                        client,
                        "getUpdates",
                        {"offset": offset, "timeout": 30, "allowed_updates": ["message", "callback_query"]},
                    )
                    for update in body.get("result", []):
                        offset = max(offset, int(update["update_id"]) + 1)
                        if "message" in update:
                            await self.handle_message(client, update["message"])
                        elif "callback_query" in update:
                            await self.handle_callback(client, update["callback_query"])
                except (httpx.HTTPError, RuntimeError, KeyError, ValueError):
                    # Never log the exception or request URL: Bot API URLs
                    # contain the token.
                    logger.error("Telegram polling failed; retrying")
                    await asyncio.sleep(5)


async def main() -> None:
    await TelegramBot().run()


if __name__ == "__main__":
    asyncio.run(main())
