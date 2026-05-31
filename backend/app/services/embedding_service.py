from collections.abc import Iterable
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.openai_client import create_openai_client


EMBEDDING_BATCH_SIZE = 50
DASHSCOPE_BATCH_SIZE = 10
SUPPORTED_PROVIDERS = {"openai", "dashscope", "qianfan"}


def chunked(items: list[str], batch_size: int) -> Iterable[list[str]]:
    """按批次切分文本列表。"""
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def get_runtime_value(runtime_settings, key: str, default: str = "") -> str:
    """优先读取运行时配置，其次读取.env配置。"""
    settings = get_settings()
    value = getattr(runtime_settings, key, None) if runtime_settings is not None else None
    if value is not None and str(value).strip() != "":
        return str(value).strip()
    return str(getattr(settings, key, default) or default).strip()


def get_embedding_provider(runtime_settings=None) -> str:
    """读取向量供应商。"""
    provider = get_runtime_value(runtime_settings, "embedding_provider", "openai").lower()
    aliases = {
        "openai-compatible": "openai",
        "openai_compatible": "openai",
        "aliyun": "dashscope",
        "ali": "dashscope",
        "baidu": "qianfan",
    }
    return aliases.get(provider, provider)


def create_openai_embeddings(texts: list[str], runtime_settings=None) -> list[list[float]]:
    """调用OpenAI兼容接口生成向量。"""
    api_key = get_runtime_value(runtime_settings, "openai_api_key")
    base_url = get_runtime_value(runtime_settings, "openai_base_url")
    model = get_runtime_value(runtime_settings, "openai_embedding_model", "text-embedding-3-small")
    client = create_openai_client(api_key=api_key or None, base_url=base_url or None)
    embeddings: list[list[float]] = []
    for batch in chunked(texts, EMBEDDING_BATCH_SIZE):
        response = client.embeddings.create(model=model, input=batch)
        embeddings.extend([item.embedding for item in response.data])
    return embeddings


def parse_indexed_embeddings(items: list[dict[str, Any]]) -> list[list[float]]:
    """解析带index或text_index的向量数组。"""
    if not items:
        return []
    if all("index" in item for item in items):
        ordered = sorted(items, key=lambda item: int(item.get("index", 0)))
    elif all("text_index" in item for item in items):
        ordered = sorted(items, key=lambda item: int(item.get("text_index", 0)))
    else:
        ordered = items
    return [item["embedding"] for item in ordered if "embedding" in item]


def create_dashscope_embeddings(
    texts: list[str],
    runtime_settings=None,
    text_type: str = "document",
) -> list[list[float]]:
    """调用阿里百炼DashScope原生接口生成向量。"""
    api_key = get_runtime_value(runtime_settings, "dashscope_api_key")
    if not api_key:
        raise RuntimeError("未配置DASHSCOPE_API_KEY，无法使用阿里百炼向量服务")
    base_url = get_runtime_value(runtime_settings, "dashscope_base_url", "https://dashscope.aliyuncs.com/api/v1").rstrip("/")
    model = get_runtime_value(runtime_settings, "dashscope_embedding_model", "text-embedding-v4")
    url = f"{base_url}/services/embeddings/text-embedding/text-embedding"
    embeddings: list[list[float]] = []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60) as client:
        for batch in chunked(texts, DASHSCOPE_BATCH_SIZE):
            response = client.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "input": {"texts": batch},
                    "parameters": {"text_type": text_type, "output_type": "dense"},
                },
            )
            response.raise_for_status()
            payload = response.json()
            batch_embeddings = parse_indexed_embeddings(payload.get("output", {}).get("embeddings", []))
            if len(batch_embeddings) != len(batch):
                raise RuntimeError("阿里百炼向量接口返回数量与请求文本数量不一致")
            embeddings.extend(batch_embeddings)
    return embeddings


def create_qianfan_embeddings(texts: list[str], runtime_settings=None) -> list[list[float]]:
    """调用百度千帆v2接口生成向量。"""
    api_key = get_runtime_value(runtime_settings, "qianfan_api_key")
    if not api_key:
        raise RuntimeError("未配置QIANFAN_API_KEY，无法使用百度千帆向量服务")
    base_url = get_runtime_value(runtime_settings, "qianfan_base_url", "https://qianfan.baidubce.com/v2").rstrip("/")
    model = get_runtime_value(runtime_settings, "qianfan_embedding_model", "embedding-v1")
    url = f"{base_url}/embeddings"
    embeddings: list[list[float]] = []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60) as client:
        for batch in chunked(texts, EMBEDDING_BATCH_SIZE):
            response = client.post(url, headers=headers, json={"model": model, "input": batch})
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", [])
            batch_embeddings = parse_indexed_embeddings(data)
            if len(batch_embeddings) != len(batch):
                raise RuntimeError("百度千帆向量接口返回数量与请求文本数量不一致")
            embeddings.extend(batch_embeddings)
    return embeddings


def create_embeddings(
    texts: list[str],
    runtime_settings=None,
    text_type: str = "document",
) -> list[list[float]]:
    """按配置选择向量供应商并生成向量。"""
    if not texts:
        return []
    provider = get_embedding_provider(runtime_settings)
    if provider not in SUPPORTED_PROVIDERS:
        raise RuntimeError(f"不支持的向量供应商: {provider}")
    if provider == "dashscope":
        return create_dashscope_embeddings(texts, runtime_settings=runtime_settings, text_type=text_type)
    if provider == "qianfan":
        return create_qianfan_embeddings(texts, runtime_settings=runtime_settings)
    return create_openai_embeddings(texts, runtime_settings=runtime_settings)


def create_embedding(text: str, runtime_settings=None, text_type: str = "query") -> list[float]:
    """生成单条文本向量。"""
    vectors = create_embeddings([text], runtime_settings=runtime_settings, text_type=text_type)
    return vectors[0] if vectors else []
