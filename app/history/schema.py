from sqlmodel import SQLModel
from datetime import datetime


class RequestLogRead(SQLModel):
    id: int
    location: str
    requested_at: datetime


class HistoryResponse(SQLModel):
    items: list[RequestLogRead]
    total: int
    offset: int
    limit: int
