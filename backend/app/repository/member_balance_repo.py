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
        """按手机号读取会员余额快照（包含实充本金与赠送金）。"""
        try:
            rows = await self._db.execute_fetchall(
                "SELECT id, customer_id, mobile, yz_open_id, display_name, is_member, "
                "card_alias, card_no, card_status, points, stored_value_fen, "
                "principal_fen, bonus_fen, "
                "created_at, updated_at FROM member_balance WHERE mobile = ? LIMIT 1",
                (mobile,),
            )
        except Exception:
            rows = await self._db.execute_fetchall(
                "SELECT id, customer_id, mobile, yz_open_id, display_name, is_member, "
                "card_alias, card_no, card_status, points, stored_value_fen, "
                "created_at, updated_at FROM member_balance WHERE mobile = ? LIMIT 1",
                (mobile,),
            )
        if not rows:
            return None
        res = dict(rows[0])
        if "principal_fen" not in res:
            res["principal_fen"] = int(res.get("stored_value_fen", 0) or 0)
            res["bonus_fen"] = 0
        return res

    async def get_by_openid(self, yz_open_id: str) -> dict | None:
        """按有赞 openid 读取会员余额快照。"""
        if not yz_open_id:
            return None
        try:
            rows = await self._db.execute_fetchall(
                "SELECT id, customer_id, mobile, yz_open_id, display_name, is_member, "
                "card_alias, card_no, card_status, points, stored_value_fen, "
                "principal_fen, bonus_fen, "
                "created_at, updated_at FROM member_balance WHERE yz_open_id = ? LIMIT 1",
                (yz_open_id,),
            )
        except Exception:
            rows = await self._db.execute_fetchall(
                "SELECT id, customer_id, mobile, yz_open_id, display_name, is_member, "
                "card_alias, card_no, card_status, points, stored_value_fen, "
                "created_at, updated_at FROM member_balance WHERE yz_open_id = ? LIMIT 1",
                (yz_open_id,),
            )
        if not rows:
            return None
        res = dict(rows[0])
        if "principal_fen" not in res:
            res["principal_fen"] = int(res.get("stored_value_fen", 0) or 0)
            res["bonus_fen"] = 0
        return res

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
        stored_value_fen: int | None = None,
    ) -> None:
        """按 mobile（openid 兜底）幂等合并会员身份/卡片/余额快照。

        B3.5（评审问题 1）：账务仓储**不自提交**，由调用方命令独占事务边界
        （member_loyalty 导入 / youzan 会员事件 / 支付链路外层事务提交）。

        r79（`M-20260926-030`）：**积分余额不再由本方法写入**。此前本方法
        用 `points = CASE WHEN ? IS NOT NULL THEN ? ELSE points END` 绝对覆盖
        `points`，而本地发分/扣减走 `credit_points`/`deduct_points_if_sufficient`
        的相对增量，两种不兼容语义共用同一列，导致外部镜像抹掉本地账本净额。
        外部权威积分一律改走 `mirror_youzan_points`（锚点 + 偏移），本地账本
        继续走相对增量，两条路径不再共用同一列的同一含义。`points` 参数已
        从签名中移除，使这一误用无法再次通过编译与静态检查。
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
                    0,
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
                    stored_value_fen,
                    stored_value_fen,
                    now,
                    int(existing["id"]),
                ),
            )

    async def mirror_youzan_points(
        self,
        *,
        mobile: str,
        yz_open_id: str = "",
        customer_id: str = "",
        youzan_total: int,
    ) -> int:
        """把有赞侧权威积分总额镜像进本地余额，返回镜像后余额。

        r79（`M-20260926-030`）：余额恒等于
        `youzan_points_base`（外部权威锚点）+ 本地账本净额。本方法只移动锚点
        并按偏移量重算余额，**不触碰本地账本已写入的净额**：

        - 有赞侧积分变动（用户在有赞店铺消费/获取）表现为 `youzan_total` 的变化，
          该变化被如实带入本地余额；
        - 小程序订单发分、抵扣扣减、退款退返与退收回滚产生的净额原样保留，
          既不会被外部镜像抹掉，也不会被镜像凭空还回来。

        偏移量在同一条 `UPDATE` 内由 `points - youzan_points_base` 现算，
        读写同一行由 SQLite 写锁串行化，不存在读到陈旧偏移的窗口。
        """
        now = now_str()
        existing = await self.get_by_mobile(mobile) if mobile else None
        if existing is None and yz_open_id:
            existing = await self.get_by_openid(yz_open_id)
        if existing is None:
            if not mobile and not yz_open_id:
                logger.warning("会员余额快照缺少 mobile 与 yz_open_id，跳过积分镜像")
                return 0
            # 首次建档：外部总额即锚点，本地净额为 0。
            await self._db.execute(
                "INSERT INTO member_balance (customer_id, mobile, yz_open_id, points, "
                "youzan_points_base, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    customer_id,
                    mobile,
                    yz_open_id,
                    youzan_total,
                    youzan_total,
                    now,
                    now,
                ),
            )
            return youzan_total
        await self._db.execute(
            "UPDATE member_balance SET "
            "points = ? + (points - youzan_points_base), "
            "youzan_points_base = ?, "
            "customer_id = CASE WHEN ? != '' THEN ? ELSE customer_id END, "
            "yz_open_id = CASE WHEN ? != '' THEN ? ELSE yz_open_id END, "
            "updated_at = ? WHERE id = ?",
            (
                youzan_total,
                youzan_total,
                customer_id,
                customer_id,
                yz_open_id,
                yz_open_id,
                now,
                int(existing["id"]),
            ),
        )
        rows = await self._db.execute_fetchall(
            "SELECT points FROM member_balance WHERE id = ?", (int(existing["id"]),)
        )
        return int(rows[0]["points"]) if rows else youzan_total

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

    async def credit_stored_value(
        self, mobile: str, amount_fen: int, bonus_fen: int = 0
    ) -> int:
        """为会员储值余额加款（充值/退款），支持指定赠送金额，返回加款后余额。"""
        now = now_str()
        principal_addition = amount_fen - bonus_fen
        try:
            cursor = await self._db.execute(
                "UPDATE member_balance SET stored_value_fen = stored_value_fen + ?, "
                "principal_fen = principal_fen + ?, bonus_fen = bonus_fen + ?, "
                "updated_at = ? WHERE mobile = ?",
                (amount_fen, principal_addition, bonus_fen, now, mobile),
            )
            if cursor.rowcount != 1:
                await self._db.execute(
                    "INSERT INTO member_balance (mobile, stored_value_fen, principal_fen, "
                    "bonus_fen, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (mobile, amount_fen, principal_addition, bonus_fen, now, now),
                )
        except Exception:
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
        """原子扣减储值余额，余额不足时不扣减。优先扣减赠送金，不足部分扣减本金。"""
        now = now_str()
        try:
            row = await self.get_by_mobile(mobile)
            if not row or int(row.get("stored_value_fen", 0)) < amount_fen:
                return False
            curr_bonus = int(row.get("bonus_fen", 0) or 0)
            deduct_bonus = min(curr_bonus, amount_fen)
            deduct_principal = amount_fen - deduct_bonus
            cursor = await self._db.execute(
                "UPDATE member_balance SET stored_value_fen = stored_value_fen - ?, "
                "bonus_fen = bonus_fen - ?, principal_fen = principal_fen - ?, "
                "updated_at = ? WHERE mobile = ? AND stored_value_fen >= ?",
                (amount_fen, deduct_bonus, deduct_principal, now, mobile, amount_fen),
            )
            return bool(cursor.rowcount == 1)
        except Exception:
            cursor = await self._db.execute(
                "UPDATE member_balance SET stored_value_fen = stored_value_fen - ?, "
                "updated_at = ? WHERE mobile = ? AND stored_value_fen >= ?",
                (amount_fen, now, mobile, amount_fen),
            )
            return bool(cursor.rowcount == 1)
