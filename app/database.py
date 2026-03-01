from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.orm import sessionmaker
from app.config import Settings
from fastapi import Request


async def init_db(settings: Settings) -> tuple[AsyncEngine, sessionmaker]:
    engine = create_async_engine(settings.database_url)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine, session_factory


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.db_session_factory() as session:
        yield session
