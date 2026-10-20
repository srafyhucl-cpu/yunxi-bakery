"""飞鹅云打印网关测试（不访问真实网络）。"""

import hashlib

import pytest

from app.models.print_job import PrintTicket
from app.service.integrations.printer.feieyun import FeieyunPrinterGateway
from app.service.integrations.printer.base import PrinterConfigurationError

TICKET = PrintTicket(
    ticket_type="CAKE_KITCHEN",
    content="【裱花间制作联】\n8寸 草莓 生日快乐",
)


def _gateway() -> FeieyunPrinterGateway:
    return FeieyunPrinterGateway(
        user="feie-user",
        ukey="feie-ukey",
        sn="feie-sn",
        api_url="https://example.invalid/Api/Open/",
        timeout_seconds=3,
    )


async def test_submit_builds_signed_form_and_submitted(
    monkeypatch,
) -> None:
    """表单字段与签名正确，ret=0 只标记 SUBMITTED。"""
    gateway = _gateway()
    captured: dict = {}

    async def fake_post(data: dict) -> dict:
        captured.update(data)
        return {"ret": 0, "data": "cloud-job-001", "msg": "ok"}

    monkeypatch.setattr(gateway, "_post_form", fake_post)

    result = await gateway.submit(TICKET, "printer-override")

    assert result.success is True
    assert result.status == "SUBMITTED"
    assert result.provider_job_id == "cloud-job-001"
    assert captured["user"] == "feie-user"
    assert captured["stukey"] == "feie-ukey"
    assert captured["apiname"] == "Open_printMsg"
    assert captured["sn"] == "printer-override"
    assert captured["content"] == TICKET.content
    assert str(captured["times"]) == "1"
    expected_sig = hashlib.sha1(
        f"feie-userfeie-ukey{captured['stime']}".encode("utf-8")
    ).hexdigest()
    assert captured["sig"] == expected_sig


async def test_submit_non_zero_ret_returns_failure(monkeypatch) -> None:
    """飞鹅 ret 非 0 时返回失败并保留错误信息。"""
    gateway = _gateway()

    async def fake_post(data: dict) -> dict:
        return {"ret": 1001, "msg": "打印机不在线"}

    monkeypatch.setattr(gateway, "_post_form", fake_post)

    result = await gateway.submit(TICKET, "")

    assert result.success is False
    assert result.status == "FAILED"
    assert "打印机不在线" in result.error


def test_missing_credentials_raise_configuration_error() -> None:
    """凭证缺失时构造即报明确配置错误，不能静默成功。"""
    with pytest.raises(PrinterConfigurationError, match="FEIEYUN"):
        FeieyunPrinterGateway(user="", ukey="", sn="", api_url="")
