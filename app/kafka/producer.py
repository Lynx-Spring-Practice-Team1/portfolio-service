from app.core.config import Settings, get_settings
from app.schemas.events import PortfolioUpdatedEvent


class KafkaPortfolioEventPublisher:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._producer = None

    async def start(self) -> None:
        from aiokafka import AIOKafkaProducer

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            value_serializer=lambda event: event.model_dump_json().encode("utf-8"),
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()

    async def publish_portfolio_updated(self, event: PortfolioUpdatedEvent) -> None:
        if self._producer is None:
            raise RuntimeError("Kafka producer is not started")

        await self._producer.send_and_wait(self.settings.portfolio_updated_topic, event)
