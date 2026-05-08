import asyncio
import json
from contextlib import suppress

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.kafka.producer import KafkaPortfolioEventPublisher
from app.schemas.events import OrderFilledEvent, PortfolioUpdatedEvent
from app.services.portfolio import PortfolioService


class PortfolioKafkaWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings | None = None,
        publisher: KafkaPortfolioEventPublisher | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.publisher = publisher or KafkaPortfolioEventPublisher(self.settings)
        self._consumer = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        from aiokafka import AIOKafkaConsumer

        self._consumer = AIOKafkaConsumer(
            self.settings.order_filled_topic,
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id=self.settings.kafka_consumer_group,
            enable_auto_commit=False,
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
        )
        await self.publisher.start()
        await self._consumer.start()
        self._task = asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        if self._consumer is not None:
            await self._consumer.stop()
        await self.publisher.stop()

    async def _consume_loop(self) -> None:
        async for message in self._consumer:
            try:
                applied = await self.handle_message(message.value)
                if applied:
                    await self._consumer.commit()
            except Exception:
                continue

    async def handle_message(self, payload: dict) -> bool:
        try:
            event = OrderFilledEvent.model_validate(payload)
        except ValidationError:
            return False

        async with self.session_factory() as session:
            service = PortfolioService(session)
            async with session.begin():
                result = await service.apply_filled_order(event)

            if not result.applied:
                return False

            snapshot = await service.get_snapshot(event.user_id)
            await self.publisher.publish_portfolio_updated(
                PortfolioUpdatedEvent(
                    event_id=f"portfolio-{event.event_id}",
                    user_id=event.user_id,
                    positions=[position.model_dump(mode="json") for position in snapshot.positions],
                    total_market_value=snapshot.total_market_value,
                    realized_pnl=snapshot.realized_pnl,
                    unrealized_pnl=snapshot.unrealized_pnl,
                ),
            )
            return True
