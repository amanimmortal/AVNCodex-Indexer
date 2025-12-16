from sqlmodel import SQLModel, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.settings import settings
import os

# Ensure data directory exists
os.makedirs(
    os.path.dirname(settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")),
    exist_ok=True,
)

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)


async def init_db():
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all) # For dev only
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncSession:
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
