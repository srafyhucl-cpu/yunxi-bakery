"""Mock 打印网关。

用于本地开发与测试：只记录“已受理”，状态固定为 MOCKED，
绝不伪装成真实打印成功（PRINTED）。
"""

from uuid import uuid4

from app.models.print_job import PrintJobStatus, PrintResult, PrintTicket
from app.service.integrations.printer.base import PrinterGateway


class MockPrinterGateway(PrinterGateway):
    """不连接任何打印机的确定性网关。"""

    name = "mock"

    async def submit(self, ticket: PrintTicket, printer_id: str) -> PrintResult:
        """返回 Mock 受理结果，provider_job_id 便于追踪。"""
        return PrintResult(
            success=True,
            status=PrintJobStatus.MOCKED.value,
            provider_job_id=f"mock-{uuid4().hex}",
        )


__all__ = ["MockPrinterGateway"]
