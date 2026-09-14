"""有赞网关错误处理回归测试。

网关拒绝调用时响应体只有 ``gw_err_resp``，没有业务 data；客户端必须显式失败，
不能把鉴权或 IP 白名单问题当成“店铺没有数据”。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.config import settings
from app.exceptions import APIError
from app.service.youzan.client import (
    YouzanClient,
    build_gateway_error_message,
    extract_gateway_error,
)

IP_BLOCKED_PAYLOAD: dict[str, Any] = {
    "gw_err_resp": {
        "trace_id": "yz7-test-trace",
        "err_msg": (
            "源IP地址1.2.3.4非法调用有赞云，请完成IP地址确认后，"
            "前往应用中心控制台进行IP白名单配置"
        ),
        "err_code": 4007,
    }
}
ACCESS_TOKEN = "secret-token-value"


class _FakeResponse:
    """模拟 httpx 响应，只暴露 _call 读取的字段。"""

    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeHTTPClient:
    """记录请求并返回固定响应，避免测试触达真实有赞网关。"""

    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self._status_code = status_code
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"url": url, "json": kwargs.get("json")})
        return _FakeResponse(self._payload, self._status_code)


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    status_code: int = 200,
) -> tuple[YouzanClient, _FakeHTTPClient]:
    """构造关闭 Mock 且不触网的客户端。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = YouzanClient()
    fake_http = _FakeHTTPClient(payload, status_code)

    async def fake_get_token() -> str:
        return ACCESS_TOKEN

    monkeypatch.setattr(client, "get_token", fake_get_token)
    setattr(client, "_http", fake_http)
    return client, fake_http


def test_extract_gateway_error_reads_gateway_payload() -> None:
    error = extract_gateway_error(IP_BLOCKED_PAYLOAD)

    assert error is not None
    assert error["err_code"] == 4007
    assert error["trace_id"] == "yz7-test-trace"


def test_extract_gateway_error_ignores_business_empty_result() -> None:
    assert extract_gateway_error({"data": {"items": []}}) is None
    assert extract_gateway_error({"response": {"tags": []}}) is None
    assert extract_gateway_error(None) is None


def test_build_gateway_error_message_flags_whitelist_and_masks_token() -> None:
    message = build_gateway_error_message(
        "youzan.items.onsale.get",
        {"err_code": 4007, "err_msg": f"access_token={ACCESS_TOKEN} 调用被拒绝"},
    )

    assert "err_code=4007" in message
    assert "IP 白名单" in message
    assert ACCESS_TOKEN not in message
    assert "access_token=***" in message


async def test_call_keeps_raw_payload_for_existing_gateway_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 单品查询等旧调用点已自行识别 gw_err_resp，_call 不改变它们的返回合同
    client, _ = _build_client(monkeypatch, IP_BLOCKED_PAYLOAD)

    result = await client._call("youzan.item.get", "3.0.0", {})

    assert result == IP_BLOCKED_PAYLOAD


async def test_list_onsale_items_raises_instead_of_returning_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _build_client(monkeypatch, IP_BLOCKED_PAYLOAD)

    with pytest.raises(APIError) as excinfo:
        await client.list_onsale_items()

    assert "err_code=4007" in str(excinfo.value)
    assert "yz7-test-trace" in str(excinfo.value)


async def test_catalog_sync_queries_raise_on_gateway_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for call in (
        lambda c: c.list_product_tags(),
        lambda c: c.search_item_base([101]),
        lambda c: c.search_item_classifications(),
    ):
        client, _ = _build_client(monkeypatch, IP_BLOCKED_PAYLOAD)
        with pytest.raises(APIError):
            await call(client)


async def test_call_returns_business_payload_when_gateway_accepts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload: dict[str, Any] = {"data": {"items": [], "count": 0}}
    client, fake_http = _build_client(monkeypatch, payload)

    result = await client._call("youzan.items.onsale.get", "3.0.1", {})

    assert result == payload
    assert fake_http.calls[0]["json"] == {}
