from openai import OpenAI

from app.core.config import get_settings


def create_openai_client(api_key: str | None = None, base_url: str | None = None) -> OpenAI:
    """创建OpenAI兼容客户端，支持中转站base_url。"""
    settings = get_settings()
    final_api_key = api_key if api_key is not None else settings.openai_api_key
    final_base_url = base_url if base_url is not None else settings.openai_base_url
    client_kwargs = {"api_key": final_api_key}
    if final_base_url:
        client_kwargs["base_url"] = final_base_url
    return OpenAI(**client_kwargs)
