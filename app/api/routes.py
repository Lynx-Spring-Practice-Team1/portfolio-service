from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.core.config import get_settings
from app.db.session import get_session
from app.models import EquitySnapshot, Position
from app.schemas.portfolio import PortfolioSnapshot
from app.services.portfolio import PortfolioService


class EquitySnapshotIn(BaseModel):
    value: Decimal


class EquitySnapshotOut(BaseModel):
    id: int
    time: datetime
    value: Decimal

    model_config = {"from_attributes": True}


class AdminHoldingBySymbol(BaseModel):
    symbol: str
    quantity: float
    holders: int


class AdminPortfolioMetrics(BaseModel):
    open_position_count: int
    active_holder_count: int
    total_held_quantity: float
    holdings_by_symbol: list[AdminHoldingBySymbol]

router = APIRouter()


def require_internal_token(
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
) -> None:
    if x_internal_token != get_settings().internal_service_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "portfolio-service"}


@router.get("/api/portfolio", response_model=PortfolioSnapshot)
@router.get("/portfolio", response_model=PortfolioSnapshot)
async def get_portfolio(
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> PortfolioSnapshot:
    service = PortfolioService(session)
    return await service.get_snapshot(user_id)


@router.get("/api/portfolio/equity-snapshots", response_model=list[EquitySnapshotOut])
async def get_equity_snapshots(
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> list[EquitySnapshotOut]:
    rows = await session.scalars(
        select(EquitySnapshot)
        .where(EquitySnapshot.user_id == user_id)
        .order_by(EquitySnapshot.time.desc())
        .limit(10)
    )
    return list(reversed(list(rows)))


@router.post("/api/portfolio/equity-snapshots", response_model=EquitySnapshotOut, status_code=201)
async def save_equity_snapshot(
    body: EquitySnapshotIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> EquitySnapshotOut:
    snap = EquitySnapshot(user_id=user_id, value=body.value)
    session.add(snap)
    await session.commit()
    await session.refresh(snap)
    return snap


@router.get("/internal/admin/metrics", response_model=AdminPortfolioMetrics)
async def get_admin_metrics(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[None, Depends(require_internal_token)],
) -> AdminPortfolioMetrics:
    active_position_filter = Position.quantity != 0
    totals = await session.execute(
        select(
            func.count(Position.id),
            func.count(func.distinct(Position.user_id)),
            func.coalesce(func.sum(Position.quantity), 0),
        ).where(active_position_filter)
    )
    open_position_count, active_holder_count, total_held_quantity = totals.one()

    rows = await session.execute(
        select(
            Position.symbol,
            func.coalesce(func.sum(Position.quantity), 0).label("quantity"),
            func.count(func.distinct(Position.user_id)).label("holders"),
        )
        .where(active_position_filter)
        .group_by(Position.symbol)
        .order_by(desc("quantity"))
        .limit(20)
    )
    return AdminPortfolioMetrics(
        open_position_count=open_position_count,
        active_holder_count=active_holder_count,
        total_held_quantity=float(total_held_quantity or 0),
        holdings_by_symbol=[
            AdminHoldingBySymbol(symbol=symbol, quantity=float(quantity or 0), holders=holders)
            for symbol, quantity, holders in rows.all()
        ],
    )
