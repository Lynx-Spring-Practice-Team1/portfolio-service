"""initial portfolio schema

Revision ID: 0001_initial_portfolio_schema
Revises:
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_portfolio_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("average_cost", sa.Numeric(28, 8), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(28, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "symbol", name="uq_positions_user_symbol"),
    )
    op.create_index(op.f("ix_positions_symbol"), "positions", ["symbol"], unique=False)
    op.create_index(op.f("ix_positions_user_id"), "positions", ["user_id"], unique=False)

    op.create_table(
        "trade_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("price", sa.Numeric(28, 8), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(28, 8), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trade_history_event_id"), "trade_history", ["event_id"], unique=True)
    op.create_index(op.f("ix_trade_history_order_id"), "trade_history", ["order_id"], unique=False)
    op.create_index(op.f("ix_trade_history_symbol"), "trade_history", ["symbol"], unique=False)
    op.create_index(op.f("ix_trade_history_user_id"), "trade_history", ["user_id"], unique=False)

    op.create_table(
        "latest_prices",
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("price", sa.Numeric(28, 8), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("symbol"),
    )
    op.create_index(
        op.f("ix_latest_prices_observed_at"),
        "latest_prices",
        ["observed_at"],
        unique=False,
    )

    op.create_table(
        "portfolio_event_errors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_portfolio_event_errors_event_id"),
        "portfolio_event_errors",
        ["event_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_portfolio_event_errors_event_id"), table_name="portfolio_event_errors")
    op.drop_table("portfolio_event_errors")
    op.drop_index(op.f("ix_latest_prices_observed_at"), table_name="latest_prices")
    op.drop_table("latest_prices")
    op.drop_index(op.f("ix_trade_history_user_id"), table_name="trade_history")
    op.drop_index(op.f("ix_trade_history_symbol"), table_name="trade_history")
    op.drop_index(op.f("ix_trade_history_order_id"), table_name="trade_history")
    op.drop_index(op.f("ix_trade_history_event_id"), table_name="trade_history")
    op.drop_table("trade_history")
    op.drop_index(op.f("ix_positions_user_id"), table_name="positions")
    op.drop_index(op.f("ix_positions_symbol"), table_name="positions")
    op.drop_table("positions")
