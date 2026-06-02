import json
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.bom_item import BomItem
from app.models.material import Material
from app.models.missing_material import MissingMaterial
from app.models.name_mapping import NameMapping
from app.models.operation_log import OperationLog
from app.services.match_service import confirm_match, deserialize_candidates


router = APIRouter(prefix="/review", tags=["review"])


class BatchConfirmRequest(BaseModel):
    """批量确认请求。"""

    ids: list[int]
    reviewer: str = Field(default="")


class ReassignRequest(BaseModel):
    """手动指定物料请求。"""

    system_code: str
    reviewer: str = Field(default="")


def success_response(data: dict) -> dict:
    """返回统一成功响应。"""
    return {"code": 0, "msg": "ok", "data": data}


def error_response(message: str) -> dict:
    """返回统一错误响应。"""
    return {"code": 1, "msg": message, "data": {}}


def bom_item_snapshot(item: BomItem | None) -> str:
    """生成BOM条目快照。"""
    if item is None:
        return "{}"
    return json.dumps(
        {
            "id": item.id,
            "status": item.status,
            "material_code": item.material_code,
            "material_name": item.material_name,
            "reviewer": item.reviewer,
        },
        ensure_ascii=False,
    )


def serialize_review_item(item: BomItem, material_by_code: dict[str, Material] | None = None) -> dict:
    """序列化审核条目。"""
    material = material_by_code.get(item.material_code or "") if material_by_code else None
    return {
        "id": item.id,
        "product_name": item.product_name,
        "product_code": item.product_code,
        "material_code": item.material_code,
        "material_name": material.name if material else None,
        "material_spec": material.spec if material else None,
        "raw_name": item.raw_name,
        "quantity": float(item.quantity) if item.quantity is not None else None,
        "unit": item.unit,
        "level": item.level,
        "confidence": float(item.confidence or 0),
        "status": item.status,
        "match_level": item.match_level,
        "candidates": deserialize_candidates(item.candidates_json),
        "auto_confirmed": item.status == "confirmed" and item.reviewed_at is None,
        "reviewer": item.reviewer,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


async def write_operation_log(
    operation: str,
    target_id: int | None,
    operator: str,
    before_value: str,
    after_value: str,
    db: AsyncSession,
) -> None:
    """写入审核操作日志。"""
    db.add(
        OperationLog(
            operation=operation,
            target_id=target_id,
            operator=operator,
            before_value=before_value,
            after_value=after_value,
        )
    )
    await db.commit()


async def get_count(db: AsyncSession, status: str | None = None) -> int:
    """统计BOM条目数量。"""
    statement = select(func.count()).select_from(BomItem)
    if status:
        statement = statement.where(BomItem.status == status)
    result = await db.execute(statement)
    return int(result.scalar() or 0)


@router.get("/dashboard")
async def review_dashboard(db: AsyncSession = Depends(get_db)):
    """返回审核仪表盘数据。"""
    total_bom_items = await get_count(db)
    pending = await get_count(db, "pending")
    confirmed = await get_count(db, "confirmed")
    rejected = await get_count(db, "rejected")
    missing_result = await db.execute(
        select(func.count()).select_from(MissingMaterial).where(MissingMaterial.status == "pending")
    )
    missing_materials = int(missing_result.scalar() or 0)
    auto_result = await db.execute(
        select(func.count()).select_from(BomItem).where(BomItem.status == "confirmed", BomItem.reviewer.is_(None))
    )
    auto_confirmed = int(auto_result.scalar() or 0)
    product_result = await db.execute(
        select(
            BomItem.product_name,
            func.sum(case((BomItem.status == "pending", 1), else_=0)),
            func.count(),
        )
        .group_by(BomItem.product_name)
        .order_by(BomItem.product_name)
    )
    products = [
        {"name": product_name or "", "pending": int(pending_count or 0), "total": int(total_count or 0)}
        for product_name, pending_count, total_count in product_result.all()
    ]
    auto_confirm_rate = round(auto_confirmed / total_bom_items, 2) if total_bom_items else 0.0
    return success_response(
        {
            "total_bom_items": total_bom_items,
            "pending": pending,
            "confirmed": confirmed,
            "rejected": rejected,
            "missing_materials": missing_materials,
            "auto_confirm_rate": auto_confirm_rate,
            "products": products,
        }
    )


@router.get("/items")
async def review_items(
    product_name: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """查询BOM审核条目。"""
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)
    query = select(BomItem)
    count_query = select(func.count()).select_from(BomItem)
    filters = []
    if product_name:
        filters.append(BomItem.product_name == product_name)
    if status:
        filters.append(BomItem.status == status)
    for condition in filters:
        query = query.where(condition)
        count_query = count_query.where(condition)
    total_result = await db.execute(count_query)
    total = int(total_result.scalar() or 0)
    result = await db.execute(
        query.order_by(BomItem.id).offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
    )
    items = result.scalars().all()
    material_codes = [item.material_code for item in items if item.material_code]
    material_by_code = {}
    if material_codes:
        material_result = await db.execute(select(Material).where(Material.code.in_(material_codes)))
        material_by_code = {material.code: material for material in material_result.scalars().all()}
    return success_response(
        {
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "items": [serialize_review_item(item, material_by_code) for item in items],
        }
    )


@router.post("/batch-confirm")
async def batch_confirm(payload: BatchConfirmRequest, db: AsyncSession = Depends(get_db)):
    """批量确认高置信度条目。"""
    confirmed_count = 0
    skipped_count = 0
    for bom_item_id in payload.ids:
        item = await db.get(BomItem, bom_item_id)
        if not item or item.status != "pending" or float(item.confidence or 0) < 0.85 or not item.material_code:
            skipped_count += 1
            continue
        before_value = bom_item_snapshot(item)
        await confirm_match(item.id, item.material_code, payload.reviewer, db)
        refreshed_item = await db.get(BomItem, item.id)
        await write_operation_log(
            "batch_confirm",
            item.id,
            payload.reviewer,
            before_value,
            bom_item_snapshot(refreshed_item),
            db,
        )
        confirmed_count += 1
    return success_response({"confirmed": confirmed_count, "skipped": skipped_count})


@router.post("/reassign/{bom_item_id}")
async def reassign_match(bom_item_id: int, payload: ReassignRequest, db: AsyncSession = Depends(get_db)):
    """手动指定某条记录对应的物料编码。"""
    item = await db.get(BomItem, bom_item_id)
    if not item:
        return error_response("BOM条目不存在")
    material_result = await db.execute(select(Material).where(Material.code == payload.system_code).limit(1))
    if not material_result.scalar_one_or_none():
        return error_response("物料编码不存在")
    before_value = bom_item_snapshot(item)
    await confirm_match(bom_item_id, payload.system_code, payload.reviewer, db)
    refreshed_item = await db.get(BomItem, bom_item_id)
    await write_operation_log(
        "reassign",
        bom_item_id,
        payload.reviewer,
        before_value,
        bom_item_snapshot(refreshed_item),
        db,
    )
    return success_response({"status": "confirmed"})


@router.get("/mapping-stats")
async def mapping_stats(db: AsyncSession = Depends(get_db)):
    """返回命名对照表统计。"""
    total_result = await db.execute(select(func.count()).select_from(NameMapping))
    today_start = date.today()
    today_result = await db.execute(
        select(func.count()).select_from(NameMapping).where(func.date(NameMapping.created_at) == today_start.isoformat())
    )
    top_result = await db.execute(select(NameMapping).order_by(desc(NameMapping.used_count)).limit(10))
    top_used = [
        {
            "raw_name": mapping.raw_name,
            "system_code": mapping.system_code,
            "system_name": mapping.system_name,
            "spec": mapping.spec,
            "used_count": mapping.used_count,
        }
        for mapping in top_result.scalars().all()
    ]
    return success_response(
        {
            "total": int(total_result.scalar() or 0),
            "today_new": int(today_result.scalar() or 0),
            "top_used": top_used,
        }
    )
