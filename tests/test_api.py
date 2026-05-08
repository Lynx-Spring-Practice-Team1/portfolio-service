from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_session
from app.main import app
from app.models import Position
from app.schemas.portfolio import CashBalance
from app.services.pricing import PriceService
from app.services.wallet import WalletClient


@pytest.mark.asyncio
async def test_get_portfolio_requires_user_header(session) -> None:
    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/portfolio")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/portfolio", "/api/portfolio"])
async def test_get_portfolio_returns_snapshot_for_supported_paths(
    session,
    monkeypatch,
    path: str,
) -> None:
    session.add(
        Position(
            user_id="user-123",
            symbol="MSFT",
            quantity=Decimal("3"),
            average_cost=Decimal("25"),
            realized_pnl=Decimal("4"),
        ),
    )
    await session.commit()

    async def fake_prices(self, symbols):
        return {"MSFT": Decimal("25")}

    async def fake_cash(self, user_id):
        return CashBalance(available=Decimal("1000"), reserved=Decimal("50"))

    monkeypatch.setattr(PriceService, "get_latest_prices", fake_prices)
    monkeypatch.setattr(WalletClient, "get_cash_balance", fake_cash)

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(path, headers={"X-User-Id": "user-123"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == "user-123"
    assert payload["positions"][0]["symbol"] == "MSFT"
    assert payload["positions"][0]["market_value"] == "75.000000"
    assert payload["realized_pnl"] == "4.000000"
