"""告警 HTTP 传输适配合同测试。"""

import pytest

from app.service import alerting


@pytest.mark.asyncio
async def test_alerting_uses_httpx_transport(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        status_code = 200
        text = "ok"

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url: str, *, json: dict) -> _Response:
            captured["url"] = url
            captured["payload"] = json
            return _Response()

    monkeypatch.setattr(alerting.httpx, "AsyncClient", lambda **_kwargs: _Client())
    service = alerting.AlertService("https://alerts.example/hook")

    await service.alert(
        alerting.AlertLevel.WARNING,
        "测试告警",
        "合成测试",
        key="alerting-httpx-contract",
    )

    assert captured["url"] == "https://alerts.example/hook"
    assert captured["payload"]["msgtype"] == "markdown"
