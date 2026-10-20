from __future__ import annotations

import asyncio
import datetime as dt
import json
import sqlite3
from decimal import Decimal
from typing import List, Sequence
import asyncpg

from bot_app.domain.entities import Receipt, ReceiptItem
from bot_app.domain.interfaces import IReceiptRepository


class PostgresReceiptRepository(IReceiptRepository):
    """Репозиторий PostgreSQL для бессерверного окружения Vercel."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    async def _connect(self) -> asyncpg.Connection:
        conn = await asyncpg.connect(self._dsn)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS receipts (
                id SERIAL PRIMARY KEY,
                store_name TEXT NOT NULL,
                purchased_at TIMESTAMPTZ NOT NULL,
                month_key TEXT NOT NULL,
                total_amount NUMERIC(12, 2) NOT NULL,
                items_json JSONB NOT NULL,
                source_message_id BIGINT,
                budget_message_id BIGINT,
                is_consolidated BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
        return conn

    async def save_receipt(self, receipt: Receipt) -> Receipt:
        conn = await self._connect()
        try:
            items_data = json.dumps(
                [
                    {
                        "name": i.name,
                        "quantity": str(i.quantity),
                        "unit_price": str(i.unit_price),
                        "total_price": str(i.total_price),
                    }
                    for i in receipt.items
                ],
                ensure_ascii=False,
            )
            row_id = await conn.fetchval(
                """
                INSERT INTO receipts (
                    store_name, purchased_at, month_key, total_amount,
                    items_json, source_message_id, budget_message_id, is_consolidated
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)
                RETURNING id
                """,
                receipt.store_name,
                receipt.purchased_at,
                receipt.month_key,
                receipt.total_amount,
                items_data,
                receipt.source_message_id,
                receipt.budget_message_id,
                receipt.is_consolidated,
            )
            receipt.id = int(row_id)
            return receipt
        finally:
            await conn.close()

    async def get_unconsolidated_by_month(self, month_key: str) -> Sequence[Receipt]:
        conn = await self._connect()
        try:
            rows = await conn.fetch(
                """
                SELECT * FROM receipts
                WHERE month_key = $1 AND is_consolidated = FALSE
                ORDER BY purchased_at ASC, id ASC
                """,
                month_key,
            )
            receipts: List[Receipt] = []
            for row in rows:
                items = [
                    ReceiptItem(
                        name=item["name"],
                        quantity=Decimal(item["quantity"]),
                        unit_price=Decimal(item["unit_price"]),
                        total_price=Decimal(item["total_price"]),
                    )
                    for item in json.loads(row["items_json"])
                ]
                receipts.append(
                    Receipt(
                        id=row["id"],
                        store_name=row["store_name"],
                        purchased_at=row["purchased_at"],
                        month_key=row["month_key"],
                        total_amount=Decimal(str(row["total_amount"])),
                        items=items,
                        source_message_id=row["source_message_id"],
                        budget_message_id=row["budget_message_id"],
                        is_consolidated=row["is_consolidated"],
                    )
                )
            return receipts
        finally:
            await conn.close()

    async def mark_month_consolidated(self, month_key: str) -> None:
        conn = await self._connect()
        try:
            await conn.execute(
                "UPDATE receipts SET is_consolidated = TRUE WHERE month_key = $1 AND is_consolidated = FALSE",
                month_key,
            )
        finally:
            await conn.close()