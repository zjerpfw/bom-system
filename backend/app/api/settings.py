from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.settings_service import serialize_system_settings, upsert_system_settings


router = APIRouter(prefix="/settings", tags=["settings"])


class UpdateSettingsRequest(BaseModel):
    """系统配置更新请求。"""

    settings: dict = Field(default_factory=dict)
    operator: str = Field(default="")


def success_response(data: dict) -> dict:
    """返回统一成功响应。"""
    return {"code": 0, "msg": "ok", "data": data}


@router.get("/system")
async def get_system_settings(db: AsyncSession = Depends(get_db)):
    """获取系统配置。"""
    return success_response(await serialize_system_settings(db))


@router.post("/system")
async def update_system_settings(payload: UpdateSettingsRequest, db: AsyncSession = Depends(get_db)):
    """更新系统配置。"""
    await upsert_system_settings(payload.settings, payload.operator, db)
    return success_response(await serialize_system_settings(db))
