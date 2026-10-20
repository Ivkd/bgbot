from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path
from typing import Optional

# Гарантируем, что корень репозитория доступен для импорта пакета bot_app на Vercel
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

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

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# Поддерживаем как DATABASE_URL, так и стандартную переменную POSTGRES_URL от интеграции Vercel
DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("POSTGRES_URL")
    or os.environ.get("POSTGRES_PRISMA_URL")
    or ""
).strip()

TARGET_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0").strip() or "0")
RECEIPTS_THREAD_ID = int(os.environ.get("RECEIPTS_THREAD_ID", "0").strip() or "0")
BUDGET_THREAD_ID = int(os.environ.get("BUDGET_THREAD_ID", "0").strip() or "0")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
CRON_SECRET = os.environ.get("CRON_SECRET", "").strip()

app = FastAPI(title="Receipt Budget Bot")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) if BOT_TOKEN else None
dp = Dispatcher()

if bot and GEMINI_API_KEY and DATABASE_URL:
    # Приводим схему postgres:// к postgresql:// для совместимости с asyncpg
    normalized_dsn = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    repository = PostgresReceiptRepository(dsn=normalized_dsn)
    recognizer = GeminiReceiptRecognizer(api_key=GEMINI_API_KEY, model_name="gemini-2.5-flash")
    formatter = TelegramHtmlTableFormatter(currency_symbol=os.environ.get("CURRENCY_SYMBOL", "₽"))
    messenger = AiogramBudgetMessenger(
        bot=bot,
        chat_id=TARGET_CHAT_ID,
        budget_thread_id=BUDGET_THREAD_ID,
    )

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
else:
    close_month_uc = None


@app.get("/")
@app.get("/api/health")
async def healthcheck() -> dict:
    """Показывает в браузере, какие переменные окружения успешно подгрузились."""
    return {
        "status": "ok",
        "bot_token_configured": bool(BOT_TOKEN),
        "gemini_key_configured": bool(GEMINI_API_KEY),
        "database_configured": bool(DATABASE_URL),
        "target_chat_id": TARGET_CHAT_ID,
        "receipts_thread_id": RECEIPTS_THREAD_ID,
        "budget_thread_id": BUDGET_THREAD_ID,
    }


@app.get("/api/setup-webhook")
async def setup_webhook(request: Request) -> dict:
    """Привязывает вебхук Telegram простым открытием этой ссылки в браузере."""
    if not bot:
        raise HTTPException(status_code=500, detail="TELEGRAM_BOT_TOKEN не задан в Environment Variables")

    webhook_url = f"https://{request.headers.get('host')}/api/webhook"
    await bot.set_webhook(
        url=webhook_url,
        secret_token=WEBHOOK_SECRET if WEBHOOK_SECRET else None,
        drop_pending_updates=True,
    )
    return {"ok": True, "webhook_url": webhook_url, "secret_token_used": bool(WEBHOOK_SECRET)}


@app.post("/api/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
) -> dict:
    if not bot:
        raise HTTPException(status_code=500, detail="Bot is not configured")
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret token")

    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot=bot, update=update)
    return {"ok": True}


@app.get("/api/cron/close-month")
async def monthly_cron(authorization: Optional[str] = Header(default=None)) -> dict:
    if CRON_SECRET and authorization != f"Bearer {CRON_SECRET}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    if not close_month_uc:
        raise HTTPException(status_code=500, detail="Use case is not initialized")

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