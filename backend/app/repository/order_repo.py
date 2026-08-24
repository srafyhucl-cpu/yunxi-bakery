"""自研小程序订单数据访问层。"""

from app.models.order import Order, OrderStatus
from app.repository.base import BaseRepository

PAYMENT_STATUS_SQL = (
    "CASE WHEN json_valid(payment) "
    "THEN COALESCE(json_extract(payment, '$.status'), 'unpaid') "
    "ELSE 'unpaid' END"
)


class OrderRepo(BaseRepository):
    """自研小程序订单仓库。"""

    async def create_order(self, order: Order) -> None:
        """创建小程序订单。"""
        await self._db.execute(
            "INSERT INTO orders ("
            "id, session_id, channel, user_id, products, total_amount, "
            "delivery, payment, status, remark, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                order.id,
                order.session_id,
                order.channel,
                order.user_id,
                order.products,
                order.total_amount,
                order.delivery,
                getattr(order, "payment", "{}"),
                order.status.value
                if hasattr(order.status, "value")
                else str(order.status),
                order.remark,
                order.created_at,
                order.updated_at,
            ),
        )

    async def list_by_user(self, user_id: str, *, limit: int = 50) -> list[Order]:
        """按用户读取订单。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, session_id, channel, user_id, products, total_amount, "
            "delivery, payment, status, remark, created_at, updated_at "
            "FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [Order(**dict(row)) for row in rows]

    async def get_order(self, order_id: str) -> Order | None:
        """按订单号读取订单。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, session_id, channel, user_id, products, total_amount, "
            "delivery, payment, status, remark, created_at, updated_at "
            "FROM orders WHERE id = ? LIMIT 1",
            (order_id,),
        )
        return Order(**dict(rows[0])) if rows else None

    async def update_status(
        self, order_id: str, status: str, updated_at: str
    ) -> Order | None:
        """更新订单履约状态并返回最新订单。"""
        await self._db.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
            (status, updated_at, order_id),
        )
        return await self.get_order(order_id)

    async def cancel_unpaid_order(self, order_id: str, updated_at: str) -> Order | None:
        """原子取消未支付且仍可取消的订单。"""
        cursor = await self._db.execute(
            "UPDATE orders SET status = ?, updated_at = ? "
            "WHERE id = ? AND status IN ('pending', 'confirmed') "
            "AND " + PAYMENT_STATUS_SQL + " IN ('unpaid', 'partial')",
            (OrderStatus.CANCELLED.value, updated_at, order_id),
        )
        if cursor.rowcount != 1:
            return None
        return await self.get_order(order_id)

    async def update_payment(
        self, order_id: str, payment: str, updated_at: str
    ) -> Order | None:
        """更新订单支付状态并返回最新订单。"""
        await self._db.execute(
            "UPDATE orders SET payment = ?, updated_at = ? WHERE id = ?",
            (payment, updated_at, order_id),
        )
        return await self.get_order(order_id)

    async def update_payment_if_unpaid_active(
        self, order_id: str, payment: str, updated_at: str
    ) -> Order | None:
        """原子写入支付状态，拒绝取消订单或已处理订单的覆盖写。"""
        cursor = await self._db.execute(
            "UPDATE orders SET payment = ?, updated_at = ? "
            "WHERE id = ? AND status != 'cancelled' AND "
            + PAYMENT_STATUS_SQL
            + " = 'unpaid'",
            (payment, updated_at, order_id),
        )
        if cursor.rowcount != 1:
            return None
        return await self.get_order(order_id)

    async def update_payment_to_partial_if_unpaid_active(
        self,
        order_id: str,
        payment: str,
        updated_at: str,
    ) -> Order | None:
        """原子把未支付订单写入组合支付中间态（余额部分已扣）。"""
        cursor = await self._db.execute(
            "UPDATE orders SET payment = ?, updated_at = ? "
            "WHERE id = ? AND status != 'cancelled' AND "
            + PAYMENT_STATUS_SQL
            + " = 'unpaid'",
            (payment, updated_at, order_id),
        )
        if cursor.rowcount != 1:
            return None
        return await self.get_order(order_id)

    async def update_payment_to_partial_if_unpaid_or_partial_active(
        self,
        order_id: str,
        payment: str,
        updated_at: str,
    ) -> Order | None:
        """原子把未支付或已部分支付订单更新为新的组合支付中间态。"""
        cursor = await self._db.execute(
            "UPDATE orders SET payment = ?, updated_at = ? "
            "WHERE id = ? AND status != 'cancelled' AND "
            + PAYMENT_STATUS_SQL
            + " IN ('unpaid', 'partial')",
            (payment, updated_at, order_id),
        )
        if cursor.rowcount != 1:
            return None
        return await self.get_order(order_id)

    async def update_payment_to_paid_if_unpaid_or_partial_active(
        self,
        order_id: str,
        payment: str,
        updated_at: str,
    ) -> Order | None:
        """原子完成支付：未支付或组合支付中间态均可流转到已支付。"""
        cursor = await self._db.execute(
            "UPDATE orders SET payment = ?, updated_at = ? "
            "WHERE id = ? AND status != 'cancelled' AND "
            + PAYMENT_STATUS_SQL
            + " IN ('unpaid', 'partial')",
            (payment, updated_at, order_id),
        )
        if cursor.rowcount != 1:
            return None
        return await self.get_order(order_id)

    async def close_unpaid_order(
        self, order_id: str, payment: str, updated_at: str
    ) -> Order | None:
        """原子关闭未支付订单并写入超时支付状态。"""
        cursor = await self._db.execute(
            "UPDATE orders SET payment = ?, status = ?, updated_at = ? "
            "WHERE id = ? AND status != 'cancelled' AND "
            + PAYMENT_STATUS_SQL
            + " IN ('unpaid', 'partial')",
            (
                payment,
                OrderStatus.CANCELLED.value,
                updated_at,
                order_id,
            ),
        )
        if cursor.rowcount != 1:
            return None
        return await self.get_order(order_id)

    async def get_payment_transaction_order_id(self, transaction_id: str) -> str | None:
        """按微信交易号读取已绑定的订单号。"""
        rows = await self._db.execute_fetchall(
            "SELECT order_id FROM payment_transactions WHERE transaction_id = ? LIMIT 1",
            (transaction_id,),
        )
        return str(rows[0]["order_id"]) if rows else None

    async def claim_payment_transaction(
        self, transaction_id: str, order_id: str, created_at: str
    ) -> bool:
        """原子认领微信交易号，防止交易号重复入账。"""
        cursor = await self._db.execute(
            "INSERT OR IGNORE INTO payment_transactions "
            "(transaction_id, order_id, created_at) VALUES (?, ?, ?)",
            (transaction_id, order_id, created_at),
        )
        return bool(cursor.rowcount == 1)

    async def list_orders(
        self,
        *,
        keyword: str = "",
        status: str = "",
        board_filter: str = "",
        limit: int = 30,
        offset: int = 0,
    ) -> list[Order]:
        """后台分页读取订单。"""
        clauses, params = self._build_where(
            keyword=keyword,
            status=status,
            board_filter=board_filter,
        )
        rows = await self._db.execute_fetchall(
            "SELECT id, session_id, channel, user_id, products, total_amount, "
            "delivery, payment, status, remark, created_at, updated_at "
            "FROM orders WHERE " + " AND ".join(clauses) + " "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return [Order(**dict(row)) for row in rows]

    async def list_by_status(self, status: str, *, limit: int = 200) -> list[Order]:
        """按履约状态读取订单，供后台任务扫描。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, session_id, channel, user_id, products, total_amount, "
            "delivery, payment, status, remark, created_at, updated_at "
            "FROM orders WHERE status = ? ORDER BY created_at ASC LIMIT ?",
            (status, limit),
        )
        return [Order(**dict(row)) for row in rows]

    async def count_orders(
        self,
        *,
        keyword: str = "",
        status: str = "",
        board_filter: str = "",
    ) -> int:
        """后台统计订单数量。"""
        clauses, params = self._build_where(
            keyword=keyword,
            status=status,
            board_filter=board_filter,
        )
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS c FROM orders WHERE " + " AND ".join(clauses),
            tuple(params),
        )
        return int(rows[0]["c"]) if rows else 0

    async def summarize_orders(self, *, keyword: str = "") -> list[dict]:
        """按履约状态和支付状态聚合订单数量与金额。"""
        clauses, params = self._build_where(keyword=keyword, status="", board_filter="")
        rows = await self._db.execute_fetchall(
            "SELECT status, " + PAYMENT_STATUS_SQL + " AS payment_status, "
            "COUNT(*) AS order_count, "
            "COALESCE(SUM(total_amount), 0) AS total_amount "
            "FROM orders WHERE "
            + " AND ".join(clauses)
            + " GROUP BY status, payment_status",
            tuple(params),
        )
        return [dict(row) for row in rows]

    def _build_where(
        self,
        *,
        keyword: str,
        status: str,
        board_filter: str = "",
    ) -> tuple[list[str], list[object]]:
        clauses = ["1 = 1"]
        params: list[object] = []
        if keyword:
            like = f"%{keyword}%"
            clauses.append(
                "(id LIKE ? OR user_id LIKE ? OR products LIKE ? OR delivery LIKE ? OR remark LIKE ?)"
            )
            params.extend([like, like, like, like, like])
        if status:
            clauses.append("status = ?")
            params.append(status)
        clauses.extend(self._board_filter_clauses(board_filter))
        return clauses, params

    def _board_filter_clauses(self, board_filter: str) -> list[str]:
        if board_filter == "unpaid":
            return [PAYMENT_STATUS_SQL + " = 'unpaid'", "status != 'cancelled'"]
        if board_filter == "pending":
            return ["status = 'pending'"]
        if board_filter == "fulfilling":
            return ["status IN ('confirmed', 'making', 'delivering')"]
        if board_filter == "done":
            return ["status = 'done'"]
        if board_filter == "closed":
            return ["(status = 'cancelled' OR " + PAYMENT_STATUS_SQL + " = 'expired')"]
        return []
