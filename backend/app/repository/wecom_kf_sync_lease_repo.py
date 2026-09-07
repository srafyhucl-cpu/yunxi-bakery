"""微信客服同步租约仓储：同一客服账号同时只允许一个同步者。

租约由调用方短事务持有：acquire 成功后提交，事务外拉取网络消息，
第二段短事务校验 token 与游标后提交持久化并释放。仓储自身不自提交。
"""

from uuid import uuid4

from app.repository.base import BaseRepository
from app.repository.wecom_kf_sync_repo import WecomKfSyncRepo

DEFAULT_SYNC_LEASE_SECONDS = 300


class WecomKfSyncLeaseRepo(BaseRepository):
    """同步租约读写，单语句原子占位与释放。"""

    async def get(self, open_kfid: str) -> dict | None:
        """读取租约行，不存在返回空。"""
        rows = await self._db.execute_fetchall(
            "SELECT open_kfid, lease_token, base_cursor, lease_until, "
            "continuation_cursor, has_more, fail_count, last_error, updated_at "
            "FROM wecom_kf_sync_leases WHERE open_kfid = ?",
            (open_kfid,),
        )
        return dict(rows[0]) if rows else None

    async def acquire(
        self, open_kfid: str, lease_seconds: int = DEFAULT_SYNC_LEASE_SECONDS
    ) -> dict | None:
        """原子取得同步租约，成功返回凭证与基准游标，失败返回空。

        无租约、已释放或已过期可取得；有效租约被其他同步者持有时返回空，
        调用方不得成为同一 open_kfid 的并发同步者。
        """
        token = uuid4().hex
        base_cursor = (await WecomKfSyncRepo(self._db).get_state(open_kfid)).last_cursor
        modifier = _lease_modifier(lease_seconds)
        await self._db.execute(
            "INSERT INTO wecom_kf_sync_leases "
            "(open_kfid, lease_token, base_cursor, lease_until, updated_at) "
            "VALUES (?, ?, ?, datetime('now', ?), datetime('now')) "
            "ON CONFLICT(open_kfid) DO UPDATE SET lease_token = excluded.lease_token, "
            "base_cursor = excluded.base_cursor, lease_until = excluded.lease_until, "
            "continuation_cursor = '', has_more = 0, updated_at = datetime('now') "
            "WHERE wecom_kf_sync_leases.lease_until <= datetime('now')",
            (open_kfid, token, base_cursor, modifier),
        )
        row = await self.get(open_kfid)
        if row is not None and str(row.get("lease_token", "")) == token:
            return {"lease_token": token, "base_cursor": base_cursor}
        return None

    async def complete(
        self,
        open_kfid: str,
        lease_token: str,
        *,
        continuation_cursor: str = "",
        has_more: bool = False,
    ) -> bool:
        """校验凭证后释放租约并记录分页延续状态，返回是否释放成功。

        陈旧同步者（token 不一致或租约已被接管）返回假，调用方必须回滚
        本次持久化，不得推进游标。
        """
        cursor = await self._db.execute(
            "UPDATE wecom_kf_sync_leases SET lease_token = '', lease_until = '', "
            "continuation_cursor = ?, has_more = ?, fail_count = 0, last_error = '', "
            "updated_at = datetime('now') WHERE open_kfid = ? AND lease_token = ?",
            (
                continuation_cursor,
                1 if has_more else 0,
                open_kfid,
                lease_token,
            ),
        )
        return int(cursor.rowcount or 0) == 1

    async def fail(self, open_kfid: str, lease_token: str, error: str) -> None:
        """记录同步失败并释放租约，游标不推进，仅租约持有者可写。"""
        await self._db.execute(
            "UPDATE wecom_kf_sync_leases SET lease_token = '', lease_until = '', "
            "fail_count = fail_count + 1, last_error = ?, "
            "updated_at = datetime('now') WHERE open_kfid = ? AND lease_token = ?",
            (str(error or "")[:500], open_kfid, lease_token),
        )


def _lease_modifier(lease_seconds: int) -> str:
    """生成 SQLite datetime 修饰符，兼容正负租约。"""
    sign = "+" if int(lease_seconds) >= 0 else "-"
    return f"{sign}{abs(int(lease_seconds))} seconds"
