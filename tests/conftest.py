from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base
from app.schemas.events import OrderFilledEvent
from app.schemas.portfolio import CashBalance


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as test_session:
        yield test_session

    await engine.dispose()


@pytest.fixture
def filled_event():
    return make_filled_event


def make_filled_event(
    event_id: str,
    side: str,
    quantity: str,
    price: str,
    symbol: str = "AAPL",
    user_id: str = "user-123",
) -> OrderFilledEvent:
    return OrderFilledEvent(
        event_id=event_id,
        order_id=f"order-{event_id}",
        user_id=user_id,
        symbol=symbol,
        side=side,
        quantity=Decimal(quantity),
        price=Decimal(price),
        filled_at=datetime(2026, 5, 8, 10, 0, tzinfo=UTC),
    )


class FakeWalletClient:
    async def get_cash_balance(self, user_id: str) -> CashBalance:
        return CashBalance(currency="USD", available=Decimal("1000"), reserved=Decimal("50"))
