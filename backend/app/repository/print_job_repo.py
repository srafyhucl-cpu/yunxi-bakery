"""订单打印作业数据访问层。"""

from app.models.print_job import OrderPrintJob
from app.repository.base import BaseRepository
from app.utils import now_str

# 显式字段列表，避免 SELECT *。
_JOB_COLUMNS = (
    "id, order_id, ticket_type, status, provider, printer_id, attempts, "
    "last_error, provider_job_id, idempotency_key, payload_snapshot, operator, "
    "created_at, updated_at, printed_at"
)


def _status_value(status: object) -> str:
    """兼容枚举与字符串两种状态入参。"""
    return str(getattr(status, "value", status))


class PrintJobRepo(BaseRepository):
    """打印作业的幂等入队、CAS 领取与状态更新。"""

    async def create_job(self, job: OrderPrintJob) -> bool:
        """按 idempotency_key 幂等入队，返回是否真正新建。"""
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO order_print_jobs ("
            + _JOB_COLUMNS
            + ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job.id,
                job.order_id,
                job.ticket_type,
                job.status,
                job.provider,
                job.printer_id,
                job.attempts,
                job.last_error,
                job.provider_job_id,
                job.idempotency_key,
                job.payload_snapshot,
                job.operator,
                job.created_at,
                job.updated_at,
                job.printed_at,
            ),
        )
        return cursor.rowcount == 1

    async def get_job(self, job_id: str) -> OrderPrintJob | None:
        """按作业号读取打印作业。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + _JOB_COLUMNS + " FROM order_print_jobs WHERE id = ? LIMIT 1",
            (job_id,),
        )
        return OrderPrintJob(**dict(rows[0])) if rows else None

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> OrderPrintJob | None:
        """按幂等键读取作业，供重复入队时复用。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + _JOB_COLUMNS + " FROM order_print_jobs "
            "WHERE idempotency_key = ? LIMIT 1",
            (idempotency_key,),
        )
        return OrderPrintJob(**dict(rows[0])) if rows else None

    async def list_for_order(self, order_id: str) -> list[OrderPrintJob]:
        """读取订单全部打印作业，最新在前。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + _JOB_COLUMNS + " FROM order_print_jobs "
            "WHERE order_id = ? ORDER BY created_at DESC, id DESC",
            (order_id,),
        )
        return [OrderPrintJob(**dict(row)) for row in rows]

    async def list_pending(self, limit: int = 10) -> list[OrderPrintJob]:
        """按创建顺序读取待处理作业。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + _JOB_COLUMNS + " FROM order_print_jobs "
            "WHERE status = 'PENDING' ORDER BY created_at ASC, id ASC LIMIT ?",
            (max(int(limit), 0),),
        )
        return [OrderPrintJob(**dict(row)) for row in rows]

    async def list_failed(self, limit: int = 10) -> list[OrderPrintJob]:
        """读取失败作业，供后台补打或人工排查。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + _JOB_COLUMNS + " FROM order_print_jobs "
            "WHERE status = 'FAILED' ORDER BY updated_at ASC, id ASC LIMIT ?",
            (max(int(limit), 0),),
        )
        return [OrderPrintJob(**dict(row)) for row in rows]

    async def list_by_status(
        self, status: str = "", limit: int = 50
    ) -> list[OrderPrintJob]:
        """按状态读取作业；status 为空时返回全部，最新在前。"""
        resolved_status = _status_value(status or "").strip().upper()
        resolved_limit = max(int(limit), 0)
        if resolved_status:
            rows = await self._db.execute_fetchall(
                "SELECT " + _JOB_COLUMNS + " FROM order_print_jobs "
                "WHERE status = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                (resolved_status, resolved_limit),
            )
        else:
            rows = await self._db.execute_fetchall(
                "SELECT " + _JOB_COLUMNS + " FROM order_print_jobs "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (resolved_limit,),
            )
        return [OrderPrintJob(**dict(row)) for row in rows]

    async def mark_claimed(self, job_id: str, updated_at: str = "") -> bool:
        """CAS 领取作业：仅 PENDING/FAILED 可进入 CLAIMED。"""
        cursor = await self._db.execute(
            "UPDATE order_print_jobs SET status = 'CLAIMED', updated_at = ? "
            "WHERE id = ? AND status IN ('PENDING', 'FAILED')",
            (updated_at or now_str(), job_id),
        )
        return cursor.rowcount == 1

    async def mark_result(
        self,
        job_id: str,
        status: str,
        provider_job_id: str,
        error: str,
        attempts_delta: int,
        *,
        updated_at: str = "",
    ) -> bool:
        """写回一次提交结果，并显式递增尝试次数。"""
        resolved_at = updated_at or now_str()
        resolved_status = _status_value(status)
        cursor = await self._db.execute(
            "UPDATE order_print_jobs SET status = ?, provider_job_id = ?, "
            "last_error = ?, "
            "attempts = CASE WHEN attempts + ? < 0 THEN 0 ELSE attempts + ? END, "
            "updated_at = ?, "
            "printed_at = CASE WHEN ? = 'PRINTED' THEN ? ELSE printed_at END "
            "WHERE id = ?",
            (
                resolved_status,
                provider_job_id,
                error,
                attempts_delta,
                attempts_delta,
                resolved_at,
                resolved_status,
                resolved_at,
                job_id,
            ),
        )
        return cursor.rowcount == 1

    async def mark_printed(
        self,
        job_id: str,
        provider_job_id: str = "",
        updated_at: str = "",
    ) -> bool:
        """记录真实出纸（由后续打印机回调或人工确认调用）。"""
        resolved_at = updated_at or now_str()
        cursor = await self._db.execute(
            "UPDATE order_print_jobs SET status = 'PRINTED', provider_job_id = ?, "
            "last_error = '', printed_at = ?, updated_at = ? "
            "WHERE id = ? AND status IN ('SUBMITTED', 'MOCKED', 'PRINTED')",
            (provider_job_id, resolved_at, resolved_at, job_id),
        )
        return cursor.rowcount == 1

    async def mark_mocked(self, job_id: str, provider_job_id: str = "") -> bool:
        """记录 Mock 已受理；Mock 绝不写 PRINTED。"""
        cursor = await self._db.execute(
            "UPDATE order_print_jobs SET status = 'MOCKED', provider_job_id = ?, "
            "last_error = '', updated_at = ? WHERE id = ?",
            (provider_job_id, now_str(), job_id),
        )
        return cursor.rowcount == 1

    async def mark_failed(
        self,
        job_id: str,
        error: str,
        *,
        attempts_delta: int = 0,
        updated_at: str = "",
    ) -> bool:
        """标记作业失败并保留错误上下文。"""
        return await self.mark_result(
            job_id,
            "FAILED",
            "",
            error,
            attempts_delta,
            updated_at=updated_at,
        )


__all__ = ["PrintJobRepo"]
