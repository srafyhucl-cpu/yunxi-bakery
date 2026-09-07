"""边缘防护共享状态仓储：限流窗口与登录失败计数。

单语句原子操作，多 worker 与重启后一致；调用方持有短事务。
同一主机多进程共享同一库文件；多机部署需外部共享存储。
"""

from app.repository.base import BaseRepository


class EdgeProtectionRepo(BaseRepository):
    """限流与登录保护的共享状态读写。"""

    async def check_request_allowed(
        self, client_key: str, now_seconds: int, window_seconds: int, limit: int
    ) -> bool:
        """固定窗口计数，返回是否放行，单语句原子递增。"""
        rows = await self._db.execute_fetchall(
            "INSERT INTO rate_limit_windows (client_key, window_start, "
            "request_count, updated_at) VALUES (?, ?, 1, datetime('now')) "
            "ON CONFLICT(client_key) DO UPDATE SET "
            "window_start = CASE WHEN rate_limit_windows.window_start <= ? "
            "THEN ? ELSE rate_limit_windows.window_start END, "
            "request_count = CASE WHEN rate_limit_windows.window_start <= ? "
            "THEN 1 ELSE rate_limit_windows.request_count + 1 END, "
            "updated_at = datetime('now') "
            "RETURNING request_count",
            (
                client_key,
                now_seconds,
                now_seconds - window_seconds,
                now_seconds,
                now_seconds - window_seconds,
            ),
        )
        await self._prune_rate_windows(now_seconds, window_seconds)
        return bool(rows) and int(rows[0]["request_count"]) <= limit

    async def _prune_rate_windows(self, now_seconds: int, window_seconds: int) -> None:
        """顺手清理过期窗口，最佳努力。"""
        await self._db.execute(
            "DELETE FROM rate_limit_windows WHERE window_start <= ?",
            (now_seconds - window_seconds * 2,),
        )

    async def admin_login_allowed(
        self, client_key: str, now_seconds: int, max_attempts: int
    ) -> bool:
        """登录失败未超阈或窗口已过期则放行。"""
        rows = await self._db.execute_fetchall(
            "SELECT fail_count, window_until FROM admin_login_attempts "
            "WHERE client_key = ? LIMIT 1",
            (client_key,),
        )
        if not rows:
            return True
        fail_count = int(rows[0]["fail_count"])
        window_until = int(rows[0]["window_until"])
        if now_seconds >= window_until:
            return True
        return fail_count < max_attempts

    async def record_admin_login_failure(
        self, client_key: str, now_seconds: int, window_seconds: int
    ) -> None:
        """记录一次登录失败，窗口过期则重置计数。"""
        await self._db.execute(
            "INSERT INTO admin_login_attempts (client_key, fail_count, "
            "window_until, updated_at) VALUES (?, 1, ?, datetime('now')) "
            "ON CONFLICT(client_key) DO UPDATE SET "
            "fail_count = CASE WHEN admin_login_attempts.window_until <= ? "
            "THEN 1 ELSE admin_login_attempts.fail_count + 1 END, "
            "window_until = CASE WHEN admin_login_attempts.window_until <= ? "
            "THEN ? ELSE admin_login_attempts.window_until END, "
            "updated_at = datetime('now')",
            (
                client_key,
                now_seconds + window_seconds,
                now_seconds,
                now_seconds,
                now_seconds + window_seconds,
            ),
        )

    async def check_and_record_login_attempt(
        self, client_key: str, now_seconds: int, window_seconds: int, max_attempts: int
    ) -> bool:
        """原子占用一次登录尝试，返回是否放行。

        检查与计数在同一写序列完成：仅当窗口过期或失败未超阈时占用，
        并发尝试按串行语义精确放行前 max 个，不存在先读后写的超发窗口。
        """
        for _ in range(2):
            cursor = await self._db.execute(
                "UPDATE admin_login_attempts SET "
                "fail_count = CASE WHEN window_until <= ? THEN 1 "
                "ELSE fail_count + 1 END, "
                "window_until = CASE WHEN window_until <= ? THEN ? "
                "ELSE window_until END, "
                "updated_at = datetime('now') "
                "WHERE client_key = ? AND (window_until <= ? OR fail_count < ?)",
                (
                    now_seconds,
                    now_seconds,
                    now_seconds + window_seconds,
                    client_key,
                    now_seconds,
                    max_attempts,
                ),
            )
            if int(cursor.rowcount or 0) == 1:
                return True
            inserted = await self._db.execute(
                "INSERT INTO admin_login_attempts (client_key, fail_count, "
                "window_until, updated_at) VALUES (?, 1, ?, datetime('now')) "
                "ON CONFLICT(client_key) DO NOTHING",
                (client_key, now_seconds + window_seconds),
            )
            if int(inserted.rowcount or 0) == 1:
                return True
        return False

    async def clear_admin_login_failures(self, client_key: str) -> None:
        """成功登录后清理失败计数。"""
        await self._db.execute(
            "DELETE FROM admin_login_attempts WHERE client_key = ?",
            (client_key,),
        )
