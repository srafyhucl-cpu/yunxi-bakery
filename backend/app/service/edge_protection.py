"""边缘防护应用服务：限流与登录保护的共享状态入口。

API 与中间件只允许调用本服务，不得直连仓储。

后端契约：
- sqlite：明确的本地/单机模式，多进程共享同一库文件，多机无效。
- redis：多机共享模式，原子 Lua 操作，缺依赖或缺地址即 fail-closed。
生产要求共享防护（EDGE_REQUIRE_SHARED=true）而后端不可用时，
readiness、preflight、startup 共用同一判定函数失败，不再各说各话。
配置完整不等于后端可用：共享模式另有异步 PING 存活探测，
启动与预检必须通过探测，中间件异常返回受控 503。
"""

import asyncio
import time
from urllib.parse import urlparse

from app.config import settings
from app.database import db_session_scope
from app.exceptions import ConfigError
from app.repository.edge_protection_repo import EdgeProtectionRepo

_redis_repo = None


def is_edge_protection_shared() -> bool:
    """共享防护是否就绪：唯一判定函数，供三处门禁共用。"""
    if str(settings.EDGE_PROTECTION_BACKEND or "").strip().lower() != "redis":
        return False
    return bool(str(settings.EDGE_REDIS_URL or "").strip())


def assert_edge_protection_ready() -> None:
    """生产要求共享防护时做 fail-closed 判定，不可用直接抛配置错误。"""
    if not bool(settings.EDGE_REQUIRE_SHARED):
        return
    if not is_edge_protection_shared():
        raise ConfigError(
            "生产要求共享边缘防护（EDGE_REQUIRE_SHARED=true），"
            "但未配置可用 Redis 后端（EDGE_PROTECTION_BACKEND=redis 与 EDGE_REDIS_URL）"
        )
    try:
        _get_redis_repo()
    except ConfigError:
        raise


def _get_redis_repo():
    """按需构造共享后端，缺依赖即抛配置错误。"""
    global _redis_repo
    if _redis_repo is None:
        from app.repository.edge_protection_redis_repo import RedisEdgeProtectionRepo

        _redis_repo = RedisEdgeProtectionRepo(str(settings.EDGE_REDIS_URL or ""))
    return _redis_repo


def _use_shared_backend() -> bool:
    """运行时是否走共享后端（含 fail-closed 校验）。"""
    if str(settings.EDGE_PROTECTION_BACKEND or "").strip().lower() != "redis":
        return False
    _get_redis_repo()
    return True


async def ping_edge_backend(
    backend: str | None = None,
    redis_url: str | None = None,
    timeout_seconds: float = 2.0,
) -> bool:
    """探测共享后端可用性：sqlite 本地模式直接就绪，redis 执行真实 PING。

    使用裸 RESP 协议，不引入 redis 依赖；不可达、超时、认证失败一律
    返回假，由调用方按 fail-closed 处理。
    """
    resolved_backend = (
        (
            str(settings.EDGE_PROTECTION_BACKEND or "")
            if backend is None
            else str(backend or "")
        )
        .strip()
        .lower()
    )
    if resolved_backend != "redis":
        return True
    url = (
        str(settings.EDGE_REDIS_URL or "")
        if redis_url is None
        else str(redis_url or "")
    ).strip()
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or 6379
        password = parsed.password or ""
        if not host:
            return False
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout_seconds
        )
        try:
            if password:
                writer.write(
                    f"*2\r\n$4\r\nAUTH\r\n${len(password.encode())}\r\n{password}\r\n".encode()
                )
                await writer.drain()
                line = await asyncio.wait_for(reader.readline(), timeout_seconds)
                if not line.startswith(b"+OK"):
                    return False
            writer.write(b"*1\r\n$4\r\nPING\r\n")
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout_seconds)
            return line.startswith(b"+PONG")
        finally:
            writer.close()
    except Exception:
        return False


async def is_request_rate_limited(client_key: str) -> bool:
    """按客户端键执行共享窗口限流，超限返回真。"""
    if _use_shared_backend():
        allowed = await _get_redis_repo().check_request_allowed(
            client_key,
            int(time.time()),
            int(settings.REQUEST_RATE_LIMIT_WINDOW_SECONDS),
            int(settings.REQUEST_RATE_LIMIT_MAX_REQUESTS),
        )
        return not allowed
    async with db_session_scope():
        allowed = await EdgeProtectionRepo().check_request_allowed(
            client_key,
            int(time.time()),
            int(settings.REQUEST_RATE_LIMIT_WINDOW_SECONDS),
            int(settings.REQUEST_RATE_LIMIT_MAX_REQUESTS),
        )
    return not allowed


async def is_admin_login_allowed(client_key: str) -> bool:
    """登录失败未超阈或窗口过期则放行。"""
    if _use_shared_backend():
        return await _get_redis_repo().admin_login_allowed(
            client_key,
            int(time.time()),
            int(settings.ADMIN_LOGIN_MAX_ATTEMPTS),
        )
    async with db_session_scope():
        return await EdgeProtectionRepo().admin_login_allowed(
            client_key,
            int(time.time()),
            int(settings.ADMIN_LOGIN_MAX_ATTEMPTS),
        )


async def record_admin_login_failure(client_key: str) -> None:
    """记录一次登录失败（兼容旧两步调用，新链路请用 attempt_admin_login）。"""
    if _use_shared_backend():
        await _get_redis_repo().record_admin_login_failure(
            client_key,
            int(time.time()),
            int(settings.ADMIN_LOGIN_WINDOW_SECONDS),
        )
        return
    async with db_session_scope():
        await EdgeProtectionRepo().record_admin_login_failure(
            client_key,
            int(time.time()),
            int(settings.ADMIN_LOGIN_WINDOW_SECONDS),
        )


async def attempt_admin_login(client_key: str, max_attempts: int | None = None) -> bool:
    """原子占用一次后台登录尝试，返回是否放行。

    检查与计数同一原子操作完成，并发尝试精确放行前 max 个；
    每次登录请求（含成功）先占用，成功后由调用方清理计数。
    """
    limit = settings.ADMIN_LOGIN_MAX_ATTEMPTS if max_attempts is None else max_attempts
    if _use_shared_backend():
        return await _get_redis_repo().check_and_record_login_attempt(
            client_key,
            int(time.time()),
            int(settings.ADMIN_LOGIN_WINDOW_SECONDS),
            int(limit),
        )
    async with db_session_scope():
        return await EdgeProtectionRepo().check_and_record_login_attempt(
            client_key,
            int(time.time()),
            int(settings.ADMIN_LOGIN_WINDOW_SECONDS),
            int(limit),
        )


async def clear_admin_login_failures(client_key: str) -> None:
    """成功登录后清理失败计数。"""
    if _use_shared_backend():
        await _get_redis_repo().clear_admin_login_failures(client_key)
        return
    async with db_session_scope():
        await EdgeProtectionRepo().clear_admin_login_failures(client_key)
