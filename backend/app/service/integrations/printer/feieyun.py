"""飞鹅云打印网关。

飞鹅 Open_printMsg 返回 ret=0 仅表示云端已接收，因此作业最多标记
SUBMITTED，不能直接视为真实出纸（PRINTED）。
"""

import hashlib
import time

import httpx

from app.config import settings
from app.models.print_job import PrintJobStatus, PrintResult, PrintTicket
from app.service.integrations.printer.base import (
    PrinterConfigurationError,
    PrinterGateway,
)

FEIEYUN_PRINT_API_NAME = "Open_printMsg"


class FeieyunPrinterGateway(PrinterGateway):
    """飞鹅云打印 HTTP 网关。"""

    name = "feieyun"

    def __init__(
        self,
        *,
        user: str | None = None,
        ukey: str | None = None,
        sn: str | None = None,
        api_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._user = settings.FEIEYUN_USER if user is None else user
        self._ukey = settings.FEIEYUN_UKEY if ukey is None else ukey
        self._sn = settings.FEIEYUN_SN if sn is None else sn
        self._api_url = (
            settings.FEIEYUN_API_URL.rstrip("/") if api_url is None else api_url
        )
        self._timeout_seconds = (
            settings.FEIEYUN_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )
        self._ensure_configured()

    def _ensure_configured(self) -> None:
        """凭证不完整时明确报错，绝不静默成功。"""
        missing = [
            name
            for name, value in (
                ("FEIEYUN_USER", self._user),
                ("FEIEYUN_UKEY", self._ukey),
                ("FEIEYUN_SN", self._sn),
                ("FEIEYUN_API_URL", self._api_url),
            )
            if not str(value or "").strip()
        ]
        if missing:
            raise PrinterConfigurationError("飞鹅云打印配置缺失: " + ", ".join(missing))

    def _build_signature(self, stime: str) -> str:
        """按飞鹅协议计算 sha1(user + ukey + stime)。"""
        raw = f"{self._user}{self._ukey}{stime}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    async def submit(self, ticket: PrintTicket, printer_id: str) -> PrintResult:
        """提交小票；云端 ret=0 返回 SUBMITTED。"""
        self._ensure_configured()
        stime = str(int(time.time()))
        data = {
            "user": self._user,
            "stukey": self._ukey,
            "stime": stime,
            "sig": self._build_signature(stime),
            "apiname": FEIEYUN_PRINT_API_NAME,
            "sn": printer_id or self._sn,
            "content": ticket.content,
            "times": "1",
        }
        response = await self._post_form(data)
        if str(response.get("ret", "")).strip() != "0":
            error = str(response.get("msg") or response.get("data") or "飞鹅云打印失败")
            return PrintResult(
                success=False, status=PrintJobStatus.FAILED.value, error=error
            )
        return PrintResult(
            success=True,
            status=PrintJobStatus.SUBMITTED.value,
            provider_job_id=str(response.get("data", "")),
        )

    async def _post_form(self, data: dict) -> dict:
        """发送表单请求，单独抽出便于测试替换，禁止测试访问真实网络。"""
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            trust_env=False,
        ) as client:
            response = await client.post(self._api_url, data=data)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("飞鹅云打印返回 JSON 格式无效")
        return payload


__all__ = ["FEIEYUN_PRINT_API_NAME", "FeieyunPrinterGateway"]
