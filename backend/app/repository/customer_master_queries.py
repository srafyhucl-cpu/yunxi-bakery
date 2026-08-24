"""客户主档域查询能力。"""

from app.repository.base import DatabaseHandle
from app.models.customer_master import (
    CustomerIdentityLink,
    CustomerMaster,
    CustomerMergeReview,
    CustomerSourceSnapshot,
)


class CustomerMasterQueryMixin:
    """客户主档域只读查询集合。"""

    _db: DatabaseHandle

    async def get_master(self, customer_id: str) -> CustomerMaster | None:
        """按主档 ID 读取客户主档。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, status, merge_into_customer_id, primary_phone, "
            "phone_verified, display_name, gender, birthday, wechat_region, "
            "first_seen_at, last_seen_at, first_source, identity_confidence, "
            "has_youzan_identity, has_miniapp_identity, has_wecom_identity, "
            "created_at, updated_at "
            "FROM customer_master WHERE id = ? LIMIT 1",
            (customer_id,),
        )
        return CustomerMaster(**dict(rows[0])) if rows else None

    async def get_by_phone(
        self,
        tenant_id: str,
        primary_phone: str,
    ) -> list[CustomerMaster]:
        """按租户和手机号读取客户主档列表。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, status, merge_into_customer_id, primary_phone, "
            "phone_verified, display_name, gender, birthday, wechat_region, "
            "first_seen_at, last_seen_at, first_source, identity_confidence, "
            "has_youzan_identity, has_miniapp_identity, has_wecom_identity, "
            "created_at, updated_at "
            "FROM customer_master WHERE tenant_id = ? AND primary_phone = ? "
            "ORDER BY created_at ASC",
            (tenant_id, primary_phone),
        )
        return [CustomerMaster(**dict(row)) for row in rows]

    async def list_masters_with_primary_phone(
        self,
        tenant_id: str,
    ) -> list[CustomerMaster]:
        """按租户列出所有有主手机号的客户主档。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, status, merge_into_customer_id, primary_phone, "
            "phone_verified, display_name, gender, birthday, wechat_region, "
            "first_seen_at, last_seen_at, first_source, identity_confidence, "
            "has_youzan_identity, has_miniapp_identity, has_wecom_identity, "
            "created_at, updated_at "
            "FROM customer_master WHERE tenant_id = ? AND primary_phone != '' "
            "ORDER BY created_at ASC",
            (tenant_id,),
        )
        return [CustomerMaster(**dict(row)) for row in rows]

    async def get_identity_link(self, link_id: str) -> CustomerIdentityLink | None:
        """按身份链接 ID 读取单条身份。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, customer_id, identity_type, identity_value, "
            "identity_value_normalized, source_system, source_record_id, source_label, "
            "link_status, verification_status, confidence_score, first_seen_at, "
            "last_seen_at, created_at, updated_at "
            "FROM customer_identity_links WHERE id = ? LIMIT 1",
            (link_id,),
        )
        return CustomerIdentityLink(**dict(rows[0])) if rows else None

    async def list_identity_links(self, customer_id: str) -> list[CustomerIdentityLink]:
        """按客户主档列出全部身份链接。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, customer_id, identity_type, identity_value, "
            "identity_value_normalized, source_system, source_record_id, source_label, "
            "link_status, verification_status, confidence_score, first_seen_at, "
            "last_seen_at, created_at, updated_at "
            "FROM customer_identity_links WHERE customer_id = ? "
            "ORDER BY created_at ASC",
            (customer_id,),
        )
        return [CustomerIdentityLink(**dict(row)) for row in rows]

    async def get_identity_by_value(
        self,
        tenant_id: str,
        identity_type: str,
        identity_value: str,
    ) -> CustomerIdentityLink | None:
        """按身份原值读取身份链接。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, customer_id, identity_type, identity_value, "
            "identity_value_normalized, source_system, source_record_id, source_label, "
            "link_status, verification_status, confidence_score, first_seen_at, "
            "last_seen_at, created_at, updated_at "
            "FROM customer_identity_links WHERE tenant_id = ? AND identity_type = ? "
            "AND identity_value = ? LIMIT 1",
            (tenant_id, identity_type, identity_value),
        )
        return CustomerIdentityLink(**dict(rows[0])) if rows else None

    async def get_identity_by_normalized_value(
        self,
        tenant_id: str,
        identity_type: str,
        identity_value_normalized: str,
    ) -> CustomerIdentityLink | None:
        """按标准化身份值读取身份链接。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, customer_id, identity_type, identity_value, "
            "identity_value_normalized, source_system, source_record_id, source_label, "
            "link_status, verification_status, confidence_score, first_seen_at, "
            "last_seen_at, created_at, updated_at "
            "FROM customer_identity_links WHERE tenant_id = ? AND identity_type = ? "
            "AND identity_value_normalized = ? LIMIT 1",
            (tenant_id, identity_type, identity_value_normalized),
        )
        return CustomerIdentityLink(**dict(rows[0])) if rows else None

    async def get_latest_identity_by_customer_and_type(
        self,
        customer_id: str,
        identity_type: str,
    ) -> CustomerIdentityLink | None:
        """按客户和身份类型读取最新一条身份链接。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, customer_id, identity_type, identity_value, "
            "identity_value_normalized, source_system, source_record_id, source_label, "
            "link_status, verification_status, confidence_score, first_seen_at, "
            "last_seen_at, created_at, updated_at "
            "FROM customer_identity_links WHERE customer_id = ? AND identity_type = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (customer_id, identity_type),
        )
        return CustomerIdentityLink(**dict(rows[0])) if rows else None

    async def get_source_snapshot(
        self,
        snapshot_id: str,
    ) -> CustomerSourceSnapshot | None:
        """按快照 ID 读取来源快照。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, customer_id, identity_link_id, source_system, "
            "source_object_type, source_record_id, source_batch_id, snapshot_json, "
            "normalized_json, field_hash, captured_at, created_at "
            "FROM customer_source_snapshots WHERE id = ? LIMIT 1",
            (snapshot_id,),
        )
        return CustomerSourceSnapshot(**dict(rows[0])) if rows else None

    async def get_source_snapshot_by_source_key(
        self,
        *,
        tenant_id: str,
        source_system: str,
        source_object_type: str,
        source_record_id: str,
        source_batch_id: str,
    ) -> CustomerSourceSnapshot | None:
        """按来源唯一键读取单条来源快照。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, customer_id, identity_link_id, source_system, "
            "source_object_type, source_record_id, source_batch_id, snapshot_json, "
            "normalized_json, field_hash, captured_at, created_at "
            "FROM customer_source_snapshots WHERE tenant_id = ? AND source_system = ? "
            "AND source_object_type = ? AND source_record_id = ? "
            "AND source_batch_id = ? LIMIT 1",
            (
                tenant_id,
                source_system,
                source_object_type,
                source_record_id,
                source_batch_id,
            ),
        )
        return CustomerSourceSnapshot(**dict(rows[0])) if rows else None

    async def list_source_snapshots(
        self,
        *,
        customer_id: str = "",
        source_batch_id: str = "",
    ) -> list[CustomerSourceSnapshot]:
        """按客户或批次列出来源快照。"""
        clauses = ["1 = 1"]
        params: list[object] = []
        if customer_id:
            clauses.append("customer_id = ?")
            params.append(customer_id)
        if source_batch_id:
            clauses.append("source_batch_id = ?")
            params.append(source_batch_id)
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, customer_id, identity_link_id, source_system, "
            "source_object_type, source_record_id, source_batch_id, snapshot_json, "
            "normalized_json, field_hash, captured_at, created_at "
            "FROM customer_source_snapshots WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at ASC",
            tuple(params),
        )
        return [CustomerSourceSnapshot(**dict(row)) for row in rows]

    async def get_merge_review(self, review_id: str) -> CustomerMergeReview | None:
        """按复核 ID 读取合并复核记录。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, review_type, review_status, source_customer_id, "
            "target_customer_id, primary_identity_link_id, review_reason, "
            "conflict_summary_json, evidence_snapshot_ids_json, decision, "
            "decision_notes, reviewed_by, reviewed_at, created_at, updated_at "
            "FROM customer_merge_reviews WHERE id = ? LIMIT 1",
            (review_id,),
        )
        return CustomerMergeReview(**dict(rows[0])) if rows else None

    async def list_merge_reviews(
        self,
        *,
        tenant_id: str = "",
        review_status: str = "",
    ) -> list[CustomerMergeReview]:
        """按租户或状态列出合并复核记录。"""
        clauses = ["1 = 1"]
        params: list[object] = []
        if tenant_id:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if review_status:
            clauses.append("review_status = ?")
            params.append(review_status)
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, review_type, review_status, source_customer_id, "
            "target_customer_id, primary_identity_link_id, review_reason, "
            "conflict_summary_json, evidence_snapshot_ids_json, decision, "
            "decision_notes, reviewed_by, reviewed_at, created_at, updated_at "
            "FROM customer_merge_reviews WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at ASC",
            tuple(params),
        )
        return [CustomerMergeReview(**dict(row)) for row in rows]

    async def get_latest_merge_review_for_customer(
        self,
        *,
        source_customer_id: str,
    ) -> CustomerMergeReview | None:
        """按来源客户读取最近一条复核记录。"""
        rows = await self._db.execute_fetchall(
            "SELECT id, tenant_id, review_type, review_status, source_customer_id, "
            "target_customer_id, primary_identity_link_id, review_reason, "
            "conflict_summary_json, evidence_snapshot_ids_json, decision, "
            "decision_notes, reviewed_by, reviewed_at, created_at, updated_at "
            "FROM customer_merge_reviews WHERE source_customer_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (source_customer_id,),
        )
        return CustomerMergeReview(**dict(rows[0])) if rows else None
