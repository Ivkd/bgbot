from __future__ import annotations

from typing import Iterable, Protocol, Sequence
from bot_app.domain.entities import MonthlySummary, Receipt


class IReceiptRecognizer(Protocol):
    """Абстракция ИИ-сервиса распознавания фотографии чека."""

    async def recognize_receipt(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> Receipt:
        ...


class IReceiptWriterRepository(Protocol):
    """Контракт записи чеков в хранилище (ISP)."""

    async def save_receipt(self, receipt: Receipt) -> Receipt:
        ...

    async def mark_month_consolidated(self, month_key: str) -> None:
        ...


class IReceiptReaderRepository(Protocol):
    """Контракт чтения чеков из хранилища (ISP)."""

    async def get_unconsolidated_by_month(self, month_key: str) -> Sequence[Receipt]:
        ...


class IReceiptRepository(IReceiptWriterRepository, IReceiptReaderRepository, Protocol):
    """Полный интерфейс репозитория чеков."""
    pass


class ITableFormatter(Protocol):
    """Абстракция генератора таблиц для сообщений в разделе «Бюджет»."""

    def format_single_receipt(self, receipt: Receipt) -> str:
        ...

    def format_monthly_summary(self, summary: MonthlySummary) -> str:
        ...


class IBudgetMessenger(Protocol):
    """Абстракция работы с разделом «Бюджет» в Telegram."""

    async def send_to_budget_topic(self, text: str) -> int:
        ...

    async def delete_from_budget_topic(self, message_ids: Iterable[int]) -> int:
        ...