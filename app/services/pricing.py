import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.models import LatestPrice

SymbolProvider = Callable[[], Sequence[str] | Awaitable[Sequence[str]]]


class PriceService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def get_latest_prices(self, symbols: Sequence[str]) -> dict[str, Decimal]:
        normalized = sorted({symbol.upper() for symbol in symbols if symbol})
        if not normalized:
            return {}

        cached = await self._get_cached_prices(normalized)
        missing = [symbol for symbol in normalized if symbol not in cached]
        if missing:
            fetched = await self._fetch_http_prices(missing)
            if fetched:
                await self.upsert_prices(fetched, source="market-http")
                cached.update(fetched)

        return cached

    async def upsert_prices(self, prices: dict[str, Decimal], source: str) -> None:
        observed_at = datetime.now(UTC)
        for symbol, price in prices.items():
            normalized = symbol.upper()
            existing = await self.session.get(LatestPrice, normalized)
            if existing:
                existing.price = price
                existing.source = source
                existing.observed_at = observed_at
            else:
                self.session.add(
                    LatestPrice(
                        symbol=normalized,
                        price=price,
                        source=source,
                        observed_at=observed_at,
                    ),
                )
        await self.session.flush()

    async def _get_cached_prices(self, symbols: Sequence[str]) -> dict[str, Decimal]:
        ttl_cutoff = datetime.now(UTC) - timedelta(
            seconds=self.settings.price_cache_ttl_seconds,
        )
        result = await self.session.scalars(
            select(LatestPrice).where(LatestPrice.symbol.in_(symbols)),
        )
        prices: dict[str, Decimal] = {}
        for row in result:
            observed_at = row.observed_at
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=UTC)
            if observed_at >= ttl_cutoff:
                prices[row.symbol] = row.price
        return prices

    async def _fetch_http_prices(self, symbols: Sequence[str]) -> dict[str, Decimal]:
        if not self.settings.market_data_service_url:
            return {}

        url = f"{self.settings.market_data_service_url.rstrip('/')}/prices/latest"
        try:
            async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
                response = await client.get(url, params={"symbols": ",".join(symbols)})
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError:
            return {}

        return parse_price_payload(payload)


class MarketWebsocketPriceStreamer:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        symbol_provider: SymbolProvider,
        settings: Settings | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.symbol_provider = symbol_provider
        self.settings = settings or get_settings()
        self._stop = asyncio.Event()

    async def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        url = build_market_ws_url(self.settings)
        if not url:
            return

        import websockets

        while not self._stop.is_set():
            try:
                async with websockets.connect(url) as websocket:
                    await self._subscribe(websocket)
                    while not self._stop.is_set():
                        try:
                            message = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=self._resubscribe_seconds(),
                            )
                        except TimeoutError:
                            await self._subscribe(websocket)
                            continue

                        prices = self._parse_ws_message(message)
                        if prices:
                            async with self.session_factory() as session:
                                service = PriceService(session, self.settings)
                                await service.upsert_prices(prices, source="market-websocket")
                                await session.commit()
            except asyncio.CancelledError:
                raise
            except Exception:
                if not self._stop.is_set():
                    await asyncio.sleep(2)

    async def _subscribe(self, websocket: object) -> None:
        tickers = await self._tickers_to_subscribe()
        if tickers:
            await websocket.send(json.dumps(self._subscription_payload(tickers)))

    async def _tickers_to_subscribe(self) -> list[str]:
        defaults = parse_tickers(self.settings.market_ws_default_tickers)
        provided_symbols = self.symbol_provider()
        if inspect.isawaitable(provided_symbols):
            provided_symbols = await provided_symbols
        return merge_tickers(defaults, parse_tickers(provided_symbols))

    def _parse_ws_message(self, message: str | bytes) -> dict[str, Decimal]:
        try:
            payload = json.loads(message)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            return {}
        return parse_price_payload(payload)

    def _resubscribe_seconds(self) -> int:
        return max(1, self.settings.market_ws_resubscribe_seconds)

    @staticmethod
    def _subscription_payload(tickers: Sequence[str]) -> dict[str, object]:
        return {
            "type": "SUBSCRIBE",
            "payload": {
                "channel": "PRICE_FEED",
                "tickers": list(tickers),
            },
        }


def build_market_ws_url(settings: Settings) -> str | None:
    if not settings.market_ws_url:
        return None

    url_parts = urlsplit(settings.market_ws_url)
    query = dict(parse_qsl(url_parts.query, keep_blank_values=True))
    if settings.market_ws_api_key:
        query["api_key"] = settings.market_ws_api_key
    if settings.market_ws_api_secret:
        query["api_secret"] = settings.market_ws_api_secret
    return urlunsplit(url_parts._replace(query=urlencode(query)))


def parse_tickers(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []

    raw_items: Sequence[str]
    if isinstance(value, str):
        raw_items = value.split(",")
    else:
        raw_items = value

    tickers: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        ticker = str(raw_item).strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tickers


def merge_tickers(*ticker_groups: Sequence[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in ticker_groups:
        for ticker in group:
            normalized = ticker.strip().upper()
            if normalized and normalized not in seen:
                seen.add(normalized)
                merged.append(normalized)
    return merged


def parse_price_payload(payload: object) -> dict[str, Decimal]:
    if isinstance(payload, str | bytes):
        try:
            return parse_price_payload(json.loads(payload))
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            return {}

    if isinstance(payload, dict):
        event_type = payload.get("type")
        if event_type is not None:
            if event_type != "PRICE_UPDATE":
                return {}
            return parse_price_payload(payload.get("payload"))

        if "payload" in payload:
            return parse_price_payload(payload["payload"])
        if "prices" in payload:
            return parse_price_payload(payload["prices"])
        if "ticker" in payload or "symbol" in payload:
            return parse_single_price(payload)

        prices: dict[str, Decimal] = {}
        for symbol, value in payload.items():
            if isinstance(value, dict):
                value_to_parse = value.get("price") or value.get("last") or value.get("close")
            else:
                value_to_parse = value
            parsed = decimal_from_any(value_to_parse)
            if parsed is not None:
                prices[str(symbol).upper()] = parsed
        return prices

    if isinstance(payload, list):
        prices: dict[str, Decimal] = {}
        for item in payload:
            prices.update(parse_price_payload(item))
        return prices

    return {}


def parse_single_price(item: dict[str, object]) -> dict[str, Decimal]:
    raw_symbol = item.get("ticker") or item.get("symbol")
    parsed = decimal_from_any(item.get("price") or item.get("last") or item.get("close"))
    if raw_symbol is None or parsed is None:
        return {}
    return {str(raw_symbol).upper(): parsed}


def decimal_from_any(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
