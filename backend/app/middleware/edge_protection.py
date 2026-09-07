"""请求体、并发、限流和安全响应头边界。"""

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.config import settings
from app.logger import setup_logger
from app.service.edge_protection import is_request_rate_limited

logger = setup_logger()

REQUEST_REJECTION_BODY = {"code": 41300, "message": "请求体超过服务端限制"}
CONCURRENCY_REJECTION_BODY = {"code": 50300, "message": "服务繁忙，请稍后重试"}
RATE_LIMIT_EXEMPT_PREFIXES = ("/health", "/ready", "/favicon.ico", "/static/")
_request_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_REQUESTS)


class RequestBodyTooLargeError(Exception):
    """请求体超过 ASGI 层限制。"""


async def edge_protection_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """执行请求体限制、并发保护、IP 限流和安全响应头。"""
    received_bytes = 0
    original_receive = request._receive

    async def limited_receive():
        nonlocal received_bytes
        message = await original_receive()
        if message.get("type") == "http.request":
            received_bytes += len(message.get("body", b""))
            if received_bytes > settings.MAX_REQUEST_BODY_BYTES:
                raise RequestBodyTooLargeError
        return message

    request._receive = limited_receive
    try:
        rate_limited = await _is_rate_limited(request)
    except Exception as exc:
        if _is_shared_backend_mode():
            _log_backend_error(exc)
            return _edge_backend_unavailable_response(request)
        raise
    if rate_limited:
        return _security_headers(
            request,
            JSONResponse(
                status_code=429, content={"code": 42900, "message": "请求过于频繁"}
            ),
        )
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            body_length = int(content_length)
        except ValueError:
            return _security_headers(
                request,
                JSONResponse(
                    status_code=400,
                    content={"code": 40000, "message": "请求长度无效"},
                ),
            )
        if body_length < 0 or body_length > settings.MAX_REQUEST_BODY_BYTES:
            return _security_headers(
                request, JSONResponse(status_code=413, content=REQUEST_REJECTION_BODY)
            )
    try:
        await asyncio.wait_for(
            _request_semaphore.acquire(),
            timeout=settings.REQUEST_ACQUIRE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return _security_headers(
            request, JSONResponse(status_code=503, content=CONCURRENCY_REJECTION_BODY)
        )
    try:
        response = await call_next(request)
    except RequestBodyTooLargeError:
        return _security_headers(
            request, JSONResponse(status_code=413, content=REQUEST_REJECTION_BODY)
        )
    finally:
        _request_semaphore.release()
    return _security_headers(request, response)


def extract_client_ip(request: Request) -> str:
    """提取客户端地址，默认只信连接地址，防止伪造转发头绕过。

    仅当运维显式配置受信代理数量，且直连地址落入受信代理网段时，
    才按层级取转发链对应位置；头缺失、位置不足、格式非法、非合法 IP、
    直连非受信代理一律回退到连接地址。
    """
    import ipaddress

    direct_host = request.client.host if request.client else "unknown"
    trusted_count = max(0, int(settings.TRUSTED_PROXY_COUNT or 0))
    if trusted_count <= 0:
        return direct_host
    if not _direct_host_is_trusted_proxy(direct_host):
        return direct_host
    forwarded = request.headers.get("x-forwarded-for", "")
    chain = [part.strip() for part in forwarded.split(",") if part.strip()]
    position = len(chain) - trusted_count
    if position < 0 or not chain:
        return direct_host
    candidate = chain[position]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return direct_host
    return candidate or direct_host


def _direct_host_is_trusted_proxy(direct_host: str) -> bool:
    """直连地址是否属于运维配置的受信代理网段。"""
    import ipaddress

    networks = [
        item.strip()
        for item in str(settings.TRUSTED_PROXY_NETWORKS or "").split(",")
        if item.strip()
    ]
    if not networks:
        return False
    try:
        address = ipaddress.ip_address(direct_host)
    except ValueError:
        return False
    for network in networks:
        try:
            if address in ipaddress.ip_network(network, strict=False):
                return True
        except ValueError:
            continue
    return False


async def _is_rate_limited(request: Request) -> bool:
    """按客户端地址执行共享存储请求窗口限流。"""
    if request.url.path.startswith(RATE_LIMIT_EXEMPT_PREFIXES):
        return False
    return await is_request_rate_limited(f"ratelimit:{extract_client_ip(request)}")


def _edge_backend_unavailable_response(request: Request) -> Response:
    """共享防护后端异常时的受控降级响应。"""
    return _security_headers(
        request,
        JSONResponse(
            status_code=503, content={"code": 50300, "message": "防护后端暂不可用"}
        ),
    )


def _is_shared_backend_mode() -> bool:
    """当前是否运行于共享防护后端模式。"""
    return str(settings.EDGE_PROTECTION_BACKEND or "").strip().lower() == "redis"


def _log_backend_error(exc: Exception) -> None:
    """记录共享防护后端异常，不泄露连接细节到响应。"""
    logger.error("共享边缘防护后端异常，已返回受控 503: %s", type(exc).__name__)


def _security_headers(request: Request, response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


__all__ = ["edge_protection_middleware", "extract_client_ip"]
