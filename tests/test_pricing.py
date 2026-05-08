import json
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import pytest

from app.core.config import Settings
from app.services.pricing import (
    MarketWebsocketPriceStreamer,
    build_market_ws_url,
    parse_price_payload,
    parse_tickers,
)


class FakeWebsocket:
    def __init__(self) -> None:
        self.sent_messages: list[dict] = []

    async def send(self, message: str) -> None:
        self.sent_messages.append(json.loads(message))


def test_parse_nested_price_update_envelope() -> None:
    payload = {"type": "PRICE_UPDATE", "payload": {"ticker": "AAPL", "price": 150.75}}

    assert parse_price_payload(payload) == {"AAPL": Decimal("150.75")}


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "CONNECTED", "payload": {"message": "ok"}},
        {"type": "ORDER_UPDATE", "payload": {"ticker": "AAPL", "price": 150.75}},
        {"type": "ORDER_BOOK_UPDATE", "payload": {"ticker": "AAPL", "price": 150.75}},
        {"type": "PRICE_UPDATE", "payload": {"ticker": "AAPL"}},
        "not-json",
    ],
)
def test_parse_ignores_unrelated_and_malformed_messages(payload) -> None:
    assert parse_price_payload(payload) == {}


@pytest.mark.asyncio
async def test_subscription_payload_shape_uses_price_feed_and_tickers() -> None:
    settings = Settings(market_ws_default_tickers="AAPL,JPM")
    streamer = MarketWebsocketPriceStreamer(
        session_factory=None,
        symbol_provider=lambda: ["msft", "aapl"],
        settings=settings,
    )
    websocket = FakeWebsocket()

    await streamer._subscribe(websocket)

    assert websocket.sent_messages == [
        {
            "type": "SUBSCRIBE",
            "payload": {"channel": "PRICE_FEED", "tickers": ["AAPL", "JPM", "MSFT"]},
        },
    ]


def test_parse_tickers_from_default_setting() -> None:
    assert parse_tickers(" aapl, JPM, aapl ,, msft ") == ["AAPL", "JPM", "MSFT"]


def test_build_market_ws_url_adds_credentials() -> None:
    settings = Settings(
        market_ws_url="ws://localhost:8080/ws?existing=true",
        market_ws_api_key="test-api-key",
        market_ws_api_secret="test-api-secret",
    )

    parsed = urlsplit(build_market_ws_url(settings))
    query = parse_qs(parsed.query)

    assert parsed.scheme == "ws"
    assert parsed.netloc == "localhost:8080"
    assert parsed.path == "/ws"
    assert query["existing"] == ["true"]
    assert query["api_key"] == ["test-api-key"]
    assert query["api_secret"] == ["test-api-secret"]
