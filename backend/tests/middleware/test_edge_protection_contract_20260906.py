"""P1-3 边缘防护后端契约测试：本地显式、共享缺失 fail-closed、代理头校验。"""

import pytest
from fastapi import Request

from app.config import Settings
from app.exceptions import ConfigError
from app.middleware.edge_protection import extract_client_ip
from app.service import edge_protection as edge_service


def _scope(client_host: str, headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    """构造最小请求作用域。"""
    return {
        "type": "http",
        "method": "GET",
        "path": "/api/x",
        "headers": headers or [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": (client_host, 50000),
        "scheme": "http",
    }


def test_sqlite_is_explicit_local_default() -> None:
    """SQLite 只是显式的本地/单机后端默认值，不得冒充多机保护。"""
    assert Settings().EDGE_PROTECTION_BACKEND == "sqlite"
    assert Settings().EDGE_REQUIRE_SHARED is False


def test_require_shared_without_redis_fails_closed(monkeypatch) -> None:
    """生产要求共享而无可用后端时判定失败，不静默降级。"""
    monkeypatch.setattr(edge_service.settings, "EDGE_REQUIRE_SHARED", True)
    monkeypatch.setattr(edge_service.settings, "EDGE_PROTECTION_BACKEND", "sqlite")
    assert edge_service.is_edge_protection_shared() is False
    with pytest.raises(ConfigError):
        edge_service.assert_edge_protection_ready()


def test_require_shared_with_redis_url_reports_shared(monkeypatch) -> None:
    """配置共享地址即判共享就绪（连接失败由运行时抛错，不在此静默）。"""
    monkeypatch.setattr(edge_service.settings, "EDGE_REQUIRE_SHARED", True)
    monkeypatch.setattr(edge_service.settings, "EDGE_PROTECTION_BACKEND", "redis")
    monkeypatch.setattr(edge_service.settings, "EDGE_REDIS_URL", "redis://x/0")
    assert edge_service.is_edge_protection_shared() is True


def test_redis_backend_without_url_fails_closed(monkeypatch) -> None:
    """共享后端缺地址直接拒绝，不回退本地计数。"""
    monkeypatch.setattr(edge_service.settings, "EDGE_PROTECTION_BACKEND", "redis")
    monkeypatch.setattr(edge_service.settings, "EDGE_REDIS_URL", "")
    with pytest.raises(ConfigError):
        edge_service._get_redis_repo()


def test_forged_forwarded_chain_falls_back_to_direct(monkeypatch) -> None:
    """伪造转发头在默认零信任下被忽略，非法 IP 回退直连。"""
    monkeypatch.setattr(edge_service.settings, "TRUSTED_PROXY_COUNT", 0)
    request = Request(
        _scope(
            "10.0.0.9",
            [(b"x-forwarded-for", b"1.2.3.4, 5.6.7.8")],
        )
    )
    assert extract_client_ip(request) == "10.0.0.9"


def test_trusted_proxy_rejects_invalid_ip(monkeypatch) -> None:
    """受信代理层级命中非法 IP 时回退直连，不采用伪造值。"""
    monkeypatch.setattr(edge_service.settings, "TRUSTED_PROXY_COUNT", 1)
    monkeypatch.setattr(edge_service.settings, "TRUSTED_PROXY_NETWORKS", "10.0.0.0/8")
    request = Request(_scope("10.0.0.9", [(b"x-forwarded-for", b"not-an-ip")]))
    assert extract_client_ip(request) == "10.0.0.9"
    valid = Request(_scope("10.0.0.9", [(b"x-forwarded-for", b"203.0.113.7")]))
    assert extract_client_ip(valid) == "203.0.113.7"
