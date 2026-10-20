from __future__ import annotations

import datetime as dt
import html
import io
import logging
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot_app.application.use_cases import CloseMonthUseCase, ProcessReceiptUseCase

logger = logging.getLogger(__name__)


def build_receipt_router(
    process_receipt_uc: ProcessReceiptUseCase,
    close_month_uc: CloseMonthUseCase,
    target_chat_id: int,
    receipts_thread_id: int,
) -> Router:
    router = Router(name="receipt_budget_router")

    @router.message(
        F.chat.id == target_chat_id,
        F.message_thread_id == receipts_thread_id,
        F.photo,
    )
    async def on_receipt_photo(message: Message, bot: Bot) -> None:
        """Слушает раздел «Чеки», распознаёт фото чека и пишет таблицу в «Бюджет»."""
        photo = message.photo[-1]
        buf = io.BytesIO()
        await bot.download(photo, destination=buf)

        try:
            receipt = await process_receipt_uc.execute(
                image_bytes=buf.getvalue(),
                source_message_id=message.message_id,
                mime_type="image/jpeg",
            )
            await message.reply(
                f"✅ Чек <b>{html.escape(receipt.store_name)}</b> "
                f"на сумму <b>{receipt.total_amount:.2f}</b> записан в раздел «Бюджет»."
            )
        except Exception as err:
            logger.exception("Ошибка обработки чека")
            await message.reply(f"⚠️ Ошибка при разборе чека: {html.escape(str(err))}")

    @router.message(Command("close_month"), F.chat.id == target_chat_id)
    async def on_manual_close_month(message: Message) -> None:
        """Позволяет вручную закрыть месяц командой /close_month 2026-10."""
        parts = (message.text or "").split(maxsplit=1)
        month_key = (
            parts[1].strip()
            if len(parts) > 1
            else dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")
        )
        summary = await close_month_uc.execute(month_key)
        if summary is None:
            await message.reply(f"ℹ️ За <b>{html.escape(month_key)}</b> нет открытых чеков.")
        else:
            await message.reply(
                f"📊 Месяц <b>{html.escape(month_key)}</b> закрыт! "
                f"Объединено чеков: <b>{len(summary.receipts)}</b> на сумму <b>{summary.grand_total:.2f}</b>."
            )

    return router