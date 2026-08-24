"""微信客服同步状态与消息账本仓库。"""

from dataclasses import dataclass
from datetime import datetime

from app.repository.base import BaseRepository


@dataclass(frozen=True)
class WecomKfSyncState:
    """微信客服 sync_msg 游标状态。"""

    open_kfid: str
    last_cursor: str = ""
    status: str = "idle"
    last_error: str = ""
    retry_count: int = 0
    last_synced_at: str = ""


class WecomKfSyncRepo(BaseRepository):
    """保存微信客服同步游标，并按 msgid 做持久化幂等。"""

    async def get_state(self, open_kfid: str) -> WecomKfSyncState:
        rows = await self._db.execute_fetchall(
            "SELECT open_kfid, last_cursor, status, last_error, retry_count, "
            "last_synced_at FROM wecom_kf_sync_states WHERE open_kfid = ?",
            (open_kfid,),
        )
        if rows:
            return WecomKfSyncState(**dict(rows[0]))
        return WecomKfSyncState(open_kfid=open_kfid)

    async def mark_syncing(self, open_kfid: str) -> None:
        now = _now()
        await self._db.execute(
            "INSERT INTO wecom_kf_sync_states "
            "(open_kfid, status, created_at, updated_at) VALUES (?, 'syncing', ?, ?) "
            "ON CONFLICT(open_kfid) DO UPDATE SET "
            "status = 'syncing', updated_at = excluded.updated_at",
            (open_kfid, now, now),
        )
        await self._db.commit()

    async def mark_success(self, open_kfid: str, cursor: str) -> None:
        now = _now()
        await self._db.execute(
            "INSERT INTO wecom_kf_sync_states "
            "(open_kfid, last_cursor, status, last_error, retry_count, "
            "last_synced_at, created_at, updated_at) "
            "VALUES (?, ?, 'idle', '', 0, ?, ?, ?) "
            "ON CONFLICT(open_kfid) DO UPDATE SET "
            "last_cursor = excluded.last_cursor, "
            "status = 'idle', last_error = '', retry_count = 0, "
            "last_synced_at = excluded.last_synced_at, "
            "updated_at = excluded.updated_at",
            (open_kfid, cursor, now, now, now),
        )
        await self._db.commit()

    async def mark_failed(self, open_kfid: str, error: str) -> None:
        now = _now()
        await self._db.execute(
            "INSERT INTO wecom_kf_sync_states "
            "(open_kfid, status, last_error, retry_count, created_at, updated_at) "
            "VALUES (?, 'failed', ?, 1, ?, ?) "
            "ON CONFLICT(open_kfid) DO UPDATE SET "
            "status = 'failed', last_error = excluded.last_error, "
            "retry_count = retry_count + 1, updated_at = excluded.updated_at",
            (open_kfid, error[:500], now, now),
        )
        await self._db.commit()

    async def add_message_if_new(
        self,
        msg_id: str,
        open_kfid: str,
        external_userid: str,
        origin: int,
        msgtype: str,
        event_type: str,
        process_action: str,
    ) -> bool:
        """记录企微消息处理账本，返回是否首次出现。"""
        if not msg_id:
            return True
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO wecom_kf_message_ledger "
            "(msg_id, open_kfid, external_userid, origin, msgtype, event_type, "
            "process_action, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                msg_id,
                open_kfid,
                external_userid,
                origin,
                msgtype,
                event_type,
                process_action,
                _now(),
            ),
        )
        await self._db.commit()
        return bool(cursor.rowcount > 0)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
