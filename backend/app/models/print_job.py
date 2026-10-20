"""打印作业模型。

打印作业只表达“交给打印网关”的意图与结果，不代表打印机已经出纸。
Mock 网关最高只到 MOCKED，飞鹅网关成功也只到 SUBMITTED。
"""

from dataclasses import dataclass
from enum import Enum


class PrintTicketType(str, Enum):
    """小票类型：裱花间制作联 / 日常现烤配送联。"""

    CAKE_KITCHEN = "CAKE_KITCHEN"
    DAILY_FRONT = "DAILY_FRONT"


class PrintJobStatus(str, Enum):
    """打印作业状态机。"""

    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    SUBMITTED = "SUBMITTED"
    PRINTED = "PRINTED"
    FAILED = "FAILED"
    MOCKED = "MOCKED"
    CANCELLED = "CANCELLED"


@dataclass
class OrderPrintJob:
    """order_print_jobs 表的数据容器。"""

    id: str
    order_id: str
    ticket_type: str
    status: str = PrintJobStatus.PENDING.value
    provider: str = ""
    printer_id: str = ""
    attempts: int = 0
    last_error: str = ""
    provider_job_id: str = ""
    idempotency_key: str = ""
    payload_snapshot: str = ""
    operator: str = ""
    created_at: str = ""
    updated_at: str = ""
    printed_at: str = ""


@dataclass
class PrintResult:
    """打印网关提交结果。

    success 表示网关已受理或 Mock 已记录，不代表真实出纸。
    """

    success: bool
    status: str
    provider_job_id: str = ""
    error: str = ""


@dataclass
class PrintTicket:
    """一张待打印的小票。"""

    ticket_type: str
    content: str
    printer_id: str = ""


__all__ = [
    "OrderPrintJob",
    "PrintJobStatus",
    "PrintResult",
    "PrintTicket",
    "PrintTicketType",
]
