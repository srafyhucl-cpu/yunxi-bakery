"""共享限流与登录防护测试：多连接、过期、重启、转发头边界。"""

import asyncio
import time

import pytest
from fastapi import Request

from app.config import settings
from app.database import close_db, db_session_scope, init_db
from app.middleware.edge_protection import extract_client_ip
from app.repository.edge_protection_repo import EdgeProtectionRepo


@pytest.fixture
async def edge_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """每个用例独享文件数据库，支持多连接并发。"""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "edge.db"))
    connection = await init_db(settings.DB_PATH)
    await close_db(connection)
    yield


def _scope(client_host: str, headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    """构造最小请求作用域。"""
    return {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/admin/orders",
        "headers": headers or [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": (client_host, 50000),
        "scheme": "http",
    }


@pytest.mark.asyncio
async def test_concurrent_requests_share_single_window(edge_db) -> None:
    """两连接并发计数共享窗口，超限精确拒绝。"""
    barrier = asyncio.Barrier(2)
    results: list[bool] = []

    async def attempt() -> None:
        async with db_session_scope():
            await barrier.wait()
            allowed = await EdgeProtectionRepo().check_request_allowed(
                "ratelimit:shared", int(time.time()), 60, 5
            )
            results.append(allowed)

    await asyncio.gather(*[attempt() for _ in range(10)])
    assert results.count(True) == 5
    assert results.count(False) == 5


@pytest.mark.asyncio
async def test_window_expiry_resets_count(edge_db) -> None:
    """窗口过期后计数重置，不沿用旧窗口。"""
    async with db_session_scope():
        repo = EdgeProtectionRepo()
        assert await repo.check_request_allowed("ratelimit:exp", 1000, 60, 1) is True
        assert await repo.check_request_allowed("ratelimit:exp", 1001, 60, 1) is False
        assert await repo.check_request_allowed("ratelimit:exp", 2000, 60, 1) is True


@pytest.mark.asyncio
async def test_state_survives_restart(edge_db) -> None:
    """新连接可见旧计数，重启不清空防护。"""
    async with db_session_scope():
        assert (
            await EdgeProtectionRepo().check_request_allowed(
                "ratelimit:restart", int(time.time()), 60, 1
            )
            is True
        )
    async with db_session_scope():
        assert (
            await EdgeProtectionRepo().check_request_allowed(
                "ratelimit:restart", int(time.time()), 60, 1
            )
            is False
        )


@pytest.mark.asyncio
async def test_admin_lock_unlock_and_expiry(edge_db) -> None:
    """登录失败计数锁定、成功清理、过期恢复。"""
    async with db_session_scope():
        repo = EdgeProtectionRepo()
        assert await repo.admin_login_allowed("admin:1.2.3.4", 1000, 3) is True
        await repo.record_admin_login_failure("admin:1.2.3.4", 1000, 300)
        await repo.record_admin_login_failure("admin:1.2.3.4", 1001, 300)
        await repo.record_admin_login_failure("admin:1.2.3.4", 1002, 300)
        assert await repo.admin_login_allowed("admin:1.2.3.4", 1003, 3) is False
        await repo.clear_admin_login_failures("admin:1.2.3.4")
        assert await repo.admin_login_allowed("admin:1.2.3.4", 1004, 3) is True
        await repo.record_admin_login_failure("admin:1.2.3.4", 1005, 300)
        await repo.record_admin_login_failure("admin:1.2.3.4", 1006, 300)
        await repo.record_admin_login_failure("admin:1.2.3.4", 1007, 300)
        assert await repo.admin_login_allowed("admin:1.2.3.4", 1008, 3) is False
        assert await repo.admin_login_allowed("admin:1.2.3.4", 2000, 3) is True


def test_forwarded_header_ignored_by_default(monkeypatch) -> None:
    """默认不信任转发头，伪造头无法绕过。"""
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 0)
    request = Request(
        _scope(
            "9.9.9.9",
            [(b"x-forwarded-for", b"1.1.1.1, 2.2.2.2")],
        )
    )
    assert extract_client_ip(request) == "9.9.9.9"


def test_forwarded_header_honored_when_configured(monkeypatch) -> None:
    """配置受信代理数量与网段后按层级取值，异常回退直连。"""
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 1)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_NETWORKS", "9.9.9.0/24")
    assert (
        extract_client_ip(
            Request(_scope("9.9.9.9", [(b"x-forwarded-for", b"1.1.1.1, 2.2.2.2")]))
        )
        == "2.2.2.2"
    )
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 2)
    assert (
        extract_client_ip(
            Request(_scope("9.9.9.9", [(b"x-forwarded-for", b"1.1.1.1, 2.2.2.2")]))
        )
        == "1.1.1.1"
    )
    assert extract_client_ip(Request(_scope("9.9.9.9"))) == "9.9.9.9"
    monkeypatch.setattr(settings, "TRUSTED_PROXY_COUNT", 5)
    assert (
        extract_client_ip(
            Request(_scope("9.9.9.9", [(b"x-forwarded-for", b"1.1.1.1")]))
        )
        == "9.9.9.9"
    )
