"""有赞订单交易数据访问层。"""

from typing import Any

from app.models.employee_agent import OrderQueryPlan
from app.models.order import YouzanOrderData
from app.repository.base import BaseRepository


ORDER_SELECT_FIELDS = (
    "order_no, buyer_id, status, amount_fen, logistics_no, "
    "logistics_status, product_titles, total_quantity, "
    "pay_time, consign_time, pay_type_str, express_type, refund_state, "
    "post_fee_fen, discount_fen, delivery_province, delivery_city, "
    "delivery_district, delivery_time, outer_user_id, order_items_json, "
    "created_at, updated_at"
)
ORDER_TIME_EXPR = "substr(COALESCE(NULLIF(pay_time, ''), created_at), 1, 10)"
DELIVERY_TIME_EXPR = "substr(delivery_time, 1, 10)"
ORDER_DATE_EXPR = "COALESCE(NULLIF(pay_time, ''), created_at, updated_at)"
DELIVERY_CLOCK_EXPR = "substr(delivery_time, 12, 5)"
ORDER_DATE_FILTER_SQL = {
    "order_time": ORDER_TIME_EXPR,
    "delivery_time": DELIVERY_TIME_EXPR,
}
ORDER_SORT_SQL = {
    "latest": ORDER_DATE_EXPR + " DESC, order_no DESC",
    "amount": "amount_fen DESC, " + ORDER_DATE_EXPR + " DESC",
    "delivery_time": "delivery_time ASC, " + ORDER_DATE_EXPR + " DESC",
}
ORDER_FULFILLMENT_RISK_STATUSES = (
    "WAIT_SELLER_SEND_GOODS",
    "WAIT_BUYER_CONFIRM_GOODS",
)


class YouzanOrderRepo(BaseRepository):
    """有赞订单交易大宽表仓库。"""

    async def get_by_order_no(self, order_no: str) -> dict | None:
        """根据订单号获取订单宽表数据。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + ORDER_SELECT_FIELDS + " FROM youzan_orders WHERE order_no = ?",
            (order_no,),
        )
        return dict(rows[0]) if rows else None

    async def get_by_order_no_for_identity(
        self,
        order_no: str,
        *,
        buyer_id: str | None,
        outer_user_id: str | None,
    ) -> dict | None:
        """按订单号和可信买家身份获取订单宽表数据。"""
        normalized_buyer_id = (buyer_id or "").strip()
        normalized_outer_user_id = (outer_user_id or "").strip()
        if not normalized_buyer_id and not normalized_outer_user_id:
            return None
        rows = await self._db.execute_fetchall(
            "SELECT " + ORDER_SELECT_FIELDS + " FROM youzan_orders "
            "WHERE order_no = ? "
            "AND ((? <> '' AND buyer_id = ?) "
            "OR (? <> '' AND outer_user_id = ?))",
            (
                order_no,
                normalized_buyer_id,
                normalized_buyer_id,
                normalized_outer_user_id,
                normalized_outer_user_id,
            ),
        )
        return dict(rows[0]) if rows else None

    async def search_orders(self, keyword: str, limit: int = 5) -> list[dict]:
        """按订单号、买家标识、商品和配送字段搜索有赞订单。"""
        normalized_keyword = keyword.strip()
        if not normalized_keyword:
            return []
        like_keyword = f"%{normalized_keyword}%"
        rows = await self._db.execute_fetchall(
            "SELECT " + ORDER_SELECT_FIELDS + " "
            "FROM youzan_orders "
            "WHERE order_no LIKE ? "
            "OR buyer_id LIKE ? "
            "OR outer_user_id LIKE ? "
            "OR product_titles LIKE ? "
            "OR delivery_province LIKE ? "
            "OR delivery_city LIKE ? "
            "OR delivery_district LIKE ? "
            "OR delivery_time LIKE ? "
            "OR order_items_json LIKE ? "
            "ORDER BY COALESCE(pay_time, created_at, updated_at) DESC, order_no DESC "
            "LIMIT ?",
            (
                like_keyword,
                like_keyword,
                like_keyword,
                like_keyword,
                like_keyword,
                like_keyword,
                like_keyword,
                like_keyword,
                like_keyword,
                limit,
            ),
        )
        return [dict(row) for row in rows]

    async def list_recent_orders(self, limit: int = 5) -> list[dict]:
        """返回最近有赞订单，用于员工询问“最近订单”时兜底。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + ORDER_SELECT_FIELDS + " "
            "FROM youzan_orders "
            "ORDER BY COALESCE(pay_time, created_at, updated_at) DESC, order_no DESC "
            "LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in rows]

    async def query_orders(self, plan: OrderQueryPlan) -> list[dict]:
        """按白名单订单查询计划返回订单明细。"""
        where_sql, params = _build_order_where(plan)
        order_sql = ORDER_SORT_SQL.get(plan.sort_by, ORDER_SORT_SQL["latest"])
        rows = await self._db.execute_fetchall(
            "SELECT "
            + ORDER_SELECT_FIELDS
            + " FROM youzan_orders "
            + where_sql
            + " ORDER BY "
            + order_sql
            + " LIMIT ?",
            (*params, plan.limit),
        )
        return [dict(row) for row in rows]

    async def summarize_orders(self, plan: OrderQueryPlan) -> dict[str, Any]:
        """按白名单订单查询计划返回统计摘要。"""
        where_sql, params = _build_order_where(plan)
        rows = await self._db.execute_fetchall(
            "SELECT COUNT(*) AS total_count, "
            "COALESCE(SUM(amount_fen), 0) AS total_amount_fen "
            "FROM youzan_orders " + where_sql,
            tuple(params),
        )
        status_rows = await self._db.execute_fetchall(
            "SELECT status, COUNT(*) AS count "
            "FROM youzan_orders "
            + where_sql
            + " GROUP BY status ORDER BY count DESC, status ASC",
            tuple(params),
        )
        summary: dict[str, Any] = (
            dict(rows[0]) if rows else {"total_count": 0, "total_amount_fen": 0}
        )
        summary["status_counts"] = {
            str(row["status"]): int(row["count"] or 0) for row in status_rows
        }
        return summary

    async def list_top_products(self, plan: OrderQueryPlan) -> list[dict]:
        """按订单商品标题聚合，返回员工粗略销量排行。"""
        where_sql, params = _build_order_where(plan)
        rows = await self._db.execute_fetchall(
            "SELECT product_titles, "
            "COUNT(*) AS order_count, "
            "COALESCE(SUM(total_quantity), 0) AS total_quantity, "
            "COALESCE(SUM(amount_fen), 0) AS total_amount_fen "
            "FROM youzan_orders " + where_sql + " GROUP BY product_titles "
            "ORDER BY total_quantity DESC, order_count DESC, product_titles ASC "
            "LIMIT ?",
            (*params, plan.limit),
        )
        return [dict(row) for row in rows]

    async def upsert_order(self, data: YouzanOrderData) -> None:
        """原子化 upsert 订单交易数据。"""
        await self._db.execute(
            "INSERT INTO youzan_orders ("
            "order_no, buyer_id, status, amount_fen, logistics_no, logistics_status, "
            "product_titles, total_quantity, pay_time, consign_time, pay_type_str, "
            "express_type, refund_state, post_fee_fen, discount_fen, "
            "delivery_province, delivery_city, delivery_district, delivery_time, "
            "outer_user_id, order_items_json, created_at, updated_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(order_no) DO UPDATE SET "
            "buyer_id = excluded.buyer_id, "
            "status = excluded.status, "
            "amount_fen = excluded.amount_fen, "
            "logistics_no = excluded.logistics_no, "
            "logistics_status = excluded.logistics_status, "
            "product_titles = excluded.product_titles, "
            "total_quantity = excluded.total_quantity, "
            "pay_time = excluded.pay_time, "
            "consign_time = excluded.consign_time, "
            "pay_type_str = excluded.pay_type_str, "
            "express_type = excluded.express_type, "
            "refund_state = excluded.refund_state, "
            "post_fee_fen = excluded.post_fee_fen, "
            "discount_fen = excluded.discount_fen, "
            "delivery_province = excluded.delivery_province, "
            "delivery_city = excluded.delivery_city, "
            "delivery_district = excluded.delivery_district, "
            "delivery_time = excluded.delivery_time, "
            "outer_user_id = excluded.outer_user_id, "
            "order_items_json = excluded.order_items_json, "
            "updated_at = excluded.updated_at "
            "WHERE excluded.updated_at > youzan_orders.updated_at",
            (
                data.order_no,
                data.buyer_id,
                data.status,
                data.amount_fen,
                data.logistics_no,
                data.logistics_status,
                data.product_titles,
                data.total_quantity,
                data.pay_time,
                data.consign_time,
                data.pay_type_str,
                data.express_type,
                data.refund_state,
                data.post_fee_fen,
                data.discount_fen,
                data.delivery_province,
                data.delivery_city,
                data.delivery_district,
                data.delivery_time,
                data.outer_user_id,
                data.order_items_json,
                data.created_at,
                data.updated_at,
            ),
        )
        await self._db.commit()


def _build_order_where(plan: OrderQueryPlan) -> tuple[str, list[object]]:
    clauses = ["1 = 1"]
    params: list[object] = []
    date_expr = ORDER_DATE_FILTER_SQL.get(plan.date_field, ORDER_TIME_EXPR)
    if plan.date_from:
        clauses.append(date_expr + " >= ?")
        params.append(plan.date_from)
    if plan.date_to:
        clauses.append(date_expr + " <= ?")
        params.append(plan.date_to)
    effective_statuses = plan.statuses
    if plan.needs_fulfillment_risk and not effective_statuses:
        effective_statuses = ORDER_FULFILLMENT_RISK_STATUSES
    if effective_statuses:
        placeholders = ",".join("?" for _ in effective_statuses)
        clauses.append("status IN (" + placeholders + ")")
        params.extend(effective_statuses)
    if plan.buyer_id:
        clauses.append("buyer_id = ?")
        params.append(plan.buyer_id)
    if plan.keyword:
        like_keyword = f"%{plan.keyword}%"
        clauses.append(
            "(product_titles LIKE ? OR order_items_json LIKE ? OR order_no LIKE ?)"
        )
        params.extend([like_keyword, like_keyword, like_keyword])
    if plan.needs_missing_logistics:
        clauses.append("(logistics_no = '' OR logistics_no IS NULL)")
    if plan.needs_refund:
        clauses.append("refund_state != 0")
    if plan.needs_fulfillment_risk:
        clauses.append("delivery_time IS NOT NULL AND delivery_time != ''")
    if plan.delivery_time_start or plan.delivery_time_end:
        clauses.append("delivery_time IS NOT NULL AND delivery_time != ''")
    if plan.delivery_time_start:
        clauses.append(DELIVERY_CLOCK_EXPR + " >= ?")
        params.append(plan.delivery_time_start)
    if plan.delivery_time_end:
        clauses.append(DELIVERY_CLOCK_EXPR + " <= ?")
        params.append(plan.delivery_time_end)
    return "WHERE " + " AND ".join(clauses), params
