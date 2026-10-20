from __future__ import annotations

import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from bot_app.domain.entities import Receipt, ReceiptItem
from bot_app.domain.interfaces import IReceiptRecognizer


class _GeminiReceiptItemSchema(BaseModel):
    name: str = Field(description="Название продукта или товара из чека")
    quantity: float = Field(default=1.0, description="Количество или вес")
    unit_price: float = Field(description="Цена за единицу")
    total_price: float = Field(description="Итоговая стоимость позиции по чеку")


class _GeminiReceiptSchema(BaseModel):
    store_name: str = Field(description="Название магазина (или 'Магазин', если не читается)")
    receipt_date_iso: Optional[str] = Field(
        default=None,
        description="Дата покупки в формате YYYY-MM-DD, если видна на чеке",
    )
    items: List[_GeminiReceiptItemSchema] = Field(description="Все товарные позиции чека")
    total_amount: float = Field(description="Итоговая сумма чека")


class GeminiReceiptRecognizer(IReceiptRecognizer):
    """Адаптер распознавания кассовых чеков через официальный SDK google-genai."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    async def recognize_receipt(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> Receipt:
        prompt = (
            "Распознай кассовый чек на изображении. Извлеки название магазина, "
            "дату чека, список всех купленных товаров (название, количество, цена, стоимость позиции) "
            "и общую итоговую сумму чека."
        )

        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_GeminiReceiptSchema,
                temperature=0.1,
            ),
        )

        parsed = _GeminiReceiptSchema.model_validate_json(response.text)
        now = dt.datetime.now(dt.timezone.utc)
        purchased_at = now
        if parsed.receipt_date_iso:
            try:
                d = dt.date.fromisoformat(parsed.receipt_date_iso)
                purchased_at = dt.datetime.combine(d, now.timetz(), tzinfo=dt.timezone.utc)
            except ValueError:
                purchased_at = now

        items = [
            ReceiptItem(
                name=i.name.strip(),
                quantity=Decimal(str(i.quantity)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                unit_price=Decimal(str(i.unit_price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                total_price=Decimal(str(i.total_price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            )
            for i in parsed.items
        ]

        total = Decimal(str(parsed.total_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total <= Decimal("0.00") and items:
            total = sum((item.total_price for item in items), Decimal("0.00"))

        return Receipt(
            store_name=parsed.store_name.strip() or "Магазин",
            purchased_at=purchased_at,
            items=items,
            total_amount=total,
            month_key=purchased_at.strftime("%Y-%m"),
        )