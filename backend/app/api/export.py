from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.export_service import export_all_pending_to_excel, export_bom_to_excel


router = APIRouter(prefix="/export", tags=["export"])

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def build_excel_response(content: bytes, filename: str) -> Response:
    """构建Excel下载响应。"""
    encoded_filename = quote(filename)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
    return Response(content=content, media_type=EXCEL_MEDIA_TYPE, headers=headers)


@router.get("/bom/{product_name}")
async def download_bom_excel(product_name: str, db: AsyncSession = Depends(get_db)):
    """下载某产品BOM导入包。"""
    content = await export_bom_to_excel(product_name, db)
    filename = f"BOM_{product_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return build_excel_response(content, filename)


@router.get("/all-pending")
async def download_all_pending_excel(db: AsyncSession = Depends(get_db)):
    """下载所有待处理项汇总。"""
    content = await export_all_pending_to_excel(db)
    filename = f"BOM_待处理汇总_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return build_excel_response(content, filename)
