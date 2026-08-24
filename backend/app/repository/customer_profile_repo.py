"""顾客长期记忆数据访问层。"""

from uuid import uuid4

from app.models.customer_profile import CustomerProfile, CustomerProfileUpsert
from app.repository.base import BaseRepository
from app.utils import now_str


class CustomerProfileRepo(BaseRepository):
    """顾客画像仓库：读取、写入与刷新最近交互时间。"""

    async def get(self, channel: str, user_id: str) -> CustomerProfile | None:
        rows = await self._db.execute_fetchall(
            "SELECT id, channel, user_id, display_name, preferences_json, "
            "order_summary_json, special_dates_json, allergens_json, consent_status, "
            "source_evidence_json, last_interaction_at, created_at, updated_at "
            "FROM customer_profiles WHERE channel = ? AND user_id = ?",
            (channel, user_id),
        )
        return CustomerProfile(**dict(rows[0])) if rows else None

    async def upsert(self, profile: CustomerProfileUpsert) -> CustomerProfile:
        now = now_str()
        last_interaction_at = profile.last_interaction_at or now
        await self._db.execute(
            "INSERT INTO customer_profiles ("
            "id, channel, user_id, display_name, preferences_json, order_summary_json, "
            "special_dates_json, allergens_json, consent_status, source_evidence_json, "
            "last_interaction_at, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(channel, user_id) DO UPDATE SET "
            "display_name = excluded.display_name, "
            "preferences_json = excluded.preferences_json, "
            "order_summary_json = excluded.order_summary_json, "
            "special_dates_json = excluded.special_dates_json, "
            "allergens_json = excluded.allergens_json, "
            "consent_status = excluded.consent_status, "
            "source_evidence_json = excluded.source_evidence_json, "
            "last_interaction_at = excluded.last_interaction_at, "
            "updated_at = excluded.updated_at",
            (
                str(uuid4()),
                profile.channel,
                profile.user_id,
                profile.display_name,
                profile.preferences_json,
                profile.order_summary_json,
                profile.special_dates_json,
                profile.allergens_json,
                profile.consent_status,
                profile.source_evidence_json,
                last_interaction_at,
                now,
                now,
            ),
        )
        await self._db.commit()
        saved = await self.get(profile.channel, profile.user_id)
        if saved is None:
            raise RuntimeError("顾客画像写入后未能读回")
        return saved

    async def touch_interaction(self, channel: str, user_id: str) -> None:
        now = now_str()
        await self._db.execute(
            "UPDATE customer_profiles SET last_interaction_at = ?, updated_at = ? "
            "WHERE channel = ? AND user_id = ?",
            (now, now, channel, user_id),
        )
        await self._db.commit()

    async def get_consent_status(self, channel: str, user_id: str) -> str:
        """读取独立 consent ledger，缺失时返回 unknown。"""
        rows = await self._db.execute_fetchall(
            "SELECT status FROM customer_consent_ledger "
            "WHERE channel = ? AND user_id = ?",
            (channel, user_id),
        )
        return str(rows[0]["status"]) if rows else "unknown"

    async def set_consent_status(self, channel: str, user_id: str, status: str) -> None:
        """写入 consent ledger 的三态状态。"""
        if status not in {"unknown", "granted", "revoked"}:
            raise ValueError("无效的 consent 状态")
        await self._db.execute(
            "INSERT INTO customer_consent_ledger "
            "(channel, user_id, status, created_at, updated_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now')) "
            "ON CONFLICT(channel, user_id) DO UPDATE SET "
            "status = excluded.status, updated_at = excluded.updated_at",
            (channel, user_id, status),
        )
        await self._db.commit()

    async def delete(self, channel: str, user_id: str) -> None:
        """删除顾客长期画像，不删除 consent ledger。"""
        await self._db.execute(
            "DELETE FROM customer_profiles WHERE channel = ? AND user_id = ?",
            (channel, user_id),
        )
        await self._db.commit()

    async def revoke_and_delete(self, channel: str, user_id: str) -> None:
        """在同一事务内撤回 consent 并删除长期画像。"""
        await self._db.execute(
            "INSERT INTO customer_consent_ledger "
            "(channel, user_id, status, created_at, updated_at) "
            "VALUES (?, ?, 'revoked', datetime('now'), datetime('now')) "
            "ON CONFLICT(channel, user_id) DO UPDATE SET "
            "status = 'revoked', updated_at = excluded.updated_at",
            (channel, user_id),
        )
        await self._db.execute(
            "DELETE FROM customer_profiles WHERE channel = ? AND user_id = ?",
            (channel, user_id),
        )
        await self._db.commit()
