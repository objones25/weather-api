from sqlmodel import select
from sqlalchemy import func
from sqlmodel.ext.asyncio.session import AsyncSession
from app.history.models import RequestLog
from typing import Optional


class HistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        location: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[RequestLog], int]:
        stmt = select(RequestLog)
        if location:
            stmt = stmt.where(RequestLog.location.ilike(f"%{location}%"))  # type: ignore[attr-defined]

        total = await self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        items = (
            await self.session.exec(
                stmt.order_by(RequestLog.requested_at.desc())  # type: ignore[attr-defined]
                .offset(offset)
                .limit(limit)
            )
        ).all()

        return list(items), total or 0
