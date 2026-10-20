from __future__ import annotations

import datetime as dt
import os
from typing import Optional
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request, status

from bot_app.application.use_cases import CloseMonthUseCase, ProcessReceiptUseCase
from bot_app.infrastructure.gemini_ocr import GeminiReceiptRecognizer
from bot_app.infrastructure.repository import PostgresReceiptRepository
from bot_app.infrastructure.table_formatter import TelegramHtmlTableFormatter
from bot_app.infrastructure.telegram_gateway import AiogramBudgetMessenger
from bot_app.presentation.handlers import build_receipt_router

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]
TARGET_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
RECEIPTS_THREAD_ID = int(os.environ["RECEIPTS_THREAD_ID"])
BUDGET_THREAD_ID = int(os.environ["BUDGET_THREAD_ID"])
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
CRON_SECRET = os.environ.get("CRON_SECRET", "")

# Сборка зависимостей (Dependency Injection / Composition Root)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

repository = PostgresReceiptRepository(dsn=DATABASE_URL)
recognizer = GeminiReceiptRecognizer(api_key=GEMINI_API_KEY, model_name="gemini-2.5-flash")
formatter = TelegramHtmlTableFormatter(currency_symbol=os.environ.get("CURRENCY_SYMBOL", "₽"))
messenger = AiogramBudgetMessenger(bot=bot, chat_id=TARGET_CHAT_ID, budget_thread_id=BUDGET_THREAD_ID)

process_receipt_uc = ProcessReceiptUseCase(
    recognizer=recognizer,
    repository=repository,
    formatter=formatter,
    messenger=messenger,
)
close_month_uc = CloseMonthUseCase(
    reader_repo=repository,
    writer_repo=repository,
    formatter=formatter,
    messenger=messenger,
)

dp.include_router(
    build_receipt_router(
        process_receipt_uc=process_receipt_uc,
        close_month_uc=close_month_uc,
        target_chat_id=TARGET_CHAT_ID,
        receipts_thread_id=RECEIPTS_THREAD_ID,
    )
)

app = FastAPI()


@app.post("/api/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
) -> dict:
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Forbidden")

    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot=bot, update=update)
    return {"ok": True}


@app.get("/api/cron/close-month")
async def monthly_cron(authorization: Optional[str] = Header(default=None)) -> dict:
    """Вызывается автоматически Vercel Cron 1-го числа каждого месяца."""
    if CRON_SECRET and authorization != f"Bearer {CRON_SECRET}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    today = dt.datetime.now(dt.timezone.utc).date()
    prev_month_last_day = today.replace(day=1) - dt.timedelta(days=1)
    month_key = prev_month_last_day.strftime("%Y-%m")

    summary = await close_month_uc.execute(month_key=month_key)
    return {
        "month": month_key,
        "consolidated": summary is not None,
        "receipts_count": len(summary.receipts) if summary else 0,
        "grand_total": str(summary.grand_total) if summary else "0.00",
    }