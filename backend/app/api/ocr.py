import time

from fastapi import APIRouter, Depends, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.ocr_service import (
    extract_bom_from_ocr_text,
    has_baidu_free_quota,
    is_table_image,
    ocr_table_with_baidu,
    ocr_with_paddle,
    preprocess_image,
    table_to_bom_items,
)
from app.services.settings_service import safe_get_runtime_settings


router = APIRouter(prefix="/ocr", tags=["ocr"])


class OcrTextRequest(BaseModel):
    """纯文本BOM提取请求。"""

    text: str
    product_name: str = ""


def call_extract_bom(raw_lines: list[str], product_name: str, runtime_settings):
    """兼容测试替换后的BOM提取函数。"""
    try:
        return extract_bom_from_ocr_text(raw_lines, product_name, runtime_settings=runtime_settings)
    except TypeError as error:
        if "unexpected keyword argument" not in str(error):
            raise
        return extract_bom_from_ocr_text(raw_lines, product_name)


@router.post("/upload")
async def upload_ocr_image(
    file: UploadFile,
    product_name: str = Form(""),
    mode: str = Form("auto"),
    db: AsyncSession = Depends(get_db),
):
    """接收图片文件，返回OCR识别和BOM提取结果。"""
    start_time = time.perf_counter()
    runtime_settings = await safe_get_runtime_settings(db)
    image_bytes = await file.read()
    normalized_mode = mode.lower()
    warnings = []
    if normalized_mode not in {"auto", "paddle", "baidu"}:
        return {"code": 1, "msg": "OCR模式不支持，请使用auto、paddle或baidu", "data": {}}

    use_baidu = normalized_mode == "baidu" or (
        normalized_mode == "auto" and is_table_image(image_bytes) and has_baidu_free_quota("table_v2")
    )
    if normalized_mode == "auto" and is_table_image(image_bytes) and not has_baidu_free_quota("table_v2"):
        warnings.append("百度OCR免费额度不足，已自动切换PaddleOCR")

    if use_baidu:
        try:
            table = ocr_table_with_baidu(image_bytes)
            raw_lines = [" | ".join(cell for cell in row if cell) for row in table]
            extracted = table_to_bom_items(table, product_name, ai_enabled=runtime_settings.ai_enabled)
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "code": 0,
                "msg": "ok",
                "data": {
                    "raw_lines": raw_lines,
                    "table": table,
                    "extracted": extracted,
                    "processing_time_ms": processing_time_ms,
                    "mode": "baidu",
                    "warnings": warnings,
                },
            }
        except Exception as error:
            if normalized_mode == "baidu":
                return {"code": 1, "msg": str(error), "data": {}}
            warnings.append("百度OCR不可用，已自动切换PaddleOCR")

    processed_image = preprocess_image(image_bytes)
    ocr_results = ocr_with_paddle(processed_image)
    raw_lines = [item["text"] for item in ocr_results]
    try:
        extracted = call_extract_bom(raw_lines, product_name, runtime_settings)
    except Exception as error:
        if runtime_settings.ai_enabled:
            warnings.append(f"AI提取失败，已切换规则提取：{error}")
            extracted = extract_bom_from_ocr_text(raw_lines, product_name, ai_enabled=False)
        else:
            raise
    processing_time_ms = int((time.perf_counter() - start_time) * 1000)
    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "raw_lines": raw_lines,
            "extracted": extracted,
            "processing_time_ms": processing_time_ms,
            "mode": "paddle",
            "warnings": warnings,
        },
    }


@router.post("/text")
async def extract_from_text(request: OcrTextRequest, db: AsyncSession = Depends(get_db)):
    """接收纯文本并提取BOM结构。"""
    runtime_settings = await safe_get_runtime_settings(db)
    raw_lines = [line.strip() for line in request.text.splitlines() if line.strip()]
    try:
        extracted = call_extract_bom(raw_lines, request.product_name, runtime_settings)
    except Exception as error:
        if not runtime_settings.ai_enabled:
            return {
                "code": 1,
                "msg": f"文本提取失败：{error}",
                "data": {"raw_lines": raw_lines},
            }
        extracted = extract_bom_from_ocr_text(raw_lines, request.product_name, ai_enabled=False)
        return {
            "code": 0,
            "msg": "ok",
            "data": {"raw_lines": raw_lines, "extracted": extracted, "warnings": [f"AI提取失败，已切换规则提取：{error}"]},
        }
    return {
        "code": 0,
        "msg": "ok",
        "data": {"raw_lines": raw_lines, "extracted": extracted},
    }
