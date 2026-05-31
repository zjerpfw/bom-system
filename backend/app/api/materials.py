import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.embedding_service import create_embeddings
from app.services.material_service import (
    async_build_embedding_index,
    async_get_material_stats,
    async_import_materials_from_csv,
    load_index,
)
from app.services.settings_service import get_runtime_settings


router = APIRouter(prefix="/materials", tags=["materials"])


@router.post("/import")
async def import_materials(file: UploadFile):
    """上传CSV文件并导入ERP物料。"""
    suffix = Path(file.filename or "materials.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(await file.read())
        temp_path = temp_file.name

    try:
        result = await async_import_materials_from_csv(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)

    return {"code": 0, "msg": "ok", "data": result}


@router.post("/build-index")
async def build_material_index(request: Request, db: AsyncSession = Depends(get_db)):
    """重建ERP物料向量索引。"""
    try:
        runtime_settings = await get_runtime_settings(db)
        if not runtime_settings.ai_enabled:
            return {"code": 1, "msg": "AI功能未启用，无法构建向量索引；请在系统设置中开启AI并配置可用的向量接口", "data": {}}
        request.app.state.runtime_settings = runtime_settings
        request.app.state.ai_enabled = runtime_settings.ai_enabled
        await async_build_embedding_index(
            embedding_provider=lambda texts: create_embeddings(
                texts,
                runtime_settings=runtime_settings,
                text_type="document",
            )
        )
    except RuntimeError as error:
        return {"code": 1, "msg": str(error), "data": {}}
    request.app.state.material_index, request.app.state.material_id_map = load_index()
    return {"code": 0, "msg": "ok", "data": {"status": "built"}}


@router.get("/stats")
async def get_material_stats():
    """返回物料数量和索引状态。"""
    stats = await async_get_material_stats()
    return {"code": 0, "msg": "ok", "data": stats}
