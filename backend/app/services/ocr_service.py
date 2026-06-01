import base64
import json
import re
import shutil
import time
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import cv2
import httpx
import numpy as np

from app.core.config import get_settings
from app.core.openai_client import create_openai_client, extract_text_from_openai_response
from app.core.paths import get_data_dir


OCR_EXTRACT_SYSTEM_PROMPT = """
你是一个工厂BOM（物料清单）数据提取专家。
用户会给你OCR识别出的文字行，你需要从中提取物料信息。

提取规则：
1. 每个物料包含：名称、规格型号、用量、单位
2. 如果某字段不确定，填 null，不要猜测
3. 识别层级关系：顶层产品→子组件→零件
4. 忽略表头、序号、页码等非物料信息

输出严格的JSON格式（不要输出其他内容）：
{
  "product": "产品名称",
  "items": [
    {
      "name": "物料名称",
      "spec": "规格型号或null",
      "quantity": 数字或null,
      "unit": "单位或null",
      "level": 1,
      "confidence": 0.0到1.0
    }
  ]
}
"""

SPECIAL_SYMBOL_MAP = {
    "×": "x",
    "Ω": "Ohm",
    "μ": "u",
    "°": "deg",
}
_paddle_ocr = None
_baidu_token_cache = {"access_token": "", "expires_at": 0.0}
DATA_DIR = get_data_dir()
BAIDU_USAGE_FILE = DATA_DIR / "baidu_ocr_usage.json"
BAIDU_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
BAIDU_TABLE_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/table"


@dataclass(frozen=True)
class BaiduOcrApi:
    """百度OCR接口免费额度配置。"""

    name: str
    title: str
    endpoint: str
    personal_monthly_limit: int
    enterprise_monthly_limit: int
    env_limit_field: str


BAIDU_OCR_APIS = {
    "table_v2": BaiduOcrApi(
        name="table_v2",
        title="表格文字识别V2",
        endpoint=BAIDU_TABLE_URL,
        personal_monthly_limit=500,
        enterprise_monthly_limit=1000,
        env_limit_field="baidu_ocr_table_monthly_free_limit",
    ),
    "general_basic": BaiduOcrApi(
        name="general_basic",
        title="通用文字识别（标准版）",
        endpoint="https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic",
        personal_monthly_limit=1000,
        enterprise_monthly_limit=2000,
        env_limit_field="baidu_ocr_general_monthly_free_limit",
    ),
    "handwriting": BaiduOcrApi(
        name="handwriting",
        title="手写文字识别",
        endpoint="https://aip.baidubce.com/rest/2.0/ocr/v1/handwriting",
        personal_monthly_limit=500,
        enterprise_monthly_limit=1000,
        env_limit_field="baidu_ocr_handwriting_monthly_free_limit",
    ),
}


def normalize_text(text: str) -> str:
    """规范化OCR文本。"""
    normalized = unicodedata.normalize("NFKC", text or "")
    for source, target in SPECIAL_SYMBOL_MAP.items():
        normalized = normalized.replace(source, target)
    return re.sub(r"\s+", " ", normalized).strip()


def get_baidu_runtime_settings(runtime_settings=None):
    """获取百度OCR可用配置快照。"""
    return runtime_settings or get_settings()


def ensure_baidu_configured(runtime_settings=None) -> None:
    """确认百度OCR密钥已配置。"""
    settings = get_baidu_runtime_settings(runtime_settings)
    if not settings.baidu_ocr_api_key or not settings.baidu_ocr_secret_key:
        raise RuntimeError("百度OCR密钥未配置，请在系统设置中填写百度OCR API Key和Secret Key")


def read_baidu_usage() -> dict:
    """读取百度OCR本地免费额度使用记录。"""
    if not BAIDU_USAGE_FILE.exists():
        return {}
    try:
        return json.loads(BAIDU_USAGE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_baidu_usage(usage: dict) -> None:
    """写入百度OCR本地免费额度使用记录。"""
    BAIDU_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    BAIDU_USAGE_FILE.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")


def get_baidu_api_config(api_name: str) -> BaiduOcrApi:
    """获取百度OCR接口配置。"""
    api_config = BAIDU_OCR_APIS.get(api_name)
    if api_config is None:
        raise RuntimeError(f"百度OCR接口未配置: {api_name}")
    return api_config


def get_baidu_usage_month() -> str:
    """获取百度OCR免费额度统计月份。"""
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def get_baidu_monthly_free_limit(api_name: str, runtime_settings=None) -> int:
    """获取百度OCR接口月度免费额度。"""
    settings = get_baidu_runtime_settings(runtime_settings)
    api_config = get_baidu_api_config(api_name)
    configured_limit = getattr(settings, api_config.env_limit_field)
    if configured_limit is not None:
        return configured_limit
    if settings.baidu_ocr_account_type == "enterprise":
        return api_config.enterprise_monthly_limit
    return api_config.personal_monthly_limit


def get_baidu_quota_status(api_name: str = "table_v2", runtime_settings=None) -> dict:
    """查询百度OCR本地免费额度状态。"""
    api_config = get_baidu_api_config(api_name)
    settings = get_baidu_runtime_settings(runtime_settings)
    usage_month = get_baidu_usage_month()
    usage = read_baidu_usage()
    month_usage = usage.get(usage_month, {})
    if isinstance(month_usage, int):
        month_usage = {"table_v2": month_usage}
    used_count = int(month_usage.get(api_name, 0))
    monthly_limit = get_baidu_monthly_free_limit(api_name, runtime_settings=runtime_settings)
    safe_limit = max(monthly_limit - settings.baidu_ocr_free_quota_safety_buffer, 0)
    remaining_count = max(safe_limit - used_count, 0)
    return {
        "api": api_config.name,
        "title": api_config.title,
        "month": usage_month,
        "account_type": settings.baidu_ocr_account_type,
        "limit": monthly_limit,
        "safety_buffer": settings.baidu_ocr_free_quota_safety_buffer,
        "safe_limit": safe_limit,
        "used": used_count,
        "remaining": remaining_count,
    }


def has_baidu_free_quota(api_name: str = "table_v2", runtime_settings=None) -> bool:
    """判断百度OCR接口是否还有免费额度。"""
    return get_baidu_quota_status(api_name, runtime_settings=runtime_settings)["remaining"] > 0


def reserve_baidu_free_quota(api_name: str = "table_v2", runtime_settings=None) -> None:
    """预占一次百度OCR免费额度，失败调用也会消耗资源。"""
    if not has_baidu_free_quota(api_name, runtime_settings=runtime_settings):
        status = get_baidu_quota_status(api_name, runtime_settings=runtime_settings)
        raise RuntimeError(
            f"百度OCR免费额度保护已触发，{status['title']}本月剩余额度不足，已阻止云端调用"
        )
    usage_month = get_baidu_usage_month()
    usage = read_baidu_usage()
    month_usage = usage.get(usage_month, {})
    if isinstance(month_usage, int):
        month_usage = {"table_v2": month_usage}
    month_usage[api_name] = int(month_usage.get(api_name, 0)) + 1
    usage[usage_month] = month_usage
    write_baidu_usage(usage)


def ensure_baidu_free_quota(api_name: str = "table_v2", runtime_settings=None) -> None:
    """兼容旧调用的百度OCR免费额度检查。"""
    if not has_baidu_free_quota(api_name, runtime_settings=runtime_settings):
        status = get_baidu_quota_status(api_name, runtime_settings=runtime_settings)
        raise RuntimeError(
            f"百度OCR免费额度保护已触发，{status['title']}本月剩余额度不足，已阻止云端调用"
        )


def record_baidu_table_call(runtime_settings=None) -> None:
    """兼容旧调用的百度表格OCR计数。"""
    reserve_baidu_free_quota("table_v2", runtime_settings=runtime_settings)


def call_get_baidu_access_token(runtime_settings=None) -> str:
    """兼容测试替换后的百度token函数。"""
    if runtime_settings is None:
        return get_baidu_access_token()
    return get_baidu_access_token(runtime_settings=runtime_settings)


def get_baidu_access_token(runtime_settings=None) -> str:
    """获取并缓存百度OCR access_token。"""
    ensure_baidu_configured(runtime_settings=runtime_settings)
    now = time.time()
    settings = get_baidu_runtime_settings(runtime_settings)
    if (
        _baidu_token_cache["access_token"]
        and _baidu_token_cache["expires_at"] > now
        and _baidu_token_cache.get("api_key") == settings.baidu_ocr_api_key
    ):
        return _baidu_token_cache["access_token"]

    response = httpx.post(
        BAIDU_TOKEN_URL,
        params={
            "grant_type": "client_credentials",
            "client_id": settings.baidu_ocr_api_key,
            "client_secret": settings.baidu_ocr_secret_key,
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError("百度OCR access_token获取失败")

    expires_in = int(data.get("expires_in", 60 * 60 * 24 * 28))
    _baidu_token_cache["access_token"] = access_token
    _baidu_token_cache["expires_at"] = now + max(expires_in - 3600, 60)
    _baidu_token_cache["api_key"] = settings.baidu_ocr_api_key
    return access_token


def decode_image(image_bytes: bytes) -> np.ndarray:
    """解码图像字节。"""
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("无法解码图片")
    return image


def calculate_skew_angle(binary_image: np.ndarray) -> float:
    """计算图片倾斜角度。"""
    coords = np.column_stack(np.where(binary_image < 255))
    if coords.size == 0:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) >= 45:
        return 0.0
    return float(angle)


def deskew_image(image: np.ndarray, angle: float) -> np.ndarray:
    """根据倾斜角矫正图片。"""
    if abs(angle) < 0.1:
        return image
    height, width = image.shape[:2]
    center = (width // 2, height // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    """预处理上传图片。"""
    image = decode_image(image_bytes)
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary_image = cv2.adaptiveThreshold(
        gray_image,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        11,
    )
    angle = calculate_skew_angle(binary_image)
    return deskew_image(binary_image, angle)


def is_table_image(image_bytes: bytes) -> bool:
    """根据宽高比和线条密度判断是否为表格图片。"""
    image = decode_image(image_bytes)
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray_image.shape[:2]
    aspect_ratio = width / max(height, 1)
    edges = cv2.Canny(gray_image, 50, 150)
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 30))
    horizontal_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, horizontal_kernel)
    vertical_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, vertical_kernel)
    line_density = (cv2.countNonZero(horizontal_lines) + cv2.countNonZero(vertical_lines)) / max(width * height, 1)
    return line_density > 0.01 or aspect_ratio > 1.8


def order_quad_points(points: np.ndarray) -> np.ndarray:
    """按左上、右上、右下、左下顺序排列四点。"""
    points = points.astype("float32")
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).reshape(-1)
    return np.array(
        [
            points[np.argmin(sums)],
            points[np.argmin(diffs)],
            points[np.argmax(sums)],
            points[np.argmax(diffs)],
        ],
        dtype="float32",
    )


def find_table_quad(image: np.ndarray) -> np.ndarray | None:
    """检测照片中的表格四边形。"""
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    enhanced_gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray_image)
    binary_image = cv2.adaptiveThreshold(
        enhanced_gray,
        255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        15,
    )
    height, width = binary_image.shape[:2]
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(width // 18, 40), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(height // 25, 40)))
    horizontal_lines = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, horizontal_kernel)
    vertical_lines = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, vertical_kernel)
    table_lines = cv2.bitwise_or(horizontal_lines, vertical_lines)
    table_lines = cv2.dilate(table_lines, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=2)
    contours, _ = cv2.findContours(table_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    image_area = height * width
    candidates = sorted(contours, key=cv2.contourArea, reverse=True)
    for contour in candidates:
        x, y, rect_width, rect_height = cv2.boundingRect(contour)
        if rect_width * rect_height < image_area * 0.08:
            continue
        hull = cv2.convexHull(contour)
        perimeter = cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, 0.03 * perimeter, True)
        if len(approx) == 4:
            return order_quad_points(approx.reshape(4, 2))
        rect = cv2.minAreaRect(hull)
        return order_quad_points(cv2.boxPoints(rect))
    return None


def warp_table_image(image: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """按表格四边形做透视矫正。"""
    ordered = order_quad_points(quad)
    top_width = np.linalg.norm(ordered[1] - ordered[0])
    bottom_width = np.linalg.norm(ordered[2] - ordered[3])
    left_height = np.linalg.norm(ordered[3] - ordered[0])
    right_height = np.linalg.norm(ordered[2] - ordered[1])
    target_width = int(max(top_width, bottom_width))
    target_height = int(max(left_height, right_height))
    if target_width < 20 or target_height < 20:
        return image
    target = np.array(
        [[0, 0], [target_width - 1, 0], [target_width - 1, target_height - 1], [0, target_height - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(ordered, target)
    return cv2.warpPerspective(image, matrix, (target_width, target_height), borderValue=(255, 255, 255))


def enhance_table_contrast(image: np.ndarray) -> np.ndarray:
    """增强表格图片对比度并保留三通道。"""
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray_image, None, 10, 7, 21)
    enhanced_gray = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8)).apply(denoised)
    sharpen_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(enhanced_gray, -1, sharpen_kernel)
    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)


def enhance_table_photo_for_ocr(image_bytes: bytes) -> bytes:
    """增强手机拍照表格，供百度表格OCR识别。"""
    image = decode_image(image_bytes)
    quad = find_table_quad(image)
    if quad is not None:
        image = warp_table_image(image, quad)
    enhanced_image = enhance_table_contrast(image)
    success, buffer = cv2.imencode(".jpg", enhanced_image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not success:
        raise RuntimeError("表格图片增强失败")
    return buffer.tobytes()


def get_paddle_ocr():
    """懒加载PaddleOCR实例。"""
    global _paddle_ocr
    if _paddle_ocr is None:
        from paddleocr import PaddleOCR

        _paddle_ocr = PaddleOCR(**get_paddle_ocr_kwargs())
    return _paddle_ocr


def get_paddle_ocr_kwargs() -> dict:
    """构建PaddleOCR初始化参数，支持离线模型目录。"""
    settings = get_settings()
    kwargs = {"use_angle_cls": True, "lang": "ch"}
    if not settings.paddleocr_model_dir:
        return kwargs

    model_root = prepare_paddleocr_model_root(Path(settings.paddleocr_model_dir), settings.paddleocr_ascii_cache_dir)
    model_dirs = {
        "det_model_dir": model_root / "det" / "ch" / "ch_PP-OCRv4_det_infer",
        "rec_model_dir": model_root / "rec" / "ch" / "ch_PP-OCRv4_rec_infer",
        "cls_model_dir": model_root / "cls" / "ch_ppocr_mobile_v2.0_cls_infer",
    }
    for key, path in model_dirs.items():
        if path.exists():
            kwargs[key] = str(path)
    return kwargs


def prepare_paddleocr_model_root(model_root: Path, cache_dir: str = "") -> Path:
    """必要时把PaddleOCR模型复制到纯ASCII路径，规避Windows中文路径问题。"""
    resolved_root = model_root.resolve()
    if is_ascii_path(resolved_root):
        return resolved_root

    cache_root = Path(cache_dir).resolve() if cache_dir else Path.home() / ".bom-system" / "paddleocr" / "whl"
    if not cache_root.exists() or is_model_cache_stale(resolved_root, cache_root):
        cache_root.parent.mkdir(parents=True, exist_ok=True)
        if cache_root.exists():
            shutil.rmtree(cache_root)
        shutil.copytree(resolved_root, cache_root)
    return cache_root


def is_ascii_path(path: Path) -> bool:
    """判断路径是否只包含ASCII字符。"""
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def is_model_cache_stale(source_root: Path, cache_root: Path) -> bool:
    """判断模型缓存是否缺少关键文件。"""
    required_files = [
        "det/ch/ch_PP-OCRv4_det_infer/inference.pdmodel",
        "rec/ch/ch_PP-OCRv4_rec_infer/inference.pdmodel",
        "cls/ch_ppocr_mobile_v2.0_cls_infer/inference.pdmodel",
    ]
    return any((source_root / relative_path).exists() and not (cache_root / relative_path).exists() for relative_path in required_files)


def normalize_bbox(bbox) -> list[list[float]]:
    """规范化OCR文本框坐标。"""
    return [[point[0], point[1]] for point in bbox]


def parse_paddle_result(raw_result) -> list[dict]:
    """解析PaddleOCR返回结果。"""
    if not raw_result:
        return []
    records = raw_result[0] if len(raw_result) == 1 and isinstance(raw_result[0], list) else raw_result
    results = []
    for record in records:
        if not record or len(record) < 2:
            continue
        bbox = normalize_bbox(record[0])
        text = normalize_text(record[1][0])
        confidence = float(record[1][1])
        results.append({"text": text, "confidence": confidence, "bbox": bbox})
    return sorted(results, key=lambda item: min(point[1] for point in item["bbox"]))


def ocr_with_paddle(image: np.ndarray) -> list[dict]:
    """使用PaddleOCR识别图片文字。"""
    ocr = get_paddle_ocr()
    ocr_image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if len(image.shape) == 2 else image
    try:
        raw_result = ocr.ocr(ocr_image)
    except TypeError:
        raw_result = ocr.ocr(ocr_image, cls=True)
    return parse_paddle_result(raw_result)


def build_table_from_cells(cells: list[dict]) -> list[list[str]]:
    """根据百度OCR单元格坐标重建二维表格。"""
    if not cells:
        return []
    max_row = max(int(cell.get("row_end", cell.get("row_start", 0))) for cell in cells)
    max_col = max(int(cell.get("col_end", cell.get("col_start", 0))) for cell in cells)
    table = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
    for cell in cells:
        row_start = int(cell.get("row_start", 0))
        row_end = int(cell.get("row_end", row_start))
        col_start = int(cell.get("col_start", 0))
        col_end = int(cell.get("col_end", col_start))
        text = normalize_text(cell.get("words") or cell.get("text") or "")
        for row_index in range(row_start, row_end + 1):
            for col_index in range(col_start, col_end + 1):
                table[row_index][col_index] = text
    return table


def ocr_table_with_baidu(image_bytes: bytes, runtime_settings=None) -> list[list[str]]:
    """调用百度OCR表格识别并返回二维表格。"""
    reserve_baidu_free_quota("table_v2", runtime_settings=runtime_settings)
    access_token = call_get_baidu_access_token(runtime_settings=runtime_settings)
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    response = httpx.post(
        BAIDU_TABLE_URL,
        params={"access_token": access_token},
        data={"image": image_base64, "return_excel": "false"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error_code"):
        raise RuntimeError(f"百度OCR调用失败: {data.get('error_msg', data.get('error_code'))}")

    tables_result = data.get("tables_result") or []
    if not tables_result:
        return []
    cells = tables_result[0].get("body") or tables_result[0].get("cells") or []
    return build_table_from_cells(cells)


def find_header_row(table: list[list[str]]) -> tuple[int, dict[str, int]]:
    """查找表头行并返回字段列映射。"""
    field_keywords = {
        "name": ["名称", "物料名称", "品名", "零件名称"],
        "spec": ["规格", "规格型号", "型号"],
        "quantity": ["用量", "数量", "Qty", "QTY"],
        "unit": ["单位", "计量单位"],
    }
    best_index = -1
    best_mapping: dict[str, int] = {}
    for row_index, row in enumerate(table):
        mapping = {}
        for col_index, cell in enumerate(row):
            normalized_cell = normalize_text(cell)
            for field_name, keywords in field_keywords.items():
                if any(keyword.lower() in normalized_cell.lower() for keyword in keywords):
                    mapping[field_name] = col_index
        if len(mapping) > len(best_mapping):
            best_index = row_index
            best_mapping = mapping
    return best_index, best_mapping


def parse_quantity(value: str):
    """解析用量数字。"""
    text = normalize_text(value)
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        number = Decimal(match.group(0))
    except InvalidOperation:
        return None
    return int(number) if number == number.to_integral_value() else float(number)


def is_summary_text(text: str) -> bool:
    """判断文本是否为合计类汇总行。"""
    normalized = normalize_text(text).replace(" ", "")
    if not normalized:
        return False
    keywords = ["合计", "总计", "小计", "共计", "累计", "总合计"]
    return any(keyword in normalized for keyword in keywords)


def is_summary_row(cells: list[str]) -> bool:
    """判断表格行是否为合计类汇总行。"""
    return is_summary_text(" ".join(normalize_text(cell) for cell in cells if normalize_text(cell)))


def table_row_to_line(row: list[str]) -> str:
    """将表格行转换为兜底提取文本。"""
    return " ".join(normalize_text(cell) for cell in row if normalize_text(cell))


def get_cell_by_mapping(cells: list[str], mapping: dict[str, int], field_name: str) -> str:
    """按字段映射安全读取单元格。"""
    col_index = mapping.get(field_name)
    if col_index is None or col_index < 0 or col_index >= len(cells):
        return ""
    return cells[col_index]


def table_to_bom_items(table: list[list[str]], product_name: str, ai_enabled: bool | None = None) -> dict:
    """将百度OCR表格转换为BOM结构。"""
    header_index, mapping = find_header_row(table)
    if header_index < 0 or "name" not in mapping:
        raw_lines = [table_row_to_line(row) for row in table if table_row_to_line(row)]
        return extract_bom_from_ocr_text(raw_lines, product_name, ai_enabled=ai_enabled)

    items = []
    fallback_lines = []
    seen_rows = set()
    for row in table[header_index + 1 :]:
        normalized_cells = [normalize_text(cell) for cell in row]
        if not any(normalized_cells):
            continue
        if is_summary_row(normalized_cells):
            continue
        row_key = "|".join(normalized_cells)
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)

        name = get_cell_by_mapping(normalized_cells, mapping, "name")
        if not name:
            fallback_line = table_row_to_line(row)
            if fallback_line:
                fallback_lines.append(fallback_line)
            continue

        spec = get_cell_by_mapping(normalized_cells, mapping, "spec")
        unit = get_cell_by_mapping(normalized_cells, mapping, "unit")
        quantity_text = get_cell_by_mapping(normalized_cells, mapping, "quantity")
        quantity = parse_quantity(quantity_text)
        items.append(
            {
                "name": name,
                "spec": spec or None,
                "quantity": quantity,
                "unit": unit or None,
                "level": 1,
                "confidence": 0.86,
            }
        )

    if fallback_lines:
        fallback_result = extract_bom_from_ocr_text(fallback_lines, product_name, ai_enabled=ai_enabled)
        items.extend(fallback_result.get("items", []))

    return {"product": product_name, "items": items}


def strip_markdown_json(content: str) -> str:
    """去除LLM返回中的markdown代码块。"""
    text = content.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def remove_leading_index(text: str) -> str:
    """移除行首序号。"""
    return re.sub(r"^\s*(?:\d+|[A-Za-z])[\.\)、\)\s]+", "", text).strip()


def looks_like_header(text: str) -> bool:
    """判断是否为表头或说明文字。"""
    lowered = text.lower()
    keywords = ["名称", "规格", "数量", "用量", "单位", "序号", "name", "spec", "qty", "unit"]
    return sum(1 for keyword in keywords if keyword.lower() in lowered) >= 2


def infer_unit(token: str) -> bool:
    """判断分词是否像单位。"""
    return token in {"个", "件", "套", "pcs", "PCS", "片", "只", "台", "米", "kg", "KG"}


def looks_like_serial_number(token: str) -> bool:
    """判断分词是否像表格序号。"""
    return bool(re.fullmatch(r"\d{1,3}", normalize_text(token)))


def looks_like_spec_token(token: str) -> bool:
    """判断分词是否像规格型号。"""
    text = normalize_text(token)
    if not text or infer_unit(text):
        return False
    has_digit = bool(re.search(r"\d", text))
    has_spec_mark = bool(re.search(r"[A-Za-zxX*./-]|mm|cm|uf|ohm|Ω|μ", text, flags=re.IGNORECASE))
    return has_digit and has_spec_mark


def is_fragment_noise(token: str) -> bool:
    """判断PaddleOCR碎片是否为表头或说明。"""
    text = normalize_text(token)
    if not text:
        return True
    if is_summary_text(text):
        return True
    exact_headers = {"序号", "名称", "规格", "规格型号", "型号", "数量", "用量", "单位", "用量单位"}
    if text in exact_headers:
        return True
    if text.lower() in {"name", "spec", "qty", "unit"}:
        return True
    return "产品名称" in text or "页码" in text


def find_previous_name_token(tokens: list[str], index: int) -> str | None:
    """从序号左侧寻找物料名称。"""
    for cursor in range(index - 1, max(index - 5, -1), -1):
        token = tokens[cursor]
        if is_fragment_noise(token) or infer_unit(token) or looks_like_serial_number(token):
            continue
        return token
    return None


def find_nearby_unit(tokens: list[str], index: int, quantity_index: int | None) -> str | None:
    """从序号或数量附近推断单位。"""
    for cursor in range(index - 1, max(index - 4, -1), -1):
        if infer_unit(tokens[cursor]):
            return tokens[cursor]
    if quantity_index is not None:
        for cursor in range(quantity_index + 1, min(quantity_index + 3, len(tokens))):
            if infer_unit(tokens[cursor]):
                return tokens[cursor]
    return None


def rule_extract_fragmented_table(raw_lines: list[str]) -> list[dict]:
    """从PaddleOCR拆散的表格文本中提取BOM条目。"""
    tokens = [normalize_text(line) for line in raw_lines if normalize_text(line)]
    items = []
    for index, token in enumerate(tokens):
        if not looks_like_serial_number(token):
            continue
        next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
        if not looks_like_spec_token(next_token):
            continue

        name = find_previous_name_token(tokens, index)
        if not name:
            continue

        spec = next_token
        quantity = None
        quantity_index = None
        for cursor in range(index + 2, min(index + 5, len(tokens))):
            candidate = tokens[cursor]
            parsed_quantity = parse_quantity(candidate)
            if parsed_quantity is not None and not looks_like_spec_token(candidate):
                quantity = parsed_quantity
                quantity_index = cursor
                break
            if looks_like_serial_number(candidate) or is_fragment_noise(candidate) or infer_unit(candidate):
                continue

        items.append(
            {
                "name": name,
                "spec": spec or None,
                "quantity": quantity,
                "unit": find_nearby_unit(tokens, index, quantity_index),
                "level": 1,
                "confidence": 0.58,
            }
        )
    return items


def rule_extract_line(line: str) -> dict | None:
    """用规则从一行文本提取BOM条目。"""
    text = remove_leading_index(normalize_text(line))
    if not text or looks_like_header(text) or is_summary_text(text):
        return None
    tokens = text.split()
    if len(tokens) < 2:
        return None

    unit = None
    if tokens and infer_unit(tokens[-1]):
        unit = tokens.pop()

    quantity = None
    quantity_index = None
    for index in range(len(tokens) - 1, -1, -1):
        quantity = parse_quantity(tokens[index])
        if quantity is not None:
            quantity_index = index
            break
    if quantity_index is not None:
        tokens.pop(quantity_index)

    if not tokens:
        return None
    name = tokens[0]
    spec = " ".join(tokens[1:]) if len(tokens) > 1 else None
    return {
        "name": name,
        "spec": spec or None,
        "quantity": quantity,
        "unit": unit,
        "level": 1,
        "confidence": 0.62,
    }


def rule_extract_bom_from_ocr_text(raw_lines: list[str], product_name: str) -> dict:
    """无AI模式下用简单规则提取BOM结构。"""
    items = []
    seen = set()
    candidates = [rule_extract_line(line) for line in raw_lines]
    candidates.extend(rule_extract_fragmented_table(raw_lines))
    for item in candidates:
        if not item:
            continue
        row_key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if row_key in seen:
            continue
        seen.add(row_key)
        items.append(item)
    return {"product": product_name, "items": items}


def should_use_ai(ai_enabled: bool | None) -> bool:
    """判断OCR提取是否启用AI。"""
    if ai_enabled is not None:
        return ai_enabled
    return get_settings().ai_enabled


def extract_bom_from_ocr_text(raw_lines: list[str], product_name: str, ai_enabled: bool | None = None, runtime_settings=None) -> dict:
    """从OCR文本中提取BOM结构，AI关闭时使用规则降级。"""
    if not should_use_ai(runtime_settings.ai_enabled if runtime_settings else ai_enabled):
        return rule_extract_bom_from_ocr_text(raw_lines, product_name)

    settings = get_settings()
    chat_model = runtime_settings.openai_chat_model if runtime_settings else settings.openai_chat_model
    api_key = runtime_settings.openai_api_key if runtime_settings else None
    base_url = runtime_settings.openai_base_url if runtime_settings else None
    client = create_openai_client(api_key=api_key, base_url=base_url)
    normalized_lines = [normalize_text(line) for line in raw_lines if normalize_text(line)]
    user_content = json.dumps(
        {"product_name": product_name, "raw_lines": normalized_lines},
        ensure_ascii=False,
    )
    response = client.chat.completions.create(
        model=chat_model,
        messages=[
            {"role": "system", "content": OCR_EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
    )
    content = extract_text_from_openai_response(response) or "{}"
    return json.loads(strip_markdown_json(content))
