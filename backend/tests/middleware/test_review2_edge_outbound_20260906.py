"""复核第二轮 TDD 测试：登录原子占用、代理网段信任、Redis 存活探测、外发 owner 隔离。

每个测试先在本轮实现前失败，修复后通过；只断言真实运行行为。
"""

import asyncio

import pytest

from app.config import settings
from app.database import db_session_scope


@pytest.mark.asyncio
async def test_p12_concurrent_login_attempts_capped(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-2：并发登录尝试原子占用，通过门禁数不超过上限。"""
    from app.database import close_db, init_db
    from app.service import edge_protection as edge_service

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "edge-atomic.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    monkeypatch.setattr(edge_service.settings, "EDGE_PROTECTION_BACKEND", "sqlite")

    barrier = asyncio.Barrier(8)

    async def attempt() -> bool:
        await barrier.wait()
        return await edge_service.attempt_admin_login("admin:9.9.9.9", max_attempts=3)

    results = await asyncio.gather(*[attempt() for _ in range(8)])
    assert results.count(True) == 3
    assert results.count(False) == 5
    assert (
        await edge_service.attempt_admin_login("admin:9.9.9.9", max_attempts=3) is False
    )


def _request(host: str, headers: list[tuple[bytes, bytes]] | None = None):
    """构造最小请求作用域。"""
    from fastapi import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/x",
            "headers": headers or [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": (host, 50000),
            "scheme": "http",
        }
    )


def test_p13_direct_forgery_ignored_despite_count(monkeypatch) -> None:
    """P1-3：直连非受信网段时伪造转发头必须被忽略。"""
    from app.middleware import edge_protection as edge_module

    monkeypatch.setattr(edge_module.settings, "TRUSTED_PROXY_COUNT", 1)
    monkeypatch.setattr(edge_module.settings, "TRUSTED_PROXY_NETWORKS", "10.0.0.0/8")
    forged = _request("198.51.100.9", [(b"x-forwarded-for", b"1.2.3.4")])
    assert edge_module.extract_client_ip(forged) == "198.51.100.9"


def test_p13_trusted_proxy_chain_respected(monkeypatch) -> None:
    """P1-3：受信代理后的转发链按层级取值，超长伪造链回退直连。"""
    from app.middleware import edge_protection as edge_module

    monkeypatch.setattr(edge_module.settings, "TRUSTED_PROXY_COUNT", 2)
    monkeypatch.setattr(
        edge_module.settings, "TRUSTED_PROXY_NETWORKS", "10.0.0.0/8, 192.168.0.0/16"
    )
    legit = _request("10.1.2.3", [(b"x-forwarded-for", b"203.0.113.7, 10.9.9.9")])
    assert edge_module.extract_client_ip(legit) == "203.0.113.7"
    short = _request("10.1.2.3", [(b"x-forwarded-for", b"203.0.113.7")])
    assert edge_module.extract_client_ip(short) == "10.1.2.3"


@pytest.mark.asyncio
async def test_p14_redis_ping_unreachable_is_false() -> None:
    """P1-4：不可达 Redis 存活探测返回假，不抛错。"""
    from app.service.edge_protection import ping_edge_backend

    assert await ping_edge_backend("redis", "redis://127.0.0.1:9/0") is False


@pytest.mark.asyncio
async def test_p14_redis_ping_reachable_is_true() -> None:
    """P1-4：可达 RESP 服务存活探测返回真（本地伪服务器）。"""
    import asyncio as aio

    from app.service.edge_protection import ping_edge_backend

    async def _resp(reader: aio.StreamReader, writer: aio.StreamWriter) -> None:
        try:
            await reader.read(1024)
            writer.write(b"+PONG\r\n")
            await writer.drain()
        finally:
            writer.close()

    server = await aio.start_server(_resp, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        assert await ping_edge_backend("redis", f"redis://127.0.0.1:{port}/0") is True
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_p15_stale_worker_cannot_overwrite(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-5：旧 worker 迟到提交不得覆盖新一轮发送状态。"""
    from app.database import close_db, init_db
    from app.repository.wecom_kf_outbound_repo import WecomKfOutboundRepo
    from app.service.wecom.kf_outbound_sender import (
        build_outbound_key,
        request_manual_retry,
    )

    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "outbound-fence.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    key = build_outbound_key("in-fence-1", "text")
    async with db_session_scope():
        row, can_send = await WecomKfOutboundRepo().claim_for_send(
            key, "kf-1", "user-1", "in-fence-1", "text", "hash-1"
        )
        assert can_send is True
        stale_token = str(row["claim_token"])
    async with db_session_scope():
        await WecomKfOutboundRepo().mark_unknown(key, stale_token, "超时")
    async with db_session_scope():
        assert await request_manual_retry(key, "op-1", "人工确认") is True
    async with db_session_scope():
        fresh, can_send = await WecomKfOutboundRepo().claim_for_send(
            key, "kf-1", "user-1", "in-fence-1", "text", "hash-1"
        )
        assert can_send is True
        assert str(fresh["claim_token"]) != stale_token
        await WecomKfOutboundRepo().mark_sent(key, str(fresh["claim_token"]))
    async with db_session_scope():
        # 陈旧 token 的迟到成功标记必须被拒绝，终态保持新一轮 sent。
        assert await WecomKfOutboundRepo().mark_sent(key, stale_token) is False
        current = await WecomKfOutboundRepo().get(key)
        assert current is not None and current["status"] == "sent"
