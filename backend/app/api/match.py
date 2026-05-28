from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.bom_item import BomItem
from app.models.missing_material import MissingMaterial
from app.services.match_service import (
    confirm_match,
    deserialize_candidates,
    process_extracted_bom,
    reject_match,
)
from app.services.settings_service import get_runtime_settings


router = APIRouter(prefix="/match", tags=["match"])


class ProcessBomRequest(BaseModel):
    """BOM匹配处理请求。"""

    extracted: dict
    product_name: str = ""


class ConfirmMatchRequest(BaseModel):
    """确认匹配请求。"""

    system_code: str
    reviewer: str = Field(default="")


class RejectMatchRequest(BaseModel):
    """拒绝匹配请求。"""

    reviewer: str = Field(default="")


def success_response(data: dict) -> dict:
    """返回统一成功响应。"""
    return {"code": 0, "msg": "ok", "data": data}


def error_response(message: str) -> dict:
    """返回统一错误响应。"""
    return {"code": 1, "msg": message, "data": {}}


def serialize_bom_item(item: BomItem) -> dict:
    """序列化待审核BOM条目。"""
    return {
        "id": item.id,
        "product_name": item.product_name,
        "raw_name": item.raw_name,
        "candidates": deserialize_candidates(item.candidates_json),
        "confidence": float(item.confidence or 0),
        "match_level": item.match_level,
    }


def serialize_missing_material(item: MissingMaterial) -> dict:
    """序列化缺失物料。"""
    return {
        "id": item.id,
        "raw_name": item.raw_name,
        "ai_suggested_name": item.ai_suggested_name,
        "ai_suggested_spec": item.ai_suggested_spec,
        "ai_suggested_unit": item.ai_suggested_unit,
        "ai_suggested_category": item.ai_suggested_category,
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.post("/process")
async def process_bom_match(request: Request, payload: ProcessBomRequest, db: AsyncSession = Depends(get_db)):
    """处理一批提取后的BOM数据。"""
    request.app.state.runtime_settings = await get_runtime_settings(db)
    request.app.state.ai_enabled = request.app.state.runtime_settings.ai_enabled
    stats = await process_extracted_bom(payload.extracted, payload.product_name, db, request.app.state)
    return success_response(stats)


@router.get("/pending")
async def list_pending_matches(page: int = 1, page_size: int = 20, db: AsyncSession = Depends(get_db)):
    """分页获取待审核匹配列表。"""
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)
    total_result = await db.execute(select(func.count()).select_from(BomItem).where(BomItem.status == "pending"))
    total = int(total_result.scalar() or 0)
    result = await db.execute(
        select(BomItem)
        .where(BomItem.status == "pending")
        .order_by(BomItem.id)
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
    )
    items = [serialize_bom_item(item) for item in result.scalars().all()]
    return success_response({"total": total, "page": safe_page, "items": items})


@router.post("/confirm/{bom_item_id}")
async def confirm_match_route(bom_item_id: int, payload: ConfirmMatchRequest, db: AsyncSession = Depends(get_db)):
    """确认某条匹配。"""
    try:
        await confirm_match(bom_item_id, payload.system_code, payload.reviewer, db)
    except ValueError as error:
        return error_response(str(error))
    return success_response({"status": "confirmed"})


@router.post("/reject/{bom_item_id}")
async def reject_match_route(bom_item_id: int, payload: RejectMatchRequest, db: AsyncSession = Depends(get_db)):
    """拒绝某条匹配。"""
    try:
        await reject_match(bom_item_id, payload.reviewer, db)
    except ValueError as error:
        return error_response(str(error))
    return success_response({"status": "rejected"})


@router.get("/missing")
async def list_missing_materials(page: int = 1, page_size: int = 20, db: AsyncSession = Depends(get_db)):
    """分页获取缺失物料列表。"""
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)
    total_result = await db.execute(
        select(func.count()).select_from(MissingMaterial).where(MissingMaterial.status == "pending")
    )
    total = int(total_result.scalar() or 0)
    result = await db.execute(
        select(MissingMaterial)
        .where(MissingMaterial.status == "pending")
        .order_by(MissingMaterial.id)
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
    )
    items = [serialize_missing_material(item) for item in result.scalars().all()]
    return success_response({"total": total, "page": safe_page, "items": items})


@router.post("/create-missing/{missing_id}")
async def create_missing_material(missing_id: int, db: AsyncSession = Depends(get_db)):
    """标记缺失物料已在ERP中新建。"""
    missing_material = await db.get(MissingMaterial, missing_id)
    if not missing_material:
        return error_response("缺失物料不存在")
    missing_material.status = "created"
    await db.commit()
    return success_response({"status": "created"})
