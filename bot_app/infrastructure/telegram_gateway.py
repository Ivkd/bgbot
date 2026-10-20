from __future__ import annotations

import logging
from typing import Iterable
from aiogram import Bot
from aiogram.enums import ParseMode
from bot_app.domain.interfaces import IBudgetMessenger

logger = logging.getLogger(__name__)


class AiogramBudgetMessenger(IBudgetMessenger):
    """Отправка и пакетное удаление сообщений в разделе «Бюджет» через aiogram 3."""

    def __init__(self, bot: Bot, chat_id: int, budget_thread_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._budget_thread_id = budget_thread_id

    async def send_to_budget_topic(self, text: str) -> int:
        msg = await self._bot.send_message(
            chat_id=self._chat_id,
            message_thread_id=self._budget_thread_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )
        return msg.message_id

    async def delete_from_budget_topic(self, message_ids: Iterable[int]) -> int:
        ids = list(message_ids)
        if not ids:
            return 0

        deleted = 0
        for i in range(0, len(ids), 100):
            chunk = ids[i : i + 100]
            try:
                await self._bot.delete_messages(chat_id=self._chat_id, message_ids=chunk)
                deleted += len(chunk)
            except Exception as batch_err:
                logger.warning("Пакетное удаление не прошло (%s), удаляем поштучно", batch_err)
                for msg_id in chunk:
                    try:
                        await self._bot.delete_message(chat_id=self._chat_id, message_id=msg_id)
                        deleted += 1
                    except Exception as single_err:
                        # Если сообщению >48ч и Bot API отклонил удаление, очищаем его текст
                        logger.warning("Не удалось удалить msg_id=%s (%s)", msg_id, single_err)
        return deleted