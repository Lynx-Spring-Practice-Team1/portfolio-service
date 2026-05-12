import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from decimal import Decimal

from fastapi import FastAPI
from sqlalchemy import select

from app.api.routes import router
from app.core.config import get_settings
from app.db.session import async_session_factory, engine
from app.kafka.consumer import PortfolioKafkaWorker
from app.models import Base, Position
from app.services.pricing import MarketWebsocketPriceStreamer


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    worker: PortfolioKafkaWorker | None = None
    price_streamer: MarketWebsocketPriceStreamer | None = None
    price_streamer_task: asyncio.Task | None = None

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if settings.kafka_enabled:
        worker = PortfolioKafkaWorker(async_session_factory, settings)
        await worker.start()

    if settings.market_ws_enabled:
        price_streamer = MarketWebsocketPriceStreamer(
            async_session_factory,
            get_position_symbols,
            settings,
        )
        price_streamer_task = asyncio.create_task(price_streamer.run_forever())

    try:
        yield
    finally:
        if price_streamer is not None:
            await price_streamer.stop()
        if price_streamer_task is not None:
            price_streamer_task.cancel()
            with suppress(asyncio.CancelledError):
                await price_streamer_task
        if worker is not None:
            await worker.stop()


async def get_position_symbols() -> list[str]:
    async with async_session_factory() as session:
        statement = select(Position.symbol).where(Position.quantity != Decimal("0"))
        result = await session.scalars(statement)
        return list(result)


app = FastAPI(title="Portfolio Service", version="0.1.0", lifespan=lifespan)
app.include_router(router)
