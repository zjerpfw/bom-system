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
    ai_match_mode: str
    ocr_extract_mode: str

    @property
    def openai_api_key_configured(self) -> bool:
        """判断OpenAI密钥是否已配置。"""
        return bool(self.openai_api_key)


SETTING_DEFINITIONS = {
    "AI_ENABLED": SettingDefinition("AI_ENABLED", "bool", "ai", "是否启用AI增强能力"),
    "OPENAI_API_KEY": SettingDefinition("OPENAI_API_KEY", "secret", "ai", "OpenAI或中转站密钥", True),
    "OPENAI_BASE_URL": SettingDefinition("OPENAI_BASE_URL", "string", "ai", "OpenAI兼容接口地址"),
    "OPENAI_CHAT_MODEL": SettingDefinition("OPENAI_CHAT_MODEL", "string", "ai", "聊天和推理模型"),
    "OPENAI_EMBEDDING_MODEL": SettingDefinition("OPENAI_EMBEDDING_MODEL", "string", "ai", "向量模型"),
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
            "ai_match_mode": runtime.ai_match_mode,
            "ocr_extract_mode": runtime.ocr_extract_mode,
        },
        "items": items,
    }
