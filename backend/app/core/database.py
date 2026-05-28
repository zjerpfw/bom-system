from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.paths import get_data_dir


class Base(DeclarativeBase):
    """数据库模型基类。"""


settings = get_settings()
database_path = get_data_dir()
database_path.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.database_url, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """提供异步数据库会话依赖。"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """初始化数据库表结构。"""
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "sqlite":
            result = await conn.execute(text("PRAGMA table_info(bom_items)"))
            existing_columns = {row[1] for row in result.fetchall()}
            if "match_level" not in existing_columns:
                await conn.execute(text("ALTER TABLE bom_items ADD COLUMN match_level VARCHAR(32)"))
            if "candidates_json" not in existing_columns:
                await conn.execute(text("ALTER TABLE bom_items ADD COLUMN candidates_json TEXT"))
            result = await conn.execute(text("PRAGMA table_info(system_settings)"))
            existing_setting_columns = {row[1] for row in result.fetchall()}
            if existing_setting_columns and "created_at" not in existing_setting_columns:
                await conn.execute(text("ALTER TABLE system_settings ADD COLUMN created_at DATETIME"))
