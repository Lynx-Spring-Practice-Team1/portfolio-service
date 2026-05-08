from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderFilledEvent(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1, max_length=32)
    side: OrderSide
    quantity: Decimal = Field(gt=Decimal("0"))
    price: Decimal = Field(gt=Decimal("0"))
    filled_at: datetime

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("side", mode="before")
    @classmethod
    def normalize_side(cls, value: str) -> str:
        return value.upper() if isinstance(value, str) else value


class PortfolioUpdatedEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"portfolio-{uuid4()}")
    user_id: str
    positions: list[dict]
    total_market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
