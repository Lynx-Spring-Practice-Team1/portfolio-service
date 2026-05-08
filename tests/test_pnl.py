from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import PortfolioEventError, Position, TradeHistory
from app.services.portfolio import PortfolioService


@pytest.mark.asyncio
async def test_average_cost_buy_and_partial_sell(session, filled_event) -> None:
    service = PortfolioService(session)

    async with session.begin():
        await service.apply_filled_order(filled_event("fill-1", "BUY", "10", "100"))
    async with session.begin():
        await service.apply_filled_order(filled_event("fill-2", "BUY", "10", "120"))
    async with session.begin():
        await service.apply_filled_order(filled_event("fill-3", "SELL", "5", "130"))

    position = await session.scalar(select(Position).where(Position.symbol == "AAPL"))

    assert position is not None
    assert Decimal(position.quantity) == Decimal("15.00000000")
    assert Decimal(position.average_cost) == Decimal("110.00000000")
    assert Decimal(position.realized_pnl) == Decimal("100.00000000")


@pytest.mark.asyncio
async def test_full_exit_resets_average_cost(session, filled_event) -> None:
    service = PortfolioService(session)

    async with session.begin():
        await service.apply_filled_order(filled_event("fill-1", "BUY", "2", "50"))
    async with session.begin():
        await service.apply_filled_order(filled_event("fill-2", "SELL", "2", "70"))

    position = await session.scalar(select(Position).where(Position.symbol == "AAPL"))

    assert position is not None
    assert Decimal(position.quantity) == Decimal("0E-8")
    assert Decimal(position.average_cost) == Decimal("0E-8")
    assert Decimal(position.realized_pnl) == Decimal("40.00000000")


@pytest.mark.asyncio
async def test_duplicate_fill_is_ignored(session, filled_event) -> None:
    service = PortfolioService(session)
    event = filled_event("fill-1", "BUY", "10", "100")

    async with session.begin():
        first = await service.apply_filled_order(event)
    async with session.begin():
        second = await service.apply_filled_order(event)

    trades = list(await session.scalars(select(TradeHistory)))
    position = await session.scalar(select(Position).where(Position.symbol == "AAPL"))

    assert first.applied is True
    assert second.applied is False
    assert second.duplicate is True
    assert len(trades) == 1
    assert Decimal(position.quantity) == Decimal("10.00000000")


@pytest.mark.asyncio
async def test_invalid_sell_records_error_without_mutating_position(session, filled_event) -> None:
    service = PortfolioService(session)

    async with session.begin():
        result = await service.apply_filled_order(filled_event("fill-1", "SELL", "1", "100"))

    errors = list(await session.scalars(select(PortfolioEventError)))
    positions = list(await session.scalars(select(Position)))

    assert result.applied is False
    assert result.invalid is True
    assert len(errors) == 1
    assert positions == []


@pytest.mark.asyncio
async def test_snapshot_uses_latest_price_for_unrealized_pnl(
    session,
    filled_event,
    monkeypatch,
) -> None:
    service = PortfolioService(session)

    async with session.begin():
        await service.apply_filled_order(filled_event("fill-1", "BUY", "4", "25"))

    async def fake_prices(symbols):
        return {"AAPL": Decimal("30")}

    async def fake_cash(user_id):
        from app.schemas.portfolio import CashBalance

        return CashBalance(available=Decimal("10"), reserved=Decimal("5"))

    monkeypatch.setattr(service.price_service, "get_latest_prices", fake_prices)
    monkeypatch.setattr(service.wallet_client, "get_cash_balance", fake_cash)

    snapshot = await service.get_snapshot("user-123")

    assert snapshot.total_market_value == Decimal("120.000000")
    assert snapshot.unrealized_pnl == Decimal("20.000000")
    assert snapshot.total_equity == Decimal("135.000000")
