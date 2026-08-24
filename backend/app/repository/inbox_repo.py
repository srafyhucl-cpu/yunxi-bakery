"""持久入站任务的数据访问层。"""

from app.repository.base import BaseRepository

MAX_INBOX_ATTEMPTS = 5
DEFAULT_LEASE_SECONDS = 60
RETRY_DELAY_SECONDS = 15


class InboxRepo(BaseRepository):
    """管理 webhook/消息 worker 的持久 inbox 状态。"""

    async def enqueue(
        self,
        queue_name: str,
        message_key: str,
        payload_json: str,
    ) -> bool:
        """写入一条 inbox 记录；重复键只返回 False。

        B3.5（评审问题 8）：仓储**不自提交**——调用方（webhook 网关 / 消息队列）
        各自以 db_session_scope 提交；持有型原子转账等需与业务写同事务的
        调用方在自身事务内使用本方法（无中间提交边界）。
        """
        cursor = await self._db.execute(
            "INSERT INTO inbox_events "
            "(queue_name, message_key, payload_json, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'received', datetime('now'), datetime('now')) "
            "ON CONFLICT(message_key) DO NOTHING",
            (queue_name, message_key, payload_json),
        )
        return bool(cursor.rowcount == 1)

    async def claim(
        self,
        queue_name: str,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> dict | None:
        """原子认领一条到期或待处理任务。"""
        sign = "+" if lease_seconds >= 0 else "-"
        lease_modifier = f"{sign}{abs(lease_seconds)} seconds"
        async with self.transaction():
            rows = await self._db.execute_fetchall(
                "SELECT id, message_key, payload_json, attempt_count "
                "FROM inbox_events "
                "WHERE queue_name = ? AND ("
                "status = 'received' "
                "OR (status = 'failed' AND next_attempt_at <= datetime('now')) "
                "OR (status = 'processing' AND lease_until <= datetime('now'))"
                ") ORDER BY id LIMIT 1",
                (queue_name,),
            )
            if not rows:
                return None
            row = rows[0]
            attempt_count = int(row["attempt_count"]) + 1
            await self._db.execute(
                "UPDATE inbox_events SET status = 'processing', "
                "attempt_count = ?, lease_until = datetime('now', ?), "
                "updated_at = datetime('now') "
                "WHERE id = ?",
                (
                    attempt_count,
                    lease_modifier,
                    row["id"],
                ),
            )
            return {
                "id": int(row["id"]),
                "message_key": str(row["message_key"]),
                "payload_json": str(row["payload_json"]),
                "attempt_count": attempt_count,
            }

    async def mark_processed(self, message_key: str) -> None:
        """将已成功处理的任务置为终态。

        B3.5（评审问题 8）：不自提交——业务写与 processed 标记须同一事务
        （调用方合并为一个 db_session_scope，见 YouzanWebhookDispatcher）。
        """
        await self._db.execute(
            "UPDATE inbox_events SET status = 'processed', lease_until = NULL, "
            "updated_at = datetime('now') WHERE message_key = ?",
            (message_key,),
        )

    async def mark_failed(self, message_key: str, error_message: str) -> None:
        """记录失败并按次数决定重试或 dead-letter（不自提交，由调用方 scope 提交）。"""
        await self._db.execute(
            "UPDATE inbox_events SET status = CASE "
            "WHEN attempt_count >= ? THEN 'dead_letter' ELSE 'failed' END, "
            "lease_until = NULL, next_attempt_at = datetime('now', ?), "
            "last_error = ?, updated_at = datetime('now') "
            "WHERE message_key = ?",
            (
                MAX_INBOX_ATTEMPTS,
                f"+{RETRY_DELAY_SECONDS} seconds",
                error_message[:500],
                message_key,
            ),
        )

    async def renew_or_validate_lease(
        self,
        message_key: str,
        expected_attempt: int,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> bool:
        """校验并续租：仅当任务仍归当前 worker 时续租（claim_token 语义）。

        B3.5（评审问题 8）：以 claim 时的 attempt_count 作为 claim_token——
        lease 过期被其他 worker 接管后 attempt_count 递增，陈旧 worker 在
        业务写**之前**于同一 UoW 内校验失败即跳过处理，杜绝陈旧 worker
        继续提交资产。调用方必须在事务内调用（不自提交）。
        """
        sign = "+" if lease_seconds >= 0 else "-"
        cursor = await self._db.execute(
            "UPDATE inbox_events SET lease_until = datetime('now', ?), "
            "updated_at = datetime('now') "
            "WHERE message_key = ? AND status = 'processing' "
            "AND lease_until > datetime('now') AND attempt_count = ?",
            (f"{sign}{abs(lease_seconds)} seconds", message_key, expected_attempt),
        )
        return int(cursor.rowcount or 0) == 1

    async def count_pending(self, queue_name: str) -> int:
        """统计尚未进入成功终态的任务。"""
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS count FROM inbox_events "
            "WHERE queue_name = ? AND status IN ('received', 'processing', 'failed')",
            (queue_name,),
        )
        return int(rows[0]["count"]) if rows else 0

    async def count_stuck(self, queue_name: str) -> int:
        """统计 lease 已过期但仍处于 processing 的任务。"""
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS count FROM inbox_events "
            "WHERE queue_name = ? AND status = 'processing' "
            "AND lease_until IS NOT NULL AND lease_until <= datetime('now')",
            (queue_name,),
        )
        return int(rows[0]["count"]) if rows else 0
