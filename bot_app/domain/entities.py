from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Sequence


@dataclass(frozen=True, slots=True)
class ReceiptItem:
    """Отдельная товарная позиция в чеке."""
    name: str
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal


@dataclass(slots=True)
class Receipt:
    """Распознанный кассовый чек."""
    store_name: str
    purchased_at: dt.datetime
    items: List[ReceiptItem]
    total_amount: Decimal
    month_key: str  # Формат "YYYY-MM", например "2026-10"
    id: Optional[int] = None
    source_message_id: Optional[int] = None
    budget_message_id: Optional[int] = None
    is_consolidated: bool = False


@dataclass(frozen=True, slots=True)
class MonthlySummary:
    """Сводный отчёт по всем чекам за закрываемый месяц."""
    month_key: str
    receipts: Sequence[Receipt]
    grand_total: Decimal