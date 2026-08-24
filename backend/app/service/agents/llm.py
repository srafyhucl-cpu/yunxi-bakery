"""LangChain 聊天模型工厂。"""

from typing import Any

import httpx
from pydantic import SecretStr

from app.config import settings
from app.service.llm.provider import (
    LLMProvider,
    default_model,
    provider_api_key,
    provider_base_url,
    provider_timeout,
)

_MODEL_REGISTRY: dict[tuple[str, str, float, float], Any] = {}
_TRANSPORT_REGISTRY: dict[str, tuple[httpx.Client, httpx.AsyncClient]] = {}


def get_langchain_chat_model(
    *,
    provider: LLMProvider = "mimo",
    model: str = "",
    temperature: float = 0.0,
    timeout_seconds: float | None = None,
) -> Any:
    """延迟构造 LangChain ChatOpenAI，避免应用启动阶段加载重依赖。"""
    from langchain_openai import ChatOpenAI

    resolved_model = model or default_model(provider)
    resolved_timeout = timeout_seconds or provider_timeout(provider)
    cache_key = (provider, resolved_model, temperature, resolved_timeout)
    if cache_key not in _MODEL_REGISTRY:
        sync_client, async_client = _get_transport(provider)
        _MODEL_REGISTRY[cache_key] = ChatOpenAI(
            api_key=SecretStr(provider_api_key(provider)),
            base_url=provider_base_url(provider),
            model=resolved_model,
            temperature=temperature,
            timeout=resolved_timeout,
            http_client=sync_client,
            http_async_client=async_client,
            default_headers={"api-key": settings.MIMO_API_KEY}
            if provider == "mimo"
            else None,
        )
    return _MODEL_REGISTRY[cache_key]


def _get_transport(provider: LLMProvider) -> tuple[httpx.Client, httpx.AsyncClient]:
    transport = _TRANSPORT_REGISTRY.get(provider)
    if transport is None:
        transport = (httpx.Client(trust_env=False), httpx.AsyncClient(trust_env=False))
        _TRANSPORT_REGISTRY[provider] = transport
    return transport


async def close_langchain_chat_models() -> None:
    """释放 LangChain registry 共享的 HTTP transport。"""
    _MODEL_REGISTRY.clear()
    transports = tuple(_TRANSPORT_REGISTRY.values())
    _TRANSPORT_REGISTRY.clear()
    for sync_client, async_client in transports:
        sync_client.close()
        await async_client.aclose()
