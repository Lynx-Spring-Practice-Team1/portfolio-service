from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PortfolioEventError, Position, TradeHistory
from app.schemas.events import OrderFilledEvent, OrderSide
from app.schemas.portfolio import CashBalance, PortfolioSnapshot, PositionSnapshot
from app.services.pricing import PriceService
from app.services.wallet import WalletClient

DECIMAL_QUANT = Decimal("0.000001")


@dataclass(frozen=True)
class FillApplicationResult:
    applied: bool
    duplicate: bool = False
    invalid: bool = False
    reason: str | None = None


class PortfolioService:
    def __init__(
        self,
        session: AsyncSession,
        price_service: PriceService | None = None,
        wallet_client: WalletClient | None = None,
    ) -> None:
        self.session = session
        self.price_service = price_service or PriceService(session)
        self.wallet_client = wallet_client or WalletClient()

    async def apply_filled_order(self, fill: OrderFilledEvent) -> FillApplicationResult:
        if await self._is_duplicate(fill.event_id):
            return FillApplicationResult(applied=False, duplicate=True, reason="duplicate_event")

        position = await self._get_position_for_update(fill.user_id, fill.symbol)
        if fill.side is OrderSide.SELL and (
            position is None or Decimal(position.quantity) < fill.quantity
        ):
            await self._record_invalid_event(fill, "sell_quantity_exceeds_position")
            return FillApplicationResult(
                applied=False,
                invalid=True,
                reason="sell_quantity_exceeds_position",
            )

        if position is None:
            position = Position(
                user_id=fill.user_id,
                symbol=fill.symbol,
                quantity=Decimal("0"),
                average_cost=Decimal("0"),
                realized_pnl=Decimal("0"),
            )
            self.session.add(position)

        realized_delta = Decimal("0")
        if fill.side is OrderSide.BUY:
            self._apply_buy(position, fill.quantity, fill.price)
        else:
            realized_delta = self._apply_sell(position, fill.quantity, fill.price)

        self.session.add(
            TradeHistory(
                event_id=fill.event_id,
                order_id=fill.order_id,
                user_id=fill.user_id,
                symbol=fill.symbol,
                side=fill.side.value,
                quantity=fill.quantity,
                price=fill.price,
                realized_pnl=realized_delta,
                filled_at=fill.filled_at,
            ),
        )
        await self.session.flush()
        return FillApplicationResult(applied=True)

    async def get_snapshot(self, user_id: str) -> PortfolioSnapshot:
        all_positions = list(
            await self.session.scalars(select(Position).where(Position.user_id == user_id)),
        )
        active_positions = [
            position for position in all_positions if Decimal(position.quantity) != 0
        ]
        latest_prices = await self.price_service.get_latest_prices(
            [position.symbol for position in active_positions],
        )
        cash = await self.wallet_client.get_cash_balance(user_id)

        position_snapshots: list[PositionSnapshot] = []
        total_market_value = Decimal("0")
        total_unrealized = Decimal("0")

        for position in active_positions:
            quantity = Decimal(position.quantity)
            average_cost = Decimal(position.average_cost)
            latest_price = latest_prices.get(position.symbol, average_cost)
            market_value = self._q(quantity * latest_price)
            unrealized_pnl = self._q((latest_price - average_cost) * quantity)

            total_market_value += market_value
            total_unrealized += unrealized_pnl
            position_snapshots.append(
                PositionSnapshot(
                    symbol=position.symbol,
                    quantity=self._q(quantity),
                    average_cost=self._q(average_cost),
                    latest_price=self._q(latest_price),
                    market_value=market_value,
                    realized_pnl=self._q(Decimal(position.realized_pnl)),
                    unrealized_pnl=unrealized_pnl,
                ),
            )

        realized_pnl = self._q(sum((Decimal(position.realized_pnl) for position in all_positions), Decimal("0")))
        total_market_value = self._q(total_market_value)
        total_unrealized = self._q(total_unrealized)
        return PortfolioSnapshot(
            user_id=user_id,
            cash=CashBalance(
                currency=cash.currency,
                available=self._q(cash.available),
                reserved=self._q(cash.reserved),
            ),
            positions=position_snapshots,
            total_market_value=total_market_value,
            realized_pnl=realized_pnl,
            unrealized_pnl=total_unrealized,
            total_equity=self._q(cash.total + total_market_value),
        )

    async def _is_duplicate(self, event_id: str) -> bool:
        existing_trade = await self.session.scalar(
            select(TradeHistory.id).where(TradeHistory.event_id == event_id),
        )
        if existing_trade is not None:
            return True

        existing_error = await self.session.scalar(
            select(PortfolioEventError.id).where(PortfolioEventError.event_id == event_id),
        )
        return existing_error is not None

    async def _get_position_for_update(self, user_id: str, symbol: str) -> Position | None:
        statement = (
            select(Position)
            .where(Position.user_id == user_id, Position.symbol == symbol)
            .with_for_update()
        )
        return await self.session.scalar(statement)

    def _apply_buy(self, position: Position, quantity: Decimal, price: Decimal) -> None:
        current_quantity = Decimal(position.quantity)
        new_quantity = current_quantity + quantity
        current_cost = current_quantity * Decimal(position.average_cost)
        added_cost = quantity * price
        position.quantity = self._q(new_quantity)
        position.average_cost = self._q((current_cost + added_cost) / new_quantity)

    def _apply_sell(self, position: Position, quantity: Decimal, price: Decimal) -> Decimal:
        current_quantity = Decimal(position.quantity)
        average_cost = Decimal(position.average_cost)
        realized_delta = self._q((price - average_cost) * quantity)
        new_quantity = current_quantity - quantity

        position.quantity = self._q(new_quantity)
        position.realized_pnl = self._q(Decimal(position.realized_pnl) + realized_delta)
        if new_quantity == 0:
            position.average_cost = Decimal("0")
        return realized_delta

    async def _record_invalid_event(self, fill: OrderFilledEvent, reason: str) -> None:
        self.session.add(
            PortfolioEventError(
                event_id=fill.event_id,
                event_type="order.filled",
                reason=reason,
                payload=fill.model_dump(mode="json"),
            ),
        )
        await self.session.flush()

    def _q(self, value: Decimal) -> Decimal:
        return value.quantize(DECIMAL_QUANT)
