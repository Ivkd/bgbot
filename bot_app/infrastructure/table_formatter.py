from __future__ import annotations

import html
from bot_app.domain.entities import MonthlySummary, Receipt
from bot_app.domain.interfaces import ITableFormatter


class TelegramHtmlTableFormatter(ITableFormatter):
    """Генератор выровненных моноширинных таблиц (<pre>) для Telegram."""

    def __init__(self, currency_symbol: str = "₽") -> None:
        self._currency = currency_symbol

    @staticmethod
    def _clip(text: str, width: int) -> str:
        clean = text.replace("\n", " ").strip()
        return clean if len(clean) <= width else clean[: width - 1] + "…"

    def format_single_receipt(self, receipt: Receipt) -> str:
        date_str = receipt.purchased_at.strftime("%d.%m.%Y %H:%M")
        header = f"{'Продукт':<20} | {'Кол-во':>6} | {'Стоимость':>10}"
        divider = "-" * len(header)
        rows = [header, divider]

        for item in receipt.items:
            name_col = self._clip(item.name, 20)
            qty_col = f"{item.quantity:g}"
            cost_col = f"{item.total_price:.2f}"
            rows.append(f"{name_col:<20} | {qty_col:>6} | {cost_col:>10}")

        rows.append(divider)
        rows.append(f"{'ИТОГО ПО ЧЕКУ':<29} | {receipt.total_amount:>10.2f}")

        table_html = html.escape("\n".join(rows))
        return (
            f"🧾 <b>Чек: {html.escape(receipt.store_name)}</b> ({date_str})\n"
            f"<pre>{table_html}</pre>\n"
            f"💰 <b>Общая сумма потраченного: {receipt.total_amount:.2f} {self._currency}</b>"
        )

    def format_monthly_summary(self, summary: MonthlySummary) -> str:
        header = f"{'№':<3} | {'Дата чека':<10} | {'Магазин':<16} | {'Потрачено':>10}"
        divider = "-" * len(header)
        rows = [header, divider]

        for idx, receipt in enumerate(summary.receipts, start=1):
            date_col = receipt.purchased_at.strftime("%d.%m.%Y")
            store_col = self._clip(receipt.store_name, 16)
            total_col = f"{receipt.total_amount:.2f}"
            rows.append(f"{idx:<3} | {date_col:<10} | {store_col:<16} | {total_col:>10}")

        rows.append(divider)
        rows.append(f"{'ИТОГО ЗА МЕСЯЦ':<35} | {summary.grand_total:>10.2f}")

        table_html = html.escape("\n".join(rows))
        return (
            f"📊 <b>Сводная таблица чеков за {html.escape(summary.month_key)}</b>\n"
            f"Всего чеков за месяц: <b>{len(summary.receipts)}</b>\n"
            f"<pre>{table_html}</pre>\n"
            f"💳 <b>Общая сумма за месяц: {summary.grand_total:.2f} {self._currency}</b>"
        )