from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession
from app.database import get_session
from app.history.service import HistoryService
from typing import Optional

router = APIRouter(
    prefix="/v1",
    tags=["History"],
)


@router.get("/history")
async def get_history(
    location: Optional[str] = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    service = HistoryService(session)
    items, total = await service.list(location=location, offset=offset, limit=limit)
    return {"items": items, "total": total, "offset": offset, "limit": limit}
