"""订单打印作业服务。

只负责入队、提交网关与失败重试记录：
- 不接支付成功事件（3B 调用 enqueue_for_order）；
- 不启动后台 worker（3B 调度 process_pending）；
- 不覆盖历史作业，补打永远新建一条 PENDING。
"""

import json
from uuid import uuid4

from app.logger import setup_logger
from app.models.order import Order
from app.models.print_job import (
    OrderPrintJob,
    PrintJobStatus,
    PrintTicket,
    PrintTicketType,
)
from app.repository.print_job_repo import PrintJobRepo
from app.service.integrations.printer.base import PrinterGateway
from app.service.order.print_jobs import DEFAULT_TICKET_WIDTH, build_print_tickets
from app.utils import now_str

logger = setup_logger()

SUCCESS_PRINT_STATUSES = (
    PrintJobStatus.MOCKED.value,
    PrintJobStatus.SUBMITTED.value,
)


class PrintJobService:
    """打印作业应用服务。"""

    def __init__(
        self,
        repo: PrintJobRepo,
        gateway: PrinterGateway,
        provider_name: str = "",
        max_attempts: int = 3,
        printer_id: str = "",
        ticket_width: int = DEFAULT_TICKET_WIDTH,
    ) -> None:
        self._repo = repo
        self._gateway = gateway
        self._provider_name = (
            (provider_name or getattr(gateway, "name", "")).strip().lower()
        )
        self._max_attempts = max(int(max_attempts), 1)
        self._printer_id = printer_id
        self._ticket_width = max(int(ticket_width), 1)

    async def enqueue_for_order(
        self,
        order: Order,
        operator: str = "system",
    ) -> list[dict]:
        """按订单内容幂等入队打印作业。"""
        tickets = build_print_tickets(order, width=self._ticket_width)
        results: list[dict] = []
        for ticket in tickets:
            idempotency_key = self._enqueue_key(order.id, ticket.ticket_type)
            existing = await self._repo.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                results.append(self._job_dict(existing, created=False))
                continue
            job = self._new_job(
                order_id=order.id,
                ticket=ticket,
                idempotency_key=idempotency_key,
                operator=operator,
            )
            created = await self._repo.create_job(job)
            if not created:
                # 并发入队时以先写入的作业为准，保证同一幂等键只有一条。
                existing = await self._repo.get_by_idempotency_key(idempotency_key)
                if existing is None:
                    raise RuntimeError(f"打印作业入队冲突: {idempotency_key}")
                job = existing
            results.append(self._job_dict(job, created=created))
        return results

    async def process_job(self, job_id: str) -> dict:
        """CAS 领取并处理一条作业。"""
        job = await self._repo.get_job(job_id)
        if job is None:
            return {
                "success": False,
                "jobId": job_id,
                "status": "NOT_FOUND",
                "attempts": 0,
                "providerJobId": "",
                "error": "打印作业不存在",
            }
        claimed = await self._repo.mark_claimed(job.id)
        if not claimed:
            latest = await self._repo.get_job(job.id) or job
            return {
                "success": False,
                "jobId": latest.id,
                "status": latest.status,
                "attempts": latest.attempts,
                "providerJobId": latest.provider_job_id,
                "error": "打印作业已被领取或已结束",
                "skipped": True,
            }

        attempt = job.attempts + 1
        try:
            ticket = self._ticket_from_job(job)
            result = await self._gateway.submit(
                ticket,
                ticket.printer_id or job.printer_id or self._printer_id,
            )
        except Exception as exc:
            logger.error(
                "打印作业提交异常 job_id=%s order_id=%s: %s",
                job.id,
                job.order_id,
                exc,
                exc_info=True,
            )
            return await self._record_failure(job, attempt, str(exc))

        if result.success and result.status in SUCCESS_PRINT_STATUSES:
            await self._repo.mark_result(
                job.id,
                result.status,
                result.provider_job_id,
                "",
                1,
            )
            logger.info(
                "打印作业已受理 job_id=%s status=%s provider_job_id=%s",
                job.id,
                result.status,
                result.provider_job_id,
            )
            return self._result_dict(
                job, result.status, attempt, result.provider_job_id
            )

        error = result.error or "打印网关返回失败"
        logger.error(
            "打印作业提交失败 job_id=%s order_id=%s: %s",
            job.id,
            job.order_id,
            error,
        )
        return await self._record_failure(job, attempt, error)

    async def process_pending(self, limit: int = 10) -> dict:
        """批量处理待打印作业，返回计数摘要。"""
        summary = {"success": 0, "failed": 0, "mocked": 0, "submitted": 0}
        jobs = await self._repo.list_pending(limit)
        for job in jobs:
            result = await self.process_job(job.id)
            if result["success"]:
                summary["success"] += 1
                if result["status"] == PrintJobStatus.MOCKED.value:
                    summary["mocked"] += 1
                elif result["status"] == PrintJobStatus.SUBMITTED.value:
                    summary["submitted"] += 1
            else:
                summary["failed"] += 1
        return summary

    async def reprint(
        self,
        order_id: str,
        ticket_type: str,
        operator: str,
    ) -> dict:
        """补打：复制原作业快照新建 PENDING，不修改原作业。"""
        resolved_type = str(getattr(ticket_type, "value", ticket_type))
        if resolved_type not in (
            PrintTicketType.CAKE_KITCHEN.value,
            PrintTicketType.DAILY_FRONT.value,
        ):
            raise ValueError(f"不支持的小票类型: {resolved_type}")
        jobs = await self._repo.list_for_order(order_id)
        source = next(
            (job for job in jobs if job.ticket_type == resolved_type),
            None,
        )
        if source is None:
            raise ValueError("原打印作业不存在，无法补打")
        ticket = PrintTicket(
            ticket_type=source.ticket_type,
            content=self._ticket_from_job(source).content,
            printer_id=source.printer_id,
        )
        key = f"order:{order_id}:{resolved_type}:reprint:{uuid4().hex}"
        job = self._new_job(
            order_id=order_id,
            ticket=ticket,
            idempotency_key=key,
            operator=operator,
        )
        await self._repo.create_job(job)
        logger.info(
            "打印作业补打已入队 order_id=%s ticket_type=%s job_id=%s",
            order_id,
            resolved_type,
            job.id,
        )
        return self._job_dict(job, created=True)

    async def list_for_order(self, order_id: str) -> list[dict]:
        """读取订单的全部打印作业。"""
        jobs = await self._repo.list_for_order(order_id)
        return [self._job_dict(job) for job in jobs]

    def _new_job(
        self,
        *,
        order_id: str,
        ticket: PrintTicket,
        idempotency_key: str,
        operator: str,
    ) -> OrderPrintJob:
        """构造一条待处理作业。"""
        timestamp = now_str()
        snapshot = json.dumps(
            {
                "ticketType": ticket.ticket_type,
                "printerId": ticket.printer_id,
                "content": ticket.content,
            },
            ensure_ascii=False,
        )
        return OrderPrintJob(
            id=f"print_{uuid4().hex}",
            order_id=order_id,
            ticket_type=ticket.ticket_type,
            status=PrintJobStatus.PENDING.value,
            provider=self._provider_name,
            printer_id=ticket.printer_id or self._printer_id,
            attempts=0,
            last_error="",
            provider_job_id="",
            idempotency_key=idempotency_key,
            payload_snapshot=snapshot,
            operator=operator,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def _ticket_from_job(self, job: OrderPrintJob) -> PrintTicket:
        """从作业快照恢复小票，避免重打时重新读取订单。"""
        try:
            payload = json.loads(job.payload_snapshot or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("打印作业快照 JSON 非法") from exc
        if not isinstance(payload, dict):
            raise ValueError("打印作业快照必须是对象")
        content = str(payload.get("content", ""))
        if not content:
            raise ValueError("打印作业快照缺少小票内容")
        return PrintTicket(
            ticket_type=job.ticket_type,
            content=content,
            printer_id=job.printer_id or str(payload.get("printerId", "")),
        )

    async def _record_failure(
        self,
        job: OrderPrintJob,
        attempt: int,
        error: str,
    ) -> dict:
        """失败未达上限回 PENDING，达到上限写 FAILED。"""
        status = (
            PrintJobStatus.PENDING.value
            if attempt < self._max_attempts
            else PrintJobStatus.FAILED.value
        )
        await self._repo.mark_result(job.id, status, "", error, 1)
        return self._result_dict(job, status, attempt, "", error)

    def _result_dict(
        self,
        job: OrderPrintJob,
        status: str,
        attempts: int,
        provider_job_id: str,
        error: str = "",
    ) -> dict:
        """统一 process_job 返回结构。"""
        return {
            "success": status in SUCCESS_PRINT_STATUSES,
            "jobId": job.id,
            "orderId": job.order_id,
            "ticketType": job.ticket_type,
            "status": status,
            "attempts": attempts,
            "providerJobId": provider_job_id,
            "error": error,
        }

    def _job_dict(self, job: OrderPrintJob, *, created: bool = True) -> dict:
        """把作业模型转成服务层返回字典。"""
        return {
            "id": job.id,
            "orderId": job.order_id,
            "ticketType": job.ticket_type,
            "status": job.status,
            "provider": job.provider,
            "printerId": job.printer_id,
            "attempts": job.attempts,
            "lastError": job.last_error,
            "providerJobId": job.provider_job_id,
            "idempotencyKey": job.idempotency_key,
            "payloadSnapshot": job.payload_snapshot,
            "operator": job.operator,
            "createdAt": job.created_at,
            "updatedAt": job.updated_at,
            "printedAt": job.printed_at,
            "created": created,
        }

    @staticmethod
    def _enqueue_key(order_id: str, ticket_type: str) -> str:
        """首次入队幂等键；版本号固定 v1，便于 3B 演进。"""
        return f"order:{order_id}:{ticket_type}:v1"


__all__ = ["PrintJobService"]
