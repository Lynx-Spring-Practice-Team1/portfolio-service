from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.portfolio import PortfolioSnapshot
from app.services.portfolio import PortfolioService

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
