from __future__ import annotations

from decimal import Decimal
from typing import Optional
from bot_app.domain.entities import MonthlySummary, Receipt
from bot_app.domain.interfaces import (
    IBudgetMessenger,
    IReceiptReaderRepository,
    IReceiptRecognizer,
    IReceiptWriterRepository,
    ITableFormatter,
)


class ProcessReceiptUseCase:
    """
    Сценарий обработки нового фото чека:
    1. Распознаёт товары и цены через ИИ.
    2. Формирует таблицу покупок и общей суммы.
    3. Отправляет таблицу в раздел «Бюджет» и сохраняет message_id в БД.
    """

    def __init__(
        self,
        recognizer: IReceiptRecognizer,
        repository: IReceiptWriterRepository,
        formatter: ITableFormatter,
        messenger: IBudgetMessenger,
    ) -> None:
        self._recognizer = recognizer
        self._repository = repository
        self._formatter = formatter
        self._messenger = messenger

    async def execute(
        self,
        image_bytes: bytes,
        source_message_id: int,
        mime_type: str = "image/jpeg",
    ) -> Receipt:
        receipt = await self._recognizer.recognize_receipt(
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
        receipt.source_message_id = source_message_id

        table_message = self._formatter.format_single_receipt(receipt)
        budget_msg_id = await self._messenger.send_to_budget_topic(table_message)
        receipt.budget_message_id = budget_msg_id

        return await self._repository.save_receipt(receipt)


class CloseMonthUseCase:
    """
    Сценарий закрытия месяца:
    1. Получает все чеки за указанный месяц (YYYY-MM).
    2. Удаляет все промежуточные сообщения этого месяца из раздела «Бюджет».
    3. Публикует одним сообщением сводную таблицу каждого чека и общую сумму за месяц.
    """

    def __init__(
        self,
        reader_repo: IReceiptReaderRepository,
        writer_repo: IReceiptWriterRepository,
        formatter: ITableFormatter,
        messenger: IBudgetMessenger,
    ) -> None:
        self._reader_repo = reader_repo
        self._writer_repo = writer_repo
        self._formatter = formatter
        self._messenger = messenger

    async def execute(self, month_key: str) -> Optional[MonthlySummary]:
        receipts = await self._reader_repo.get_unconsolidated_by_month(month_key)
        if not receipts:
            return None

        message_ids = [r.budget_message_id for r in receipts if r.budget_message_id is not None]
        if message_ids:
            await self._messenger.delete_from_budget_topic(message_ids)

        grand_total = sum((r.total_amount for r in receipts), Decimal("0.00"))
        summary = MonthlySummary(
            month_key=month_key,
            receipts=receipts,
            grand_total=grand_total,
        )

        summary_table = self._formatter.format_monthly_summary(summary)
        await self._messenger.send_to_budget_topic(summary_table)
        await self._writer_repo.mark_month_consolidated(month_key)
        return summary