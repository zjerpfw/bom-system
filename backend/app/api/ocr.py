import time

from fastapi import APIRouter, Depends, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.ocr_service import (
    enhance_table_photo_for_ocr,
    extract_bom_from_ocr_text,
    find_header_row,
    get_cell_by_mapping,
    has_baidu_free_quota,
    is_summary_row,
    is_table_image,
    ocr_table_with_baidu,
    ocr_with_paddle,
    parse_quantity,
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


def call_has_baidu_free_quota(api_name: str, runtime_settings) -> bool:
    """兼容测试替换后的百度OCR额度函数。"""
    try:
        return has_baidu_free_quota(api_name, runtime_settings=runtime_settings)
    except TypeError as error:
        if "unexpected keyword argument" not in str(error):
            raise
        return has_baidu_free_quota(api_name)


def call_ocr_table_with_baidu(image_bytes: bytes, runtime_settings) -> list[list[str]]:
    """兼容测试替换后的百度OCR表格函数。"""
    try:
        return ocr_table_with_baidu(image_bytes, runtime_settings=runtime_settings)
    except TypeError as error:
        if "unexpected keyword argument" not in str(error):
            raise
        return ocr_table_with_baidu(image_bytes)


def count_complete_bom_rows(table: list[list[str]]) -> int:
    """统计同时包含名称和数量的表格数据行。"""
    header_index, mapping = find_header_row(table)
    if header_index < 0 or "name" not in mapping or "quantity" not in mapping:
        return 0

    complete_count = 0
    for row in table[header_index + 1 :]:
        normalized_cells = [str(cell).strip() for cell in row]
        if not any(normalized_cells) or is_summary_row(normalized_cells):
            continue
        name = get_cell_by_mapping(normalized_cells, mapping, "name")
        quantity = parse_quantity(get_cell_by_mapping(normalized_cells, mapping, "quantity"))
        if name and quantity is not None:
            complete_count += 1
    return complete_count


def should_retry_original_table(table: list[list[str]]) -> bool:
    """判断增强后的表格结果是否过少，需要用原图重试。"""
    return count_complete_bom_rows(table) < 1


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
    if normalized_mode not in {"auto", "paddle", "baidu", "baidu_enhanced"}:
        return {"code": 1, "msg": "OCR模式不支持，请使用auto、paddle、baidu或baidu_enhanced", "data": {}}

    table_like = is_table_image(image_bytes)
    use_enhanced_baidu = normalized_mode == "baidu_enhanced" or (normalized_mode == "auto" and table_like)
    use_baidu = normalized_mode in {"baidu", "baidu_enhanced"} or (
        normalized_mode == "auto"
        and table_like
        and call_has_baidu_free_quota("table_v2", runtime_settings)
    )
    if normalized_mode == "auto" and table_like and not call_has_baidu_free_quota("table_v2", runtime_settings):
        warnings.append("百度OCR免费额度不足，已自动切换PaddleOCR")

    if use_baidu:
        try:
            ocr_image_bytes = enhance_table_photo_for_ocr(image_bytes) if use_enhanced_baidu else image_bytes
            table = call_ocr_table_with_baidu(ocr_image_bytes, runtime_settings)
            baidu_mode = "baidu_enhanced" if use_enhanced_baidu else "baidu"
            if normalized_mode == "auto" and use_enhanced_baidu and should_retry_original_table(table):
                if call_has_baidu_free_quota("table_v2", runtime_settings):
                    original_table = call_ocr_table_with_baidu(image_bytes, runtime_settings)
                    if count_complete_bom_rows(original_table) > count_complete_bom_rows(table):
                        table = original_table
                        baidu_mode = "baidu_original_retry"
                        warnings.append("增强识别结果偏少，已自动用原图重试")
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
                    "mode": baidu_mode,
                    "warnings": warnings,
                },
            }
        except Exception as error:
            if normalized_mode in {"baidu", "baidu_enhanced"}:
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
