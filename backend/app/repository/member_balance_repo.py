"""会员余额与卡片状态数据访问层。"""

from app.logger import setup_logger
from app.repository.base import BaseRepository
from app.utils import now_str

logger = setup_logger()


class MemberBalanceRepo(BaseRepository):
    """会员余额快照仓储（mobile 唯一，openid 兜底）。

    数值字段（is_member / points / stored_value_fen）传 None 表示不更新，
    显式传 0 会真实覆盖，避免默认值抹掉既有余额。
    """

    async def get_by_mobile(self, mobile: str) -> dict | None:
        """按手机号读取会员余额快照。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, customer_id, mobile, yz_open_id, display_name, is_member, "
            "card_alias, card_no, card_status, points, stored_value_fen, "
            "created_at, updated_at FROM member_balance WHERE mobile = ? LIMIT 1",
            (mobile,),
        )
        return rows[0] if rows else None

    async def get_by_openid(self, yz_open_id: str) -> dict | None:
        """按有赞 openid 读取会员余额快照。"""
        if not yz_open_id:
            return None
        rows = await self._db.execute_fetchall(
            "SELECT id, customer_id, mobile, yz_open_id, display_name, is_member, "
            "card_alias, card_no, card_status, points, stored_value_fen, "
            "created_at, updated_at FROM member_balance WHERE yz_open_id = ? LIMIT 1",
            (yz_open_id,),
        )
        return rows[0] if rows else None

    async def upsert_identity(
        self,
        *,
        mobile: str,
        customer_id: str = "",
        yz_open_id: str = "",
        display_name: str = "",
        is_member: int | None = None,
        card_alias: str = "",
        card_no: str = "",
        card_status: str = "",
        points: int | None = None,
        stored_value_fen: int | None = None,
    ) -> None:
        """按 mobile（openid 兜底）幂等合并会员身份/卡片/余额快照。

        B3.5（评审问题 1）：账务仓储**不自提交**，由调用方命令独占事务边界
        （member_loyalty 导入 / youzan 会员事件 / 支付链路外层事务提交）。
        """
        now = now_str()
        existing = await self.get_by_mobile(mobile) if mobile else None
        if existing is None and yz_open_id:
            existing = await self.get_by_openid(yz_open_id)
        if existing is None and not mobile and not yz_open_id:
            logger.warning("会员余额快照缺少 mobile 与 yz_open_id，跳过写入")
            return
        if existing is None:
            await self._db.execute(
                "INSERT INTO member_balance (customer_id, mobile, yz_open_id, "
                "display_name, is_member, card_alias, card_no, card_status, points, "
                "stored_value_fen, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    customer_id,
                    mobile,
                    yz_open_id,
                    display_name,
                    is_member if is_member is not None else 0,
                    card_alias,
                    card_no,
                    card_status,
                    points if points is not None else 0,
                    stored_value_fen if stored_value_fen is not None else 0,
                    now,
                    now,
                ),
            )
        else:
            await self._db.execute(
                "UPDATE member_balance SET "
                "customer_id = CASE WHEN ? != '' THEN ? ELSE customer_id END, "
                "yz_open_id = CASE WHEN ? != '' THEN ? ELSE yz_open_id END, "
                "display_name = CASE WHEN ? != '' THEN ? ELSE display_name END, "
                "is_member = CASE WHEN ? IS NOT NULL THEN ? ELSE is_member END, "
                "card_alias = CASE WHEN ? != '' THEN ? ELSE card_alias END, "
                "card_no = CASE WHEN ? != '' THEN ? ELSE card_no END, "
                "card_status = CASE WHEN ? != '' THEN ? ELSE card_status END, "
                "points = CASE WHEN ? IS NOT NULL THEN ? ELSE points END, "
                "stored_value_fen = CASE WHEN ? IS NOT NULL THEN ? ELSE "
                "stored_value_fen END, "
                "updated_at = ? WHERE id = ?",
                (
                    customer_id,
                    customer_id,
                    yz_open_id,
                    yz_open_id,
                    display_name,
                    display_name,
                    is_member,
                    is_member,
                    card_alias,
                    card_alias,
                    card_no,
                    card_no,
                    card_status,
                    card_status,
                    points,
                    points,
                    stored_value_fen,
                    stored_value_fen,
                    now,
                    int(existing["id"]),
                ),
            )

    async def get_stored_value_fen(self, mobile: str) -> int:
        """读取会员储值余额（分），账户不存在返回 0。"""
        rows = await self._db.execute_fetchall(
            "SELECT stored_value_fen FROM member_balance WHERE mobile = ? LIMIT 1",
            (mobile,),
        )
        return int(rows[0]["stored_value_fen"]) if rows else 0

    async def get_points(self, mobile: str) -> int:
        """读取会员积分余额，账户不存在返回 0。"""
        rows = await self._db.execute_fetchall(
            "SELECT points FROM member_balance WHERE mobile = ? LIMIT 1",
            (mobile,),
        )
        return int(rows[0]["points"]) if rows else 0

    async def credit_points(self, mobile: str, amount: int) -> int:
        """为会员积分加款（发分/退回抵扣），返回加款后余额。"""
        now = now_str()
        cursor = await self._db.execute(
            "UPDATE member_balance SET points = points + ?, updated_at = ? "
            "WHERE mobile = ?",
            (amount, now, mobile),
        )
        if cursor.rowcount != 1:
            await self._db.execute(
                "INSERT INTO member_balance (mobile, points, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (mobile, amount, now, now),
            )
        rows = await self._db.execute_fetchall(
            "SELECT points FROM member_balance WHERE mobile = ? LIMIT 1",
            (mobile,),
        )
        return int(rows[0]["points"]) if rows else amount

    async def deduct_points_if_sufficient(self, mobile: str, amount: int) -> bool:
        """原子扣减积分，余额不足时不扣减。"""
        cursor = await self._db.execute(
            "UPDATE member_balance SET points = points - ?, updated_at = ? "
            "WHERE mobile = ? AND points >= ?",
            (amount, now_str(), mobile, amount),
        )
        return bool(cursor.rowcount == 1)

    async def credit_stored_value(self, mobile: str, amount_fen: int) -> int:
        """为会员储值余额加款（充值/退款），返回加款后余额。"""
        now = now_str()
        cursor = await self._db.execute(
            "UPDATE member_balance SET stored_value_fen = stored_value_fen + ?, "
            "updated_at = ? WHERE mobile = ?",
            (amount_fen, now, mobile),
        )
        if cursor.rowcount != 1:
            await self._db.execute(
                "INSERT INTO member_balance (mobile, stored_value_fen, created_at, "
                "updated_at) VALUES (?, ?, ?, ?)",
                (mobile, amount_fen, now, now),
            )
        rows = await self._db.execute_fetchall(
            "SELECT stored_value_fen FROM member_balance WHERE mobile = ? LIMIT 1",
            (mobile,),
        )
        return int(rows[0]["stored_value_fen"]) if rows else amount_fen

    async def deduct_stored_value_if_sufficient(
        self,
        mobile: str,
        amount_fen: int,
    ) -> bool:
        """原子扣减储值余额，余额不足时不扣减。"""
        cursor = await self._db.execute(
            "UPDATE member_balance SET stored_value_fen = stored_value_fen - ?, "
            "updated_at = ? WHERE mobile = ? AND stored_value_fen >= ?",
            (amount_fen, now_str(), mobile, amount_fen),
        )
        return bool(cursor.rowcount == 1)
