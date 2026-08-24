"""请求体、并发、限流和安全响应头边界。"""

import asyncio
import time
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.config import settings

REQUEST_REJECTION_BODY = {"code": 41300, "message": "请求体超过服务端限制"}
CONCURRENCY_REJECTION_BODY = {"code": 50300, "message": "服务繁忙，请稍后重试"}
RATE_LIMIT_EXEMPT_PREFIXES = ("/health", "/ready", "/favicon.ico", "/static/")
_request_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_REQUESTS)
_request_rate_limits: dict[str, tuple[int, float]] = {}


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
    if _is_rate_limited(request):
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


def _is_rate_limited(request: Request) -> bool:
    """按客户端地址执行单进程请求窗口限流。"""
    if request.url.path.startswith(RATE_LIMIT_EXEMPT_PREFIXES):
        return False
    client_host = request.client.host if request.client else "unknown"
    request_count, reset_at = _request_rate_limits.get(client_host, (0, 0.0))
    current_time = time.monotonic()
    if current_time >= reset_at:
        _request_rate_limits[client_host] = (
            1,
            current_time + settings.REQUEST_RATE_LIMIT_WINDOW_SECONDS,
        )
        return False
    request_count += 1
    _request_rate_limits[client_host] = (request_count, reset_at)
    return request_count > settings.REQUEST_RATE_LIMIT_MAX_REQUESTS


def _security_headers(request: Request, response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


__all__ = ["_request_rate_limits", "edge_protection_middleware"]
