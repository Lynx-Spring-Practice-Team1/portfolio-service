# Portfolio Service

Python/FastAPI portfolio microservice for the broker platform.

The service consumes filled-order events, maintains user positions and trade history in PostgreSQL, calculates average-cost P&L, enriches snapshots with latest market prices, and publishes `portfolio.updated` events for other services.

## Features

- `GET /health` service health endpoint.
- `GET /portfolio` gateway-facing portfolio snapshot using `X-User-Id`.
- PostgreSQL persistence for positions, trade history, latest prices, and invalid event records.
- Average-cost realized and unrealized P&L.
- Kafka consumer for `order.filled`.
- Kafka producer for `portfolio.updated`.
- Market price lookup from cached websocket prices with HTTP fallback.
- Wallet cash balance lookup with safe zero-cash fallback while wallet integration is still evolving.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d postgres redpanda
alembic upgrade head
uvicorn app.main:app --reload
```

Kafka processing is disabled by default for local API development. Enable it with:

```bash
KAFKA_ENABLED=true uvicorn app.main:app --reload
```

## API

```http
GET /health
```

```http
GET /portfolio
X-User-Id: user-123
```

The portfolio response includes active positions, available and reserved cash, market value, realized P&L, unrealized P&L, and total equity.

## Events

Input topic: `order.filled`

```json
{
  "event_id": "fill-1",
  "order_id": "order-1",
  "user_id": "user-123",
  "symbol": "AAPL",
  "side": "BUY",
  "quantity": "10",
  "price": "100.00",
  "filled_at": "2026-05-08T10:00:00Z"
}
```

Output topic: `portfolio.updated`

```json
{
  "event_id": "portfolio-fill-1",
  "user_id": "user-123",
  "positions": [],
  "total_market_value": "1000.00",
  "realized_pnl": "0.00",
  "unrealized_pnl": "0.00",
  "updated_at": "2026-05-08T10:00:01Z"
}
```

## P&L Rule

The v1 implementation uses average cost:

- Buy fills increase quantity and recalculate average cost.
- Sell fills decrease quantity and realize `(sell_price - average_cost) * sold_quantity`.
- Unrealized P&L is `(latest_price - average_cost) * current_quantity`.
- Duplicate fill events are ignored by `event_id`.
- Invalid sells are recorded in `portfolio_event_errors` and do not mutate positions.

## Tests

```bash
pytest
```
