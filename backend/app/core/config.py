import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

from app.core.paths import get_env_file

ENV_FILE = get_env_file()

load_dotenv(ENV_FILE)


@dataclass(frozen=True)
class Settings:
    """系统配置项。"""

    host: str
    port: int
    api_key: str
    ai_enabled: bool
    openai_api_key: str
    openai_base_url: str
    openai_chat_model: str
    openai_embedding_model: str
    embedding_provider: str
    dashscope_api_key: str
    dashscope_base_url: str
    dashscope_embedding_model: str
    qianfan_api_key: str
    qianfan_base_url: str
    qianfan_embedding_model: str
    paddleocr_model_dir: str
    paddleocr_ascii_cache_dir: str
    baidu_ocr_app_id: str
    baidu_ocr_api_key: str
    baidu_ocr_secret_key: str
    baidu_ocr_account_type: str
    baidu_ocr_free_quota_safety_buffer: int
    baidu_ocr_table_monthly_free_limit: int | None
    baidu_ocr_general_monthly_free_limit: int | None
    baidu_ocr_handwriting_monthly_free_limit: int | None
    database_url: str


def get_optional_int(name: str) -> int | None:
    """读取可选整数配置。"""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return int(value)


def get_bool(name: str, default: bool = False) -> bool:
    """读取布尔配置。"""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


@lru_cache
def get_settings() -> Settings:
    """读取并缓存系统配置。"""
    return Settings(
        host=os.getenv("HOST", "0.0.0.0").strip(),
        port=int(os.getenv("PORT", "8000")),
        api_key=os.getenv("API_KEY", ""),
        ai_enabled=get_bool("AI_ENABLED", False),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "").strip(),
        openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini").strip(),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip(),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "openai").strip().lower(),
        dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", "").strip(),
        dashscope_base_url=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1").strip(),
        dashscope_embedding_model=os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4").strip(),
        qianfan_api_key=os.getenv("QIANFAN_API_KEY", "").strip(),
        qianfan_base_url=os.getenv("QIANFAN_BASE_URL", "https://qianfan.baidubce.com/v2").strip(),
        qianfan_embedding_model=os.getenv("QIANFAN_EMBEDDING_MODEL", "embedding-v1").strip(),
        paddleocr_model_dir=os.getenv("PADDLEOCR_MODEL_DIR", "").strip(),
        paddleocr_ascii_cache_dir=os.getenv("PADDLEOCR_ASCII_CACHE_DIR", "").strip(),
        baidu_ocr_app_id=os.getenv("BAIDU_OCR_APP_ID", ""),
        baidu_ocr_api_key=os.getenv("BAIDU_OCR_API_KEY", ""),
        baidu_ocr_secret_key=os.getenv("BAIDU_OCR_SECRET_KEY", ""),
        baidu_ocr_account_type=os.getenv("BAIDU_OCR_ACCOUNT_TYPE", "personal").strip().lower(),
        baidu_ocr_free_quota_safety_buffer=int(os.getenv("BAIDU_OCR_FREE_QUOTA_SAFETY_BUFFER", "5")),
        baidu_ocr_table_monthly_free_limit=get_optional_int("BAIDU_OCR_TABLE_MONTHLY_FREE_LIMIT"),
        baidu_ocr_general_monthly_free_limit=get_optional_int("BAIDU_OCR_GENERAL_MONTHLY_FREE_LIMIT"),
        baidu_ocr_handwriting_monthly_free_limit=get_optional_int("BAIDU_OCR_HANDWRITING_MONTHLY_FREE_LIMIT"),
        database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/bom.db"),
    )
