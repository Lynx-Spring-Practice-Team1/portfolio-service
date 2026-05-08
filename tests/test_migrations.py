from app.models import Base


def test_metadata_contains_portfolio_tables() -> None:
    assert {
        "positions",
        "trade_history",
        "latest_prices",
        "portfolio_event_errors",
    }.issubset(Base.metadata.tables.keys())
