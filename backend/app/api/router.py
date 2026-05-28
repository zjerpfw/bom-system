from fastapi import APIRouter

from app.api.export import router as export_router
from app.api.match import router as match_router
from app.api.materials import router as materials_router
from app.api.ocr import router as ocr_router
from app.api.review import router as review_router
from app.api.settings import router as settings_router


api_router = APIRouter()
api_router.include_router(materials_router)
api_router.include_router(ocr_router)
api_router.include_router(match_router)
api_router.include_router(review_router)
api_router.include_router(export_router)
api_router.include_router(settings_router)


@api_router.get("/health")
async def health_check():
    """返回服务健康状态。"""
    return {"code": 0, "msg": "ok", "data": {"status": "running"}}
