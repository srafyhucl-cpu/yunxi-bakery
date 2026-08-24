"""优惠券库存数据访问层。"""

import aiosqlite

from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.repository.base import BaseRepository, DatabaseHandle
from app.utils import now_str


class CouponInventoryRepo(BaseRepository):
    """优惠券生命周期记录仓储（coupon_id+status+mobile 组合去重）。"""

    _COLS = (
        "id, coupon_id, coupon_group_id, customer_id, mobile, status, order_no, "
        "title, value_fen, detail_json, source, occurred_at, created_at, "
        "template_id, valid_from, valid_until, deducted_fen, consumed_at, refunded_at"
    )

    def __init__(self, db: DatabaseHandle | aiosqlite.Connection | None = None) -> None:
        """测试注入裸 aiosqlite 连接时统一包装为 DatabaseHandle。"""
        if db is not None and not isinstance(db, DatabaseHandle):
            db = DatabaseHandle(db)
        super().__init__(db)

    async def get_by_dedup_key(
        self, coupon_id: str, status: str, mobile: str
    ) -> dict | None:
        """按组合去重键读取优惠券记录。"""
        if not coupon_id or not status:
            return None
        rows = await self._db.execute_fetchall(
            "SELECT id, coupon_id, coupon_group_id, customer_id, mobile, status, "
            "order_no, title, value_fen, detail_json, source, occurred_at, created_at, "
            "template_id, valid_from, valid_until, deducted_fen, consumed_at, refunded_at "
            "FROM coupon_inventory "
            "WHERE coupon_id = ? AND status = ? AND mobile = ? LIMIT 1",
            (coupon_id, status, mobile),
        )
        return rows[0] if rows else None

    async def insert(self, entry: CouponInventoryEntry) -> None:
        """写入一条优惠券生命周期记录（含模板/有效期/核销回填列）。

        B3.5（评审问题 1）：账务仓储**不自提交**，由调用方统一支付应用服务 /
        发券 / 摄取命令独占事务边界（外层 transaction 或 db_session_scope 提交）。
        """
        await self._db.execute(
            "INSERT INTO coupon_inventory (coupon_id, coupon_group_id, customer_id, "
            "mobile, status, order_no, title, value_fen, detail_json, source, "
            "occurred_at, created_at, template_id, valid_from, valid_until, "
            "deducted_fen, consumed_at, refunded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.coupon_id,
                entry.coupon_group_id,
                entry.customer_id,
                entry.mobile,
                entry.status,
                entry.order_no,
                entry.title,
                entry.value_fen,
                entry.detail_json,
                entry.source,
                entry.occurred_at,
                now_str(),
                entry.template_id,
                entry.valid_from,
                entry.valid_until,
                entry.deducted_fen,
                entry.consumed_at,
                entry.refunded_at,
            ),
        )

    async def list_by_mobile(
        self, mobile: str, *, authority: str = "youzan", limit: int = 100
    ) -> list[dict]:
        """我的券列表：ROW_NUMBER 按券取最新状态行（来源权重 + 时间）。"""
        rank = (
            "CASE source WHEN 'order' THEN 2 WHEN 'local' THEN 2 ELSE 1 END"
            if authority != "local"
            else "2"
        )
        source_filter = (
            "" if authority == "youzan" else " AND source IN ('order', 'local')"
        )
        return await self._db.execute_fetchall(
            "SELECT " + self._COLS + " FROM ("
            "SELECT " + self._COLS + ", "
            "ROW_NUMBER() OVER (PARTITION BY coupon_id "
            "ORDER BY "
            + rank
            + " DESC, occurred_at DESC, created_at DESC, id DESC) AS rn "
            "FROM coupon_inventory WHERE mobile = ?" + source_filter + " "
            ") WHERE rn = 1 ORDER BY occurred_at DESC, id DESC LIMIT ?",
            (mobile, limit),
        )

    async def get_latest_state(
        self, coupon_id: str, mobile: str, *, authority: str = "youzan"
    ) -> dict | None:
        """读取券最新状态行（来源权重 + 时间）。"""
        source_filter = (
            "" if authority == "youzan" else " AND source IN ('order', 'local')"
        )
        rows = await self._db.execute_fetchall(
            "SELECT " + self._COLS + ", "
            "CASE source WHEN 'order' THEN 2 WHEN 'local' THEN 2 ELSE 1 END AS src_rank "
            "FROM coupon_inventory WHERE coupon_id = ? AND mobile = ?"
            + source_filter
            + " "
            "ORDER BY src_rank DESC, occurred_at DESC, created_at DESC, id DESC LIMIT 1",
            (coupon_id, mobile),
        )
        return rows[0] if rows else None

    async def consume(
        self,
        coupon_id: str,
        mobile: str,
        *,
        order_no: str,
        deducted_fen: int,
        consumed_at: str,
        occurred_at: str,
        authority: str = "youzan",
    ) -> dict | None:
        """核销：基于最新 TAKE 行插入 order 来源 CONSUME 行。

        authority 默认 youzan（import/webhook 均为有效来源）；local 模式只认
        order/local 行。由 service 层传入 settings.COUPON_AUTHORITY，禁止硬编码。
        """
        latest = await self.get_latest_state(coupon_id, mobile, authority=authority)
        if latest is None or latest["status"] != CouponStatus.TAKE:
            return None
        valid_until = str(latest.get("valid_until", "") or "")
        if valid_until and consumed_at[:10] > valid_until[:10]:
            return None
        entry = CouponInventoryEntry(
            coupon_id=coupon_id,
            status=CouponStatus.CONSUME,
            mobile=mobile,
            coupon_group_id=str(latest.get("coupon_group_id", "")),
            customer_id=str(latest.get("customer_id", "")),
            order_no=order_no,
            title=str(latest.get("title", "")),
            value_fen=int(latest.get("value_fen", 0) or 0),
            detail_json=str(latest.get("detail_json", "{}")),
            source=LedgerSource.ORDER,
            occurred_at=occurred_at,
            template_id=str(latest.get("template_id", "")),
            valid_from=str(latest.get("valid_from", "")),
            valid_until=valid_until,
            deducted_fen=max(0, int(deducted_fen or 0)),
            consumed_at=consumed_at,
        )
        await self.insert(entry)
        return entry

    async def refund(
        self,
        coupon_id: str,
        mobile: str,
        *,
        order_no: str,
        refunded_at: str,
        occurred_at: str,
        authority: str = "youzan",
    ) -> dict | None:
        """退回：基于最新 CONSUME 行插入 order 来源 BACK 行。"""
        latest = await self.get_latest_state(coupon_id, mobile, authority=authority)
        if latest is None or latest["status"] != CouponStatus.CONSUME:
            return None
        entry = CouponInventoryEntry(
            coupon_id=coupon_id,
            status=CouponStatus.BACK,
            mobile=mobile,
            coupon_group_id=str(latest.get("coupon_group_id", "")),
            customer_id=str(latest.get("customer_id", "")),
            order_no=order_no,
            title=str(latest.get("title", "")),
            value_fen=int(latest.get("value_fen", 0) or 0),
            detail_json=str(latest.get("detail_json", "{}")),
            source=LedgerSource.ORDER,
            occurred_at=occurred_at,
            template_id=str(latest.get("template_id", "")),
            valid_from=str(latest.get("valid_from", "")),
            valid_until=str(latest.get("valid_until", "")),
            deducted_fen=int(latest.get("deducted_fen", 0) or 0),
            refunded_at=refunded_at,
        )
        await self.insert(entry)
        return entry

    async def list_by_order(self, order_no: str) -> list[dict]:
        """按订单号查询券核销/退回记录。"""
        return await self._db.execute_fetchall(
            "SELECT " + self._COLS + " FROM coupon_inventory "
            "WHERE order_no = ? ORDER BY id ASC",
            (order_no,),
        )

    async def list_all(
        self,
        *,
        mobile: str = "",
        status: str = "",
        template_id: str = "",
        limit: int = 200,
    ) -> list[dict]:
        """库存明细查询（管理后台）：返回生命周期全部行（含历史），供记录查询。"""
        sql = (
            "SELECT " + self._COLS + ", "
            "CASE source WHEN 'order' THEN 2 WHEN 'local' THEN 2 ELSE 1 END AS src_rank "
            "FROM coupon_inventory WHERE 1=1"
        )
        params: list[object] = []
        if mobile:
            sql += " AND mobile = ?"
            params.append(mobile)
        if status:
            sql += " AND status = ?"
            params.append(status)
        if template_id:
            sql += " AND template_id = ?"
            params.append(template_id)
        sql += " ORDER BY src_rank DESC, occurred_at DESC, created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        return await self._db.execute_fetchall(sql, params)
