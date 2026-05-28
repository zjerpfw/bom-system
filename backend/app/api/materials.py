import tempfile
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile

from app.services.material_service import (
    async_build_embedding_index,
    async_get_material_stats,
    async_import_materials_from_csv,
    load_index,
)


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
async def build_material_index(request: Request):
    """重建ERP物料向量索引。"""
    try:
        await async_build_embedding_index()
    except RuntimeError as error:
        return {"code": 1, "msg": str(error), "data": {}}
    request.app.state.material_index, request.app.state.material_id_map = load_index()
    return {"code": 0, "msg": "ok", "data": {"status": "built"}}


@router.get("/stats")
async def get_material_stats():
    """返回物料数量和索引状态。"""
    stats = await async_get_material_stats()
    return {"code": 0, "msg": "ok", "data": stats}
