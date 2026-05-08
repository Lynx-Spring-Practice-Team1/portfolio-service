from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.events import OrderFilledEvent


def test_order_filled_event_normalizes_symbol_and_side(filled_event) -> None:
    event = filled_event("fill-1", "buy", "1", "10", symbol="msft")

    assert event.symbol == "MSFT"
    assert event.side == "BUY"


def test_order_filled_event_rejects_negative_quantity(filled_event) -> None:
    with pytest.raises(ValidationError):
        OrderFilledEvent(
            event_id="fill-2",
            order_id="order-2",
            user_id="user-123",
            symbol="AAPL",
            side="BUY",
            quantity=Decimal("-1"),
            price=Decimal("10"),
            filled_at=filled_event("seed", "BUY", "1", "10").filled_at,
        )
