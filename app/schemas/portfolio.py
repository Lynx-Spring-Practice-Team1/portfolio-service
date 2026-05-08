from decimal import Decimal

from pydantic import BaseModel


class CashBalance(BaseModel):
    currency: str = "USD"
    available: Decimal = Decimal("0")
    reserved: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        return self.available + self.reserved


class PositionSnapshot(BaseModel):
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    latest_price: Decimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal


class PortfolioSnapshot(BaseModel):
    user_id: str
    cash: CashBalance
    positions: list[PositionSnapshot]
    total_market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_equity: Decimal
