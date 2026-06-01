from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.system_setting import SystemSetting


@dataclass(frozen=True)
class SettingDefinition:
    """系统配置定义。"""

    key: str
    value_type: str
    group_name: str
    description: str
    is_secret: bool = False


@dataclass(frozen=True)
class RuntimeSettings:
    """运行时配置快照。"""

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
    baidu_ocr_app_id: str
    baidu_ocr_api_key: str
    baidu_ocr_secret_key: str
    baidu_ocr_account_type: str
    baidu_ocr_free_quota_safety_buffer: int
    baidu_ocr_table_monthly_free_limit: int | None
    baidu_ocr_general_monthly_free_limit: int | None
    baidu_ocr_handwriting_monthly_free_limit: int | None
    ai_match_mode: str
    ocr_extract_mode: str

    @property
    def openai_api_key_configured(self) -> bool:
        """判断OpenAI密钥是否已配置。"""
        return bool(self.openai_api_key)

    @property
    def dashscope_api_key_configured(self) -> bool:
        """判断阿里百炼密钥是否已配置。"""
        return bool(self.dashscope_api_key)

    @property
    def qianfan_api_key_configured(self) -> bool:
        """判断百度千帆密钥是否已配置。"""
        return bool(self.qianfan_api_key)

    @property
    def baidu_ocr_api_key_configured(self) -> bool:
        """判断百度OCR API Key是否已配置。"""
        return bool(self.baidu_ocr_api_key)

    @property
    def baidu_ocr_secret_key_configured(self) -> bool:
        """判断百度OCR Secret Key是否已配置。"""
        return bool(self.baidu_ocr_secret_key)


SETTING_DEFINITIONS = {
    "AI_ENABLED": SettingDefinition("AI_ENABLED", "bool", "ai", "是否启用AI增强能力"),
    "OPENAI_API_KEY": SettingDefinition("OPENAI_API_KEY", "secret", "ai", "OpenAI或中转站密钥", True),
    "OPENAI_BASE_URL": SettingDefinition("OPENAI_BASE_URL", "string", "ai", "OpenAI兼容接口地址"),
    "OPENAI_CHAT_MODEL": SettingDefinition("OPENAI_CHAT_MODEL", "string", "ai", "聊天和推理模型"),
    "OPENAI_EMBEDDING_MODEL": SettingDefinition("OPENAI_EMBEDDING_MODEL", "string", "ai", "向量模型"),
    "EMBEDDING_PROVIDER": SettingDefinition("EMBEDDING_PROVIDER", "string", "ai", "向量供应商"),
    "DASHSCOPE_API_KEY": SettingDefinition("DASHSCOPE_API_KEY", "secret", "ai", "阿里百炼DashScope密钥", True),
    "DASHSCOPE_BASE_URL": SettingDefinition("DASHSCOPE_BASE_URL", "string", "ai", "阿里百炼DashScope接口地址"),
    "DASHSCOPE_EMBEDDING_MODEL": SettingDefinition("DASHSCOPE_EMBEDDING_MODEL", "string", "ai", "阿里百炼向量模型"),
    "QIANFAN_API_KEY": SettingDefinition("QIANFAN_API_KEY", "secret", "ai", "百度千帆API Key", True),
    "QIANFAN_BASE_URL": SettingDefinition("QIANFAN_BASE_URL", "string", "ai", "百度千帆接口地址"),
    "QIANFAN_EMBEDDING_MODEL": SettingDefinition("QIANFAN_EMBEDDING_MODEL", "string", "ai", "百度千帆向量模型"),
    "BAIDU_OCR_APP_ID": SettingDefinition("BAIDU_OCR_APP_ID", "string", "ocr", "百度OCR App ID"),
    "BAIDU_OCR_API_KEY": SettingDefinition("BAIDU_OCR_API_KEY", "secret", "ocr", "百度OCR API Key", True),
    "BAIDU_OCR_SECRET_KEY": SettingDefinition("BAIDU_OCR_SECRET_KEY", "secret", "ocr", "百度OCR Secret Key", True),
    "BAIDU_OCR_ACCOUNT_TYPE": SettingDefinition("BAIDU_OCR_ACCOUNT_TYPE", "string", "ocr", "百度OCR账号类型"),
    "BAIDU_OCR_FREE_QUOTA_SAFETY_BUFFER": SettingDefinition(
        "BAIDU_OCR_FREE_QUOTA_SAFETY_BUFFER", "int", "ocr", "百度OCR免费额度保护预留次数"
    ),
    "BAIDU_OCR_TABLE_MONTHLY_FREE_LIMIT": SettingDefinition(
        "BAIDU_OCR_TABLE_MONTHLY_FREE_LIMIT", "int", "ocr", "百度OCR表格识别月度免费额度"
    ),
    "BAIDU_OCR_GENERAL_MONTHLY_FREE_LIMIT": SettingDefinition(
        "BAIDU_OCR_GENERAL_MONTHLY_FREE_LIMIT", "int", "ocr", "百度OCR通用识别月度免费额度"
    ),
    "BAIDU_OCR_HANDWRITING_MONTHLY_FREE_LIMIT": SettingDefinition(
        "BAIDU_OCR_HANDWRITING_MONTHLY_FREE_LIMIT", "int", "ocr", "百度OCR手写识别月度免费额度"
    ),
    "AI_MATCH_MODE": SettingDefinition("AI_MATCH_MODE", "string", "ai", "物料匹配模式"),
    "OCR_EXTRACT_MODE": SettingDefinition("OCR_EXTRACT_MODE", "string", "ocr", "OCR文本提取模式"),
}


def parse_bool(value: str | bool | None) -> bool:
    """解析布尔配置值。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def serialize_value(value) -> str:
    """序列化配置值。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value).strip()


def parse_int(value: str | int | None, default: int = 0) -> int:
    """解析整数配置值。"""
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(str(value).strip())
    except ValueError:
        return default


def parse_optional_int(value: str | int | None) -> int | None:
    """解析可选整数配置值。"""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def mask_secret(value: str | None) -> str:
    """掩码显示密钥。"""
    return "********" if value else ""


def build_default_values() -> dict[str, str]:
    """构建.env默认配置。"""
    settings = get_settings()
    return {
        "AI_ENABLED": serialize_value(settings.ai_enabled),
        "OPENAI_API_KEY": settings.openai_api_key,
        "OPENAI_BASE_URL": settings.openai_base_url,
        "OPENAI_CHAT_MODEL": settings.openai_chat_model,
        "OPENAI_EMBEDDING_MODEL": settings.openai_embedding_model,
        "EMBEDDING_PROVIDER": settings.embedding_provider,
        "DASHSCOPE_API_KEY": settings.dashscope_api_key,
        "DASHSCOPE_BASE_URL": settings.dashscope_base_url,
        "DASHSCOPE_EMBEDDING_MODEL": settings.dashscope_embedding_model,
        "QIANFAN_API_KEY": settings.qianfan_api_key,
        "QIANFAN_BASE_URL": settings.qianfan_base_url,
        "QIANFAN_EMBEDDING_MODEL": settings.qianfan_embedding_model,
        "BAIDU_OCR_APP_ID": settings.baidu_ocr_app_id,
        "BAIDU_OCR_API_KEY": settings.baidu_ocr_api_key,
        "BAIDU_OCR_SECRET_KEY": settings.baidu_ocr_secret_key,
        "BAIDU_OCR_ACCOUNT_TYPE": settings.baidu_ocr_account_type,
        "BAIDU_OCR_FREE_QUOTA_SAFETY_BUFFER": serialize_value(settings.baidu_ocr_free_quota_safety_buffer),
        "BAIDU_OCR_TABLE_MONTHLY_FREE_LIMIT": serialize_value(settings.baidu_ocr_table_monthly_free_limit),
        "BAIDU_OCR_GENERAL_MONTHLY_FREE_LIMIT": serialize_value(settings.baidu_ocr_general_monthly_free_limit),
        "BAIDU_OCR_HANDWRITING_MONTHLY_FREE_LIMIT": serialize_value(settings.baidu_ocr_handwriting_monthly_free_limit),
        "AI_MATCH_MODE": "rule_first",
        "OCR_EXTRACT_MODE": "rule_first",
    }


async def load_setting_rows(db: AsyncSession) -> dict[str, SystemSetting]:
    """读取系统配置行。"""
    result = await db.execute(select(SystemSetting))
    return {row.key: row for row in result.scalars().all()}


async def get_effective_setting_values(db: AsyncSession) -> dict[str, str]:
    """获取数据库覆盖后的有效配置。"""
    values = build_default_values()
    rows = await load_setting_rows(db)
    for key, row in rows.items():
        if key in values and row.value is not None:
            values[key] = row.value
    return values


def build_runtime_settings(values: dict[str, str]) -> RuntimeSettings:
    """构建运行时配置快照。"""
    return RuntimeSettings(
        ai_enabled=parse_bool(values.get("AI_ENABLED")),
        openai_api_key=values.get("OPENAI_API_KEY", ""),
        openai_base_url=values.get("OPENAI_BASE_URL", ""),
        openai_chat_model=values.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        openai_embedding_model=values.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_provider=(values.get("EMBEDDING_PROVIDER", "openai") or "openai").lower(),
        dashscope_api_key=values.get("DASHSCOPE_API_KEY", ""),
        dashscope_base_url=values.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1"),
        dashscope_embedding_model=values.get("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4"),
        qianfan_api_key=values.get("QIANFAN_API_KEY", ""),
        qianfan_base_url=values.get("QIANFAN_BASE_URL", "https://qianfan.baidubce.com/v2"),
        qianfan_embedding_model=values.get("QIANFAN_EMBEDDING_MODEL", "embedding-v1"),
        baidu_ocr_app_id=values.get("BAIDU_OCR_APP_ID", ""),
        baidu_ocr_api_key=values.get("BAIDU_OCR_API_KEY", ""),
        baidu_ocr_secret_key=values.get("BAIDU_OCR_SECRET_KEY", ""),
        baidu_ocr_account_type=(values.get("BAIDU_OCR_ACCOUNT_TYPE", "personal") or "personal").lower(),
        baidu_ocr_free_quota_safety_buffer=parse_int(values.get("BAIDU_OCR_FREE_QUOTA_SAFETY_BUFFER"), 5),
        baidu_ocr_table_monthly_free_limit=parse_optional_int(values.get("BAIDU_OCR_TABLE_MONTHLY_FREE_LIMIT")),
        baidu_ocr_general_monthly_free_limit=parse_optional_int(values.get("BAIDU_OCR_GENERAL_MONTHLY_FREE_LIMIT")),
        baidu_ocr_handwriting_monthly_free_limit=parse_optional_int(
            values.get("BAIDU_OCR_HANDWRITING_MONTHLY_FREE_LIMIT")
        ),
        ai_match_mode=values.get("AI_MATCH_MODE", "rule_first") or "rule_first",
        ocr_extract_mode=values.get("OCR_EXTRACT_MODE", "rule_first") or "rule_first",
    )


async def get_runtime_settings(db: AsyncSession) -> RuntimeSettings:
    """读取运行时配置。"""
    values = await get_effective_setting_values(db)
    return build_runtime_settings(values)


def get_env_runtime_settings() -> RuntimeSettings:
    """只使用.env构建运行时配置。"""
    return build_runtime_settings(build_default_values())


async def safe_get_runtime_settings(db: AsyncSession) -> RuntimeSettings:
    """读取运行时配置，数据库不可用时回退.env。"""
    try:
        return await get_runtime_settings(db)
    except SQLAlchemyError:
        return get_env_runtime_settings()


async def upsert_system_settings(values: dict, operator: str, db: AsyncSession) -> None:
    """新增或更新系统配置。"""
    rows = await load_setting_rows(db)
    for key, value in values.items():
        if key not in SETTING_DEFINITIONS:
            continue
        definition = SETTING_DEFINITIONS[key]
        serialized_value = serialize_value(value)
        if definition.is_secret and serialized_value == "":
            continue
        row = rows.get(key)
        if row:
            row.value = serialized_value
            row.value_type = definition.value_type
            row.group_name = definition.group_name
            row.description = definition.description
            row.is_secret = 1 if definition.is_secret else 0
            row.updated_by = operator
            continue
        db.add(
            SystemSetting(
                key=key,
                value=serialized_value,
                value_type=definition.value_type,
                group_name=definition.group_name,
                description=definition.description,
                is_secret=1 if definition.is_secret else 0,
                updated_by=operator,
            )
        )
    await db.commit()


async def serialize_system_settings(db: AsyncSession) -> dict:
    """序列化系统配置供前端展示。"""
    values = await get_effective_setting_values(db)
    runtime = build_runtime_settings(values)
    items = {}
    for key, definition in SETTING_DEFINITIONS.items():
        value = values.get(key, "")
        items[key] = {
            "key": key,
            "value": mask_secret(value) if definition.is_secret else value,
            "configured": bool(value),
            "value_type": definition.value_type,
            "group_name": definition.group_name,
            "description": definition.description,
            "is_secret": definition.is_secret,
        }
    return {
        "runtime": {
            "ai_enabled": runtime.ai_enabled,
            "openai_api_key_configured": runtime.openai_api_key_configured,
            "openai_base_url": runtime.openai_base_url,
            "openai_chat_model": runtime.openai_chat_model,
            "openai_embedding_model": runtime.openai_embedding_model,
            "embedding_provider": runtime.embedding_provider,
            "dashscope_api_key_configured": runtime.dashscope_api_key_configured,
            "dashscope_base_url": runtime.dashscope_base_url,
            "dashscope_embedding_model": runtime.dashscope_embedding_model,
            "qianfan_api_key_configured": runtime.qianfan_api_key_configured,
            "qianfan_base_url": runtime.qianfan_base_url,
            "qianfan_embedding_model": runtime.qianfan_embedding_model,
            "baidu_ocr_app_id": runtime.baidu_ocr_app_id,
            "baidu_ocr_api_key_configured": runtime.baidu_ocr_api_key_configured,
            "baidu_ocr_secret_key_configured": runtime.baidu_ocr_secret_key_configured,
            "baidu_ocr_account_type": runtime.baidu_ocr_account_type,
            "baidu_ocr_free_quota_safety_buffer": runtime.baidu_ocr_free_quota_safety_buffer,
            "baidu_ocr_table_monthly_free_limit": runtime.baidu_ocr_table_monthly_free_limit,
            "baidu_ocr_general_monthly_free_limit": runtime.baidu_ocr_general_monthly_free_limit,
            "baidu_ocr_handwriting_monthly_free_limit": runtime.baidu_ocr_handwriting_monthly_free_limit,
            "ai_match_mode": runtime.ai_match_mode,
            "ocr_extract_mode": runtime.ocr_extract_mode,
        },
        "items": items,
    }
