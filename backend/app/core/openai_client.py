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


def extract_text_from_openai_response(response) -> str:
    """从OpenAI兼容响应中提取文本内容。"""
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        if isinstance(response.get("output_text"), str):
            return response["output_text"]
        choices = response.get("choices")
        if choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                return str(message.get("content") or "")
            if isinstance(choices[0], dict):
                return str(choices[0].get("text") or "")
        output = response.get("output")
        if isinstance(output, list):
            return extract_text_from_openai_output(output)

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return output_text

    choices = getattr(response, "choices", None)
    if choices:
        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        if message is not None:
            return str(getattr(message, "content", "") or "")
        return str(getattr(first_choice, "text", "") or "")

    output = getattr(response, "output", None)
    if isinstance(output, list):
        return extract_text_from_openai_output(output)

    return str(response)


def extract_text_from_openai_output(output_items: list) -> str:
    """从Responses API的output数组中提取文本。"""
    texts = []
    for item in output_items:
        content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
            else:
                text = getattr(part, "text", None)
            if text:
                texts.append(str(text))
    return "\n".join(texts)
