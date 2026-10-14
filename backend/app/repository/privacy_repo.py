"""主体隐私数据的导出、删除和生命周期清理仓库。"""

from dataclasses import dataclass
from typing import Any

from app.models.order import Order
from app.repository.base import BaseRepository
from app.utils import subject_identity_candidates


@dataclass(frozen=True)
class PrivacyRetentionCutoffs:
    messages: str
    profiles: str
    retrieval_logs: str
    address_audit: str
    orders: str


class PrivacyRepo(BaseRepository):
    """集中维护主体数据覆盖范围，避免隐私流程散落在业务仓库。"""

    async def list_orders_holding_stored_value(self, user_id: str) -> list[Order]:
        """读取该主体仍占用储值、尚未结清的订单。

        组合支付/余额支付已把储值扣在 `balance_ledger`，而账本对 `orders`
        没有外键。主体删除会连带删除订单，因此删除前必须先把这些订单挑出来
        结清，否则被扣金额失去退款凭据。已支付订单的储值已换货，不属占用。
        """
        rows = await self._fetchall(
            "SELECT id, session_id, channel, user_id, products, total_amount, "
            "delivery, payment, status, remark, created_at, updated_at "
            "FROM orders WHERE user_id = ? "
            "AND COALESCE(json_valid(payment), 0) = 1 "
            "AND COALESCE(json_extract(payment, '$.balanceFen'), 0) > 0 "
            "AND COALESCE(json_extract(payment, '$.status'), 'unpaid') "
            "IN ('unpaid', 'partial')",
            (user_id,),
        )
        return [Order(**row) for row in rows]

    async def list_orders_with_live_wechat_prepay(self, user_id: str) -> list[Order]:
        """读取该主体微信尾款腿仍在途、尚未到账的订单。

        预下单一旦成功，微信侧的支付会话即已生效且我方无法撤销（`create_jsapi_prepay`
        未发送 `time_expire`，会话有效期由微信侧决定），用户在订单被删除后仍可能
        完成付款。付款通知按 `out_trade_no` 回查订单，订单一旦消失，到账资金既
        无法落账也无法建案。因此这类订单必须阻止主体删除，而不是跟着一起删。

        已支付（`paid`）的订单不再阻塞：资金已到账并落账，其余记录随主体删除
        走既有隐私口径。
        """
        rows = await self._fetchall(
            "SELECT id, session_id, channel, user_id, products, total_amount, "
            "delivery, payment, status, remark, created_at, updated_at "
            "FROM orders WHERE user_id = ? "
            "AND COALESCE(json_valid(payment), 0) = 1 "
            "AND COALESCE(json_extract(payment, '$.wechatPrepayFen'), 0) > 0 "
            "AND COALESCE(json_extract(payment, '$.status'), 'unpaid') != 'paid'",
            (user_id,),
        )
        return [Order(**row) for row in rows]

    async def export_subject(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """导出与主体标识直接关联的全部业务记录。"""
        customer_ids = await self._customer_ids(user_id)
        sessions = await self._fetchall(
            "SELECT id, channel, user_id, staff_id, status, extra_info, created_at, updated_at "
            "FROM sessions WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        )
        session_ids = [str(row["id"]) for row in sessions]
        orders = await self._fetchall(
            "SELECT id, session_id, channel, user_id, products, total_amount, delivery, "
            "payment, status, remark, created_at, updated_at FROM orders WHERE user_id = ? "
            "ORDER BY created_at ASC",
            (user_id,),
        )
        order_ids = [str(row["id"]) for row in orders]
        return {
            "sessions": sessions,
            "messages": await self._rows_for_ids(
                "SELECT id, session_id, role, content, channel_msg_id, estimated_tokens, "
                "tool_calls, tool_name, created_at FROM messages WHERE session_id IN ({}) "
                "ORDER BY created_at ASC",
                session_ids,
            ),
            "conversation_summaries": await self._rows_for_user(
                "SELECT id, session_id, channel, user_id, summary_text, state_json, "
                "source_message_ids_json, source_until_message_id, token_estimate, status, "
                "created_at, updated_at FROM conversation_summaries WHERE user_id = ? "
                "ORDER BY created_at ASC",
                user_id,
            ),
            "customer_profiles": await self._rows_for_user(
                "SELECT id, channel, user_id, display_name, preferences_json, "
                "order_summary_json, special_dates_json, allergens_json, consent_status, "
                "source_evidence_json, last_interaction_at, created_at, updated_at "
                "FROM customer_profiles WHERE user_id = ?",
                user_id,
            ),
            "consent": await self._rows_for_user(
                "SELECT channel, user_id, status, created_at, updated_at "
                "FROM customer_consent_ledger WHERE user_id = ?",
                user_id,
            ),
            "customer_master": await self._rows_for_ids(
                "SELECT id, tenant_id, status, merge_into_customer_id, primary_phone, "
                "phone_verified, display_name, gender, birthday, wechat_region, "
                "first_seen_at, last_seen_at, first_source, identity_confidence, "
                "has_youzan_identity, has_miniapp_identity, has_wecom_identity, "
                "created_at, updated_at FROM customer_master WHERE id IN ({})",
                customer_ids,
            ),
            "customer_identity_links": await self._rows_for_subject_or_ids(
                "SELECT id, tenant_id, customer_id, identity_type, identity_value, "
                "identity_value_normalized, source_system, source_record_id, source_label, "
                "link_status, verification_status, confidence_score, first_seen_at, "
                "last_seen_at, created_at, updated_at FROM customer_identity_links "
                "WHERE identity_value = ? OR identity_value_normalized = ?",
                user_id,
                customer_ids,
            ),
            "customer_source_snapshots": await self._rows_for_ids(
                "SELECT id, tenant_id, customer_id, identity_link_id, source_system, "
                "source_object_type, source_record_id, source_batch_id, snapshot_json, "
                "normalized_json, field_hash, captured_at, created_at "
                "FROM customer_source_snapshots WHERE customer_id IN ({})",
                customer_ids,
            ),
            "addresses": await self._rows_for_user(
                "SELECT id, user_id, receiver_name, receiver_phone, address, is_default, "
                "created_at, updated_at FROM miniapp_addresses WHERE user_id = ?",
                user_id,
            ),
            "address_audit": await self._rows_for_user(
                "SELECT id, address_id, user_id, operator, action, before_json, after_json, "
                "note, created_at FROM miniapp_address_audit WHERE user_id = ? "
                "ORDER BY created_at ASC",
                user_id,
            ),
            "orders": orders,
            "order_events": await self._rows_for_ids(
                "SELECT id, order_id, status, operator, note, created_at "
                "FROM order_events WHERE order_id IN ({}) ORDER BY created_at ASC",
                order_ids,
            ),
            "group_registrations": await self._rows_for_user(
                "SELECT id, campaign_id, group_id, user_id, customer_name, customer_phone, "
                "product_name, quantity, fulfillment_method, desired_time, address, remark, "
                "status, created_at, updated_at FROM group_registrations WHERE user_id = ?",
                user_id,
            ),
            "human_transfers": await self._rows_for_user(
                "SELECT id, session_id, user_id, staff_id, reason, status, "
                "conversation_summary, created_at, accepted_at, closed_at "
                "FROM human_transfers WHERE user_id = ? ORDER BY created_at ASC",
                user_id,
            ),
            "analytics_events": await self._fetchall(
                "SELECT id, session_id, buyer_id, event_type, event_source, ref_id, "
                "meta_data, created_at FROM analytics_events WHERE buyer_id = ? "
                "OR session_id IN (SELECT id FROM sessions WHERE user_id = ?)",
                (user_id, user_id),
            ),
            "youzan_orders": await self._fetchall(
                "SELECT order_no, buyer_id, status, amount_fen, logistics_no, logistics_status, "
                "product_titles, total_quantity, pay_time, consign_time, pay_type_str, "
                "express_type, refund_state, post_fee_fen, discount_fen, delivery_province, "
                "delivery_city, delivery_district, delivery_time, outer_user_id, "
                "order_items_json, created_at, updated_at FROM youzan_orders "
                "WHERE buyer_id = ? OR outer_user_id = ?",
                (user_id, user_id),
            ),
        }

    async def delete_subject(self, user_id: str) -> None:
        """删除主体业务数据，并保留 revoked 状态作为合规事实。"""
        customer_ids = await self._customer_ids(user_id)
        await self._db.execute(
            "DELETE FROM conversation_reviews WHERE session_id IN "
            "(SELECT id FROM sessions WHERE user_id = ?)",
            (user_id,),
        )
        await self._db.execute(
            "DELETE FROM messages WHERE session_id IN "
            "(SELECT id FROM sessions WHERE user_id = ?)",
            (user_id,),
        )
        await self._db.execute(
            "DELETE FROM human_transfers WHERE user_id = ? OR session_id IN "
            "(SELECT id FROM sessions WHERE user_id = ?)",
            (user_id, user_id),
        )
        await self._db.execute(
            "DELETE FROM conversation_summaries WHERE user_id = ?", (user_id,)
        )
        await self._db.execute(
            "DELETE FROM order_events WHERE order_id IN "
            "(SELECT id FROM orders WHERE user_id = ?)",
            (user_id,),
        )
        # 硬外键表必须先于 orders 清理：payment_transactions.order_id 与
        # delivery_orders.order_id 均声明 REFERENCES orders(id)，且建库时
        # `PRAGMA foreign_keys = ON`、两张表都是 on_delete=NO ACTION。漏删任一张，
        # 整笔删除事务就会在 DELETE FROM orders 处抛 FOREIGN KEY constraint failed
        # 并回滚——真实支付过或下过闪送单的用户将永久无法行使主体删除权。
        # 认领与配送行都以订单为唯一定位依据，订单本身被删除后已无独立留存价值。
        await self._db.execute(
            "DELETE FROM payment_transactions WHERE order_id IN "
            "(SELECT id FROM orders WHERE user_id = ?)",
            (user_id,),
        )
        await self._db.execute(
            "DELETE FROM delivery_orders WHERE order_id IN "
            "(SELECT id FROM orders WHERE user_id = ?)",
            (user_id,),
        )
        await self._db.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))
        await self._db.execute(
            "DELETE FROM miniapp_address_audit WHERE user_id = ?", (user_id,)
        )
        await self._db.execute(
            "DELETE FROM miniapp_addresses WHERE user_id = ?", (user_id,)
        )
        await self._db.execute(
            "DELETE FROM group_registrations WHERE user_id = ?", (user_id,)
        )
        await self._db.execute(
            "DELETE FROM customer_profiles WHERE user_id = ?", (user_id,)
        )
        await self._db.execute(
            "DELETE FROM analytics_events WHERE buyer_id = ? OR session_id IN "
            "(SELECT id FROM sessions WHERE user_id = ?)",
            (user_id, user_id),
        )
        await self._db.execute(
            "DELETE FROM youzan_orders WHERE buyer_id = ? OR outer_user_id = ?",
            (user_id, user_id),
        )
        await self._delete_customer_records(user_id, customer_ids)
        await self._db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        await self._db.execute(
            "INSERT INTO customer_consent_ledger (channel, user_id, status, created_at, updated_at) "
            "SELECT channel, ?, 'revoked', created_at, datetime('now') "
            "FROM customer_consent_ledger WHERE user_id = ? "
            "ON CONFLICT(channel, user_id) DO UPDATE SET status = 'revoked', updated_at = excluded.updated_at",
            (user_id, user_id),
        )
        await self._db.execute(
            "UPDATE customer_consent_ledger SET status = 'revoked', updated_at = datetime('now') "
            "WHERE user_id = ?",
            (user_id,),
        )

    async def purge_expired(self, cutoffs: PrivacyRetentionCutoffs) -> dict[str, int]:
        """按已批准的保留期限清理可自动删除的数据。"""
        deleted: dict[str, int] = {}
        deleted["messages"] = await self._delete_with_cutoff(
            "messages", cutoffs.messages
        )
        deleted["profiles"] = await self._delete_with_cutoff(
            "customer_profiles", cutoffs.profiles
        )
        deleted["retrieval_logs"] = await self._delete_with_cutoff(
            "knowledge_retrieval_logs", cutoffs.retrieval_logs
        )
        deleted["address_audit"] = await self._delete_with_cutoff(
            "miniapp_address_audit", cutoffs.address_audit
        )
        deleted["orders"] = await self._purge_orders(cutoffs.orders)
        return deleted

    async def _purge_orders(self, cutoff: str) -> int:
        """清理超过保留期的终态订单：必须先清硬外键子表，再删订单本身。

        `payment_transactions.order_id` 与 `delivery_orders.order_id` 都声明了
        `REFERENCES orders(id)`，建库时 `PRAGMA foreign_keys = ON` 且两张表均为
        `on_delete=NO ACTION`。因此不能把 orders 当叶子表直接删：一旦命中已支付
        订单（必然带交易认领行），`DELETE FROM orders` 会抛外键错误；又因五张表
        的清理同处一个事务，异常会把前面已删的消息、画像、检索日志与地址审计
        一起回滚，使整个保留期作业永久失败且不删任何数据。

        过滤条件沿用原 `_delete_with_cutoff("orders", ...)` 口径：`done`/`cancelled`
        且 `updated_at` 早于截止时间。
        """
        await self._db.execute(
            "DELETE FROM payment_transactions WHERE order_id IN "
            "(SELECT id FROM orders WHERE updated_at < ? "
            "AND status IN ('done', 'cancelled'))",
            (cutoff,),
        )
        await self._db.execute(
            "DELETE FROM delivery_orders WHERE order_id IN "
            "(SELECT id FROM orders WHERE updated_at < ? "
            "AND status IN ('done', 'cancelled'))",
            (cutoff,),
        )
        cursor = await self._db.execute(
            "DELETE FROM orders WHERE updated_at < ? AND status IN ('done', 'cancelled')",
            (cutoff,),
        )
        return int(cursor.rowcount)

    async def _rows_for_user(self, sql: str, user_id: str) -> list[dict[str, Any]]:
        return await self._fetchall(sql, (user_id,))

    async def _rows_for_subject_or_ids(
        self,
        sql: str,
        user_id: str,
        customer_ids: list[str],
    ) -> list[dict[str, Any]]:
        if not customer_ids:
            return await self._fetchall(sql, (user_id, user_id))
        placeholders = ", ".join("?" for _ in customer_ids)
        return await self._fetchall(
            sql + " OR customer_id IN (" + placeholders + ")",
            (user_id, user_id, *customer_ids),
        )

    async def _customer_ids(self, user_id: str) -> list[str]:
        """解析主体关联的客户主档 ID 集合。

        身份链接的 `identity_value` 登记的是裸 openid，而前台下发的
        `user_id` 带 `wx_` 前缀。只按 `user_id` 原值匹配会让真实小程序
        用户恒定匹配不到任何链接，客户主档层整层漏删。
        """
        candidates = subject_identity_candidates(user_id)
        placeholders = ", ".join("?" for _ in candidates)
        rows = await self._fetchall(
            "SELECT DISTINCT customer_id FROM customer_identity_links "
            "WHERE identity_value IN ("
            + placeholders
            + ") OR identity_value_normalized IN ("
            + placeholders
            + ") OR source_record_id IN ("
            + placeholders
            + ")",
            candidates * 3,
        )
        return [str(row["customer_id"]) for row in rows if row["customer_id"]]

    async def _delete_customer_records(
        self, user_id: str, customer_ids: list[str]
    ) -> None:
        """清理客户主档层：先硬外键子表，再身份链接，最后主档本身。

        `customer_source_snapshots.identity_link_id` 与
        `customer_merge_reviews.primary_identity_link_id` 都声明了
        `REFERENCES customer_identity_links(id)`，建库时
        `PRAGMA foreign_keys = ON` 且两张表都是 on_delete=NO ACTION。
        因此不能把身份链接当叶子表先删：只要有快照或复核记录引用了待删
        链接，`DELETE FROM customer_identity_links` 就会抛
        FOREIGN KEY constraint failed，并因整笔主体删除同处一个事务而
        全部回滚——用户永久无法行使主体删除权。
        """
        candidates = subject_identity_candidates(user_id)
        link_placeholders = ", ".join("?" for _ in candidates)
        link_parameters = candidates * 3
        link_sql = (
            "DELETE FROM customer_identity_links WHERE identity_value IN ("
            + link_placeholders
            + ") OR identity_value_normalized IN ("
            + link_placeholders
            + ") OR source_record_id IN ("
            + link_placeholders
            + ")"
        )
        link_rows = await self._fetchall(
            "SELECT id FROM customer_identity_links WHERE identity_value IN ("
            + link_placeholders
            + ") OR identity_value_normalized IN ("
            + link_placeholders
            + ") OR source_record_id IN ("
            + link_placeholders
            + ")",
            link_parameters,
        )
        link_ids = [str(row["id"]) for row in link_rows]
        if link_ids:
            link_id_placeholders = ", ".join("?" for _ in link_ids)
            link_id_parameters = tuple(link_ids)
            await self._db.execute(
                "DELETE FROM customer_source_snapshots WHERE identity_link_id IN ("
                + link_id_placeholders
                + ")",
                link_id_parameters,
            )
            await self._db.execute(
                "DELETE FROM customer_merge_reviews WHERE primary_identity_link_id IN ("
                + link_id_placeholders
                + ")",
                link_id_parameters,
            )
        if customer_ids:
            placeholders = ", ".join("?" for _ in customer_ids)
            parameters = tuple(customer_ids)
            await self._db.execute(
                "DELETE FROM customer_source_snapshots WHERE customer_id IN ("
                + placeholders
                + ")",
                parameters,
            )
            await self._db.execute(
                "DELETE FROM customer_merge_reviews WHERE source_customer_id IN ("
                + placeholders
                + ") OR target_customer_id IN ("
                + placeholders
                + ")",
                parameters + parameters,
            )
        await self._db.execute(link_sql, link_parameters)
        for customer_id in customer_ids:
            remaining = await self._fetchall(
                "SELECT COUNT(*) AS count FROM customer_identity_links WHERE customer_id = ?",
                (customer_id,),
            )
            if int(remaining[0]["count"]) == 0:
                await self._db.execute(
                    "DELETE FROM customer_master WHERE id = ?", (customer_id,)
                )
            else:
                await self._db.execute(
                    "UPDATE customer_master SET primary_phone = '', display_name = '', "
                    "birthday = '', wechat_region = '', updated_at = datetime('now') "
                    "WHERE id = ?",
                    (customer_id,),
                )

    async def _rows_for_ids(
        self, sql_template: str, ids: list[str]
    ) -> list[dict[str, Any]]:
        if not ids:
            return []
        placeholders = ", ".join("?" for _ in ids)
        return await self._fetchall(sql_template.format(placeholders), tuple(ids))

    async def _fetchall(
        self, sql: str, parameters: tuple[object, ...] = ()
    ) -> list[dict[str, Any]]:
        rows = await self._db.execute_fetchall(sql, parameters)
        return [dict(row) if not isinstance(row, dict) else row for row in rows]

    async def _delete_with_cutoff(self, table_name: str, cutoff: str) -> int:
        statements = {
            "messages": "DELETE FROM messages WHERE created_at < ?",
            "customer_profiles": "DELETE FROM customer_profiles WHERE updated_at < ?",
            "knowledge_retrieval_logs": "DELETE FROM knowledge_retrieval_logs WHERE created_at < ?",
            "miniapp_address_audit": "DELETE FROM miniapp_address_audit WHERE created_at < ?",
            "orders": "DELETE FROM orders WHERE updated_at < ? AND status IN ('done', 'cancelled')",
        }
        sql = statements[table_name]
        cursor = await self._db.execute(sql, (cutoff,))
        return int(cursor.rowcount)
