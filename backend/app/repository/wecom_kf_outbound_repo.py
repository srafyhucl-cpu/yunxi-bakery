"""企微客服外发投递账本仓库。"""

from uuid import uuid4

from app.repository.base import BaseRepository

STATUS_PENDING = "pending"
STATUS_SENDING = "sending"
STATUS_SENT = "sent"
STATUS_UNKNOWN = "unknown"
STATUS_FAILED = "failed"

# 发送租约过期秒数：sending 行超过此时限未终态，视为持有者崩溃，
# 新认领可凭新凭证接管，旧凭证立即失效。
SEND_STALE_SECONDS = 300

_LEDGER_COLUMNS = (
    "outbound_key, open_kfid, external_userid, inbound_msg_id, "
    "provider_msgid, msgtype, content_hash, claim_token, status, "
    "attempt_count, last_error, created_at, updated_at"
)


class WecomKfOutboundRepo(BaseRepository):
    """保存外发投递状态，发送状态机由调用方推进。

    owner 隔离：认领签发唯一 claim_token；mark_sent/unknown/failed 必须
    携带 token 且仅当行仍为 sending 且 token 一致时生效，陈旧 worker
    的迟到提交返回假，不得覆盖新一轮状态。
    """

    async def claim_for_send(
        self,
        outbound_key: str,
        open_kfid: str,
        external_userid: str,
        inbound_msg_id: str,
        msgtype: str,
        content_hash: str = "",
    ) -> tuple[dict, bool]:
        """原子占位并转为发送中，仅首个调用者可发送。

        返回（当前行，是否可发送）。已发送、发送中、未知、失败均不可重复发送。
        同一幂等键绑定内容哈希：已存在记录的内容哈希非空且与本次不一致时
        直接抛错，禁止同一 inbound/part 用不同内容复用。
        成功认领的行携带本次 claim_token。
        """
        await self._db.execute(
            "INSERT INTO wecom_kf_outbound_ledger "
            "(outbound_key, open_kfid, external_userid, inbound_msg_id, "
            "provider_msgid, msgtype, content_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(outbound_key) DO NOTHING",
            (
                outbound_key,
                open_kfid,
                external_userid,
                inbound_msg_id,
                outbound_key,
                msgtype,
                content_hash,
            ),
        )
        row = await self._get_row(outbound_key)
        stored_hash = str(row.get("content_hash", "") or "")
        if stored_hash and content_hash and stored_hash != content_hash:
            raise ValueError(
                f"外发内容冲突 outbound_key={outbound_key}，同一投递键不得更换内容"
            )
        if not stored_hash and content_hash:
            await self._db.execute(
                "UPDATE wecom_kf_outbound_ledger SET content_hash = ? "
                "WHERE outbound_key = ?",
                (content_hash, outbound_key),
            )
            row["content_hash"] = content_hash
        if str(row.get("status", "")) != STATUS_PENDING:
            if str(row.get("status", "")) == STATUS_SENDING:
                return await self._try_takeover_stale_sending(outbound_key)
            return row, False
        token = uuid4().hex
        cursor = await self._db.execute(
            "UPDATE wecom_kf_outbound_ledger SET status = ?, claim_token = ?, "
            "attempt_count = attempt_count + 1, updated_at = datetime('now') "
            "WHERE outbound_key = ? AND status = ?",
            (STATUS_SENDING, token, outbound_key, STATUS_PENDING),
        )
        if int(cursor.rowcount or 0) != 1:
            return await self._get_row(outbound_key), False
        row = await self._get_row(outbound_key)
        return row, True

    async def _try_takeover_stale_sending(self, outbound_key: str) -> tuple[dict, bool]:
        """过期发送租约接管：持有者疑似崩溃时凭新凭证接管并递增 attempt。

        租约有效期内返回不可发送，调用方退避，不得触碰持有者的行。
        """
        token = uuid4().hex
        cursor = await self._db.execute(
            "UPDATE wecom_kf_outbound_ledger SET claim_token = ?, "
            "attempt_count = attempt_count + 1, updated_at = datetime('now') "
            "WHERE outbound_key = ? AND status = ? "
            "AND updated_at <= datetime('now', ?)",
            (
                token,
                outbound_key,
                STATUS_SENDING,
                f"-{SEND_STALE_SECONDS} seconds",
            ),
        )
        row = await self._get_row(outbound_key)
        return row, bool(cursor.rowcount == 1)

    async def mark_sent(self, outbound_key: str, claim_token: str) -> bool:
        """标记已发送：仅 sending 且 token 一致时生效，返回是否写入。"""
        cursor = await self._db.execute(
            "UPDATE wecom_kf_outbound_ledger SET status = ?, "
            "updated_at = datetime('now') "
            "WHERE outbound_key = ? AND status = ? AND claim_token = ?",
            (STATUS_SENT, outbound_key, STATUS_SENDING, claim_token),
        )
        return int(cursor.rowcount or 0) == 1

    async def mark_unknown(
        self, outbound_key: str, claim_token: str, error: str
    ) -> bool:
        """标记未知结果：仅 sending 且 token 一致时生效，需人工确认。"""
        cursor = await self._db.execute(
            "UPDATE wecom_kf_outbound_ledger SET status = ?, last_error = ?, "
            "updated_at = datetime('now') "
            "WHERE outbound_key = ? AND status = ? AND claim_token = ?",
            (STATUS_UNKNOWN, error[:500], outbound_key, STATUS_SENDING, claim_token),
        )
        return int(cursor.rowcount or 0) == 1

    async def mark_failed(
        self, outbound_key: str, claim_token: str, error: str
    ) -> bool:
        """标记明确失败：仅 sending 且 token 一致时生效，需人工重试。"""
        cursor = await self._db.execute(
            "UPDATE wecom_kf_outbound_ledger SET status = ?, last_error = ?, "
            "updated_at = datetime('now') "
            "WHERE outbound_key = ? AND status = ? AND claim_token = ?",
            (STATUS_FAILED, error[:500], outbound_key, STATUS_SENDING, claim_token),
        )
        return int(cursor.rowcount or 0) == 1

    async def requeue_for_manual_retry(
        self, outbound_key: str, operator: str, reason: str
    ) -> bool:
        """人工确认后重新排队，仅未知或失败状态可转回待发送。

        重排即轮换 claim_token，旧凭证立即失效。
        """
        cursor = await self._db.execute(
            "UPDATE wecom_kf_outbound_ledger SET status = ?, claim_token = ?, "
            "last_error = ?, updated_at = datetime('now') "
            "WHERE outbound_key = ? AND status IN (?, ?)",
            (
                STATUS_PENDING,
                uuid4().hex,
                f"人工重试:{operator}:{reason}"[:500],
                outbound_key,
                STATUS_UNKNOWN,
                STATUS_FAILED,
            ),
        )
        return bool(cursor.rowcount == 1)

    async def get(self, outbound_key: str) -> dict | None:
        """查询单条投递记录，不存在返回空。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + _LEDGER_COLUMNS + " FROM wecom_kf_outbound_ledger "
            "WHERE outbound_key = ?",
            (outbound_key,),
        )
        return dict(rows[0]) if rows else None

    async def _get_row(self, outbound_key: str) -> dict:
        """读取单行，不存在返回空字典。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + _LEDGER_COLUMNS + " FROM wecom_kf_outbound_ledger "
            "WHERE outbound_key = ?",
            (outbound_key,),
        )
        return dict(rows[0]) if rows else {}
