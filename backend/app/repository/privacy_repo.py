"""主体隐私数据的导出、删除和生命周期清理仓库。"""

from dataclasses import dataclass
from typing import Any

from app.repository.base import BaseRepository


@dataclass(frozen=True)
class PrivacyRetentionCutoffs:
    messages: str
    profiles: str
    retrieval_logs: str
    address_audit: str
    orders: str


class PrivacyRepo(BaseRepository):
    """集中维护主体数据覆盖范围，避免隐私流程散落在业务仓库。"""

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
        deleted["orders"] = await self._delete_with_cutoff("orders", cutoffs.orders)
        return deleted

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
        rows = await self._fetchall(
            "SELECT DISTINCT customer_id FROM customer_identity_links "
            "WHERE identity_value = ? OR identity_value_normalized = ? "
            "OR source_record_id = ?",
            (user_id, user_id, user_id),
        )
        return [str(row["customer_id"]) for row in rows if row["customer_id"]]

    async def _delete_customer_records(
        self, user_id: str, customer_ids: list[str]
    ) -> None:
        await self._db.execute(
            "DELETE FROM customer_identity_links WHERE identity_value = ? "
            "OR identity_value_normalized = ? OR source_record_id = ?",
            (user_id, user_id, user_id),
        )
        if not customer_ids:
            return
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
