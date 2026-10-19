"""打印网关抽象。"""

from abc import ABC, abstractmethod

from app.models.print_job import PrintResult, PrintTicket


class PrinterConfigurationError(RuntimeError):
    """打印网关配置缺失或不可用。"""


class PrinterGateway(ABC):
    """打印网关统一接口。"""

    name: str = ""

    @abstractmethod
    async def submit(self, ticket: PrintTicket, printer_id: str) -> PrintResult:
        """提交一张小票；返回云端受理结果，不承诺真实出纸。"""
        raise NotImplementedError


__all__ = ["PrinterConfigurationError", "PrinterGateway"]
