from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from typing import Optional


class RequestLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    location: str = Field(index=True)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
