"""统一的文本模型 provider 与默认模型解析。"""

from typing import Literal

from app.config import settings

LLMProvider = Literal["mimo", "deepseek"]


def resolve_provider_model(model: str = "") -> tuple[LLMProvider, str]:
    """解析显式模型，空模型统一使用 MiMo 默认值。"""
    normalized_model = model.strip()
    if not normalized_model:
        return "mimo", settings.MIMO_CHAT_MODEL
    if "mimo" in normalized_model.lower():
        return "mimo", normalized_model
    return "deepseek", normalized_model


def default_model(provider: LLMProvider) -> str:
    """返回指定 provider 的配置模型。"""
    return settings.MIMO_CHAT_MODEL if provider == "mimo" else settings.DEEPSEEK_MODEL


def provider_timeout(provider: LLMProvider) -> float:
    """返回指定 provider 的请求超时。"""
    return (
        settings.MIMO_TIMEOUT_SECONDS
        if provider == "mimo"
        else settings.DEEPSEEK_TIMEOUT_SECONDS
    )


def provider_api_key(provider: LLMProvider) -> str:
    """返回指定 provider 的 API key。"""
    return settings.MIMO_API_KEY if provider == "mimo" else settings.DEEPSEEK_API_KEY


def provider_base_url(provider: LLMProvider) -> str:
    """返回指定 provider 的 API base URL。"""
    return settings.MIMO_BASE_URL if provider == "mimo" else settings.DEEPSEEK_BASE_URL


def select_llm_model(has_image: bool) -> str:
    """选择文本或视觉模型，空字符串表示使用 provider 默认文本模型。"""
    if not has_image:
        return ""
    return settings.MIMO_VISION_MODEL or settings.MIMO_CHAT_MODEL
