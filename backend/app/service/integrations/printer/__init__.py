"""打印网关工厂。"""

from app.service.integrations.printer.base import (
    PrinterConfigurationError,
    PrinterGateway,
)
from app.service.integrations.printer.feieyun import FeieyunPrinterGateway
from app.service.integrations.printer.mock import MockPrinterGateway


def build_printer_gateway(settings) -> PrinterGateway:
    """按 PRINT_PROVIDER 构造网关；未知值直接报配置错误。"""
    provider = str(getattr(settings, "PRINT_PROVIDER", "mock") or "").strip().lower()
    if provider == MockPrinterGateway.name:
        return MockPrinterGateway()
    if provider == FeieyunPrinterGateway.name:
        return FeieyunPrinterGateway()
    raise PrinterConfigurationError(f"未知打印网关: {provider or '(empty)'}")


__all__ = ["build_printer_gateway"]
