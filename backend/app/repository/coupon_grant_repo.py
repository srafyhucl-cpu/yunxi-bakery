"""发券记录数据访问层（local 模式）。"""

from app.models.coupon import CouponGrant
from app.repository.base import BaseRepository
from app.utils import now_str


class CouponGrantRepo(BaseRepository):
    """发券记录仓储。"""

    _COLS = (
        "id, template_id, customer_id, mobile, coupon_code, granted_by, "
        "channel, audience_json, status, created_at"
    )

    async def insert(self, grant: CouponGrant) -> None:
        """写入发券记录。

        B3.5（评审问题 1）：账务仓储**不自提交**，由调用方命令（发券 / 导入）
        外层事务提交。
        """
        await self._db.execute(
            "INSERT INTO coupon_grants (id, template_id, customer_id, mobile, coupon_code, "
            "granted_by, channel, audience_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                grant.id,
                grant.template_id,
                grant.customer_id,
                grant.mobile,
                grant.coupon_code,
                grant.granted_by,
                grant.channel,
                grant.audience_json,
                grant.status,
                grant.created_at or now_str(),
            ),
        )

    async def get(self, grant_id: str) -> dict | None:
        """按发券记录 ID 读取。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + self._COLS + " FROM coupon_grants WHERE id = ? LIMIT 1",
            (grant_id,),
        )
        return rows[0] if rows else None

    async def list_by_mobile(self, mobile: str, limit: int = 50) -> list[dict]:
        """按手机号查询发券记录。"""
        return await self._db.execute_fetchall(
            "SELECT "
            + self._COLS
            + " FROM coupon_grants WHERE mobile = ? ORDER BY created_at DESC LIMIT ?",
            (mobile, limit),
        )

    async def list(
        self, *, mobile: str = "", template_id: str = "", limit: int = 200
    ) -> list[dict]:
        """发券记录列表，支持筛选。"""
        sql = "SELECT " + self._COLS + " FROM coupon_grants WHERE 1=1"
        params: list[object] = []
        if mobile:
            sql += " AND mobile = ?"
            params.append(mobile)
        if template_id:
            sql += " AND template_id = ?"
            params.append(template_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return await self._db.execute_fetchall(sql, params)

    async def revoke(self, grant_id: str) -> None:
        """回收发券记录（B3.5：账务仓储不自提交，由调用方事务提交）。"""
        await self._db.execute(
            "UPDATE coupon_grants SET status = 'revoked' WHERE id = ?",
            (grant_id,),
        )
