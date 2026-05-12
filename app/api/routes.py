from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import EquitySnapshot
from app.schemas.portfolio import PortfolioSnapshot
from app.services.portfolio import PortfolioService


class EquitySnapshotIn(BaseModel):
    value: Decimal


class EquitySnapshotOut(BaseModel):
    id: int
    time: datetime
    value: Decimal

    model_config = {"from_attributes": True}

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "portfolio-service"}


@router.get("/api/portfolio", response_model=PortfolioSnapshot)
@router.get("/portfolio", response_model=PortfolioSnapshot)
async def get_portfolio(
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> PortfolioSnapshot:
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id header is required",
        )

    service = PortfolioService(session)
    return await service.get_snapshot(x_user_id)


@router.get("/api/portfolio/equity-snapshots", response_model=list[EquitySnapshotOut])
async def get_equity_snapshots(
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> list[EquitySnapshotOut]:
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-User-Id required")
    rows = await session.scalars(
        select(EquitySnapshot)
        .where(EquitySnapshot.user_id == x_user_id)
        .order_by(EquitySnapshot.time.desc())
        .limit(10)
    )
    return list(reversed(list(rows)))


@router.post("/api/portfolio/equity-snapshots", response_model=EquitySnapshotOut, status_code=201)
async def save_equity_snapshot(
    body: EquitySnapshotIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> EquitySnapshotOut:
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-User-Id required")
    snap = EquitySnapshot(user_id=x_user_id, value=body.value)
    session.add(snap)
    await session.commit()
    await session.refresh(snap)
    return snap
