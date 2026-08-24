"""客户主档域写入能力。"""

from abc import abstractmethod
from uuid import uuid4

from app.repository.base import DatabaseHandle
from app.models.customer_master import (
    CustomerIdentityLink,
    CustomerIdentityLinkCreate,
    CustomerMaster,
    CustomerMasterCreate,
    CustomerMergeReview,
    CustomerMergeReviewCreate,
    CustomerSourceSnapshot,
    CustomerSourceSnapshotCreate,
)
from app.utils import now_str


class CustomerMasterWriteMixin:
    """客户主档域写入集合。"""

    _db: DatabaseHandle

    @abstractmethod
    async def get_master(self, customer_id: str) -> CustomerMaster | None: ...

    @abstractmethod
    async def get_identity_link(self, link_id: str) -> CustomerIdentityLink | None: ...

    @abstractmethod
    async def get_source_snapshot(
        self, snapshot_id: str
    ) -> CustomerSourceSnapshot | None: ...

    @abstractmethod
    async def get_merge_review(self, review_id: str) -> CustomerMergeReview | None: ...

    async def create_master(self, payload: CustomerMasterCreate) -> CustomerMaster:
        """创建客户主档并返回最新结果。"""
        customer_id = str(uuid4())
        now = now_str()
        await self._db.execute(
            "INSERT INTO customer_master ("
            "id, tenant_id, status, merge_into_customer_id, primary_phone, phone_verified, "
            "display_name, gender, birthday, wechat_region, first_seen_at, last_seen_at, "
            "first_source, identity_confidence, has_youzan_identity, has_miniapp_identity, "
            "has_wecom_identity, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                customer_id,
                payload.tenant_id,
                "active",
                None,
                payload.primary_phone,
                payload.phone_verified,
                payload.display_name,
                payload.gender,
                payload.birthday,
                payload.wechat_region,
                payload.first_seen_at,
                payload.last_seen_at,
                payload.first_source,
                payload.identity_confidence,
                payload.has_youzan_identity,
                payload.has_miniapp_identity,
                payload.has_wecom_identity,
                now,
                now,
            ),
        )
        await self._db.commit()
        saved = await self.get_master(customer_id)
        if saved is None:
            raise RuntimeError("客户主档写入后未能读回")
        return saved

    async def create_identity_link(
        self,
        payload: CustomerIdentityLinkCreate,
    ) -> CustomerIdentityLink:
        """创建客户身份链接并返回最新结果。"""
        link_id = str(uuid4())
        now = now_str()
        await self._db.execute(
            "INSERT INTO customer_identity_links ("
            "id, tenant_id, customer_id, identity_type, identity_value, "
            "identity_value_normalized, source_system, source_record_id, source_label, "
            "link_status, verification_status, confidence_score, first_seen_at, "
            "last_seen_at, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                link_id,
                payload.tenant_id,
                payload.customer_id,
                payload.identity_type,
                payload.identity_value,
                payload.identity_value_normalized,
                payload.source_system,
                payload.source_record_id,
                payload.source_label,
                payload.link_status,
                payload.verification_status,
                payload.confidence_score,
                payload.first_seen_at,
                payload.last_seen_at,
                now,
                now,
            ),
        )
        await self._db.commit()
        saved = await self.get_identity_link(link_id)
        if saved is None:
            raise RuntimeError("客户身份链接写入后未能读回")
        return saved

    async def create_source_snapshot(
        self,
        payload: CustomerSourceSnapshotCreate,
    ) -> CustomerSourceSnapshot:
        """创建来源快照并返回最新结果。"""
        snapshot_id = str(uuid4())
        now = now_str()
        await self._db.execute(
            "INSERT INTO customer_source_snapshots ("
            "id, tenant_id, customer_id, identity_link_id, source_system, "
            "source_object_type, source_record_id, source_batch_id, snapshot_json, "
            "normalized_json, field_hash, captured_at, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id,
                payload.tenant_id,
                payload.customer_id,
                payload.identity_link_id,
                payload.source_system,
                payload.source_object_type,
                payload.source_record_id,
                payload.source_batch_id,
                payload.snapshot_json,
                payload.normalized_json,
                payload.field_hash,
                payload.captured_at,
                now,
            ),
        )
        await self._db.commit()
        saved = await self.get_source_snapshot(snapshot_id)
        if saved is None:
            raise RuntimeError("客户来源快照写入后未能读回")
        return saved

    async def create_merge_review(
        self,
        payload: CustomerMergeReviewCreate,
    ) -> CustomerMergeReview:
        """创建合并复核记录并返回最新结果。"""
        review_id = str(uuid4())
        now = now_str()
        await self._db.execute(
            "INSERT INTO customer_merge_reviews ("
            "id, tenant_id, review_type, review_status, source_customer_id, "
            "target_customer_id, primary_identity_link_id, review_reason, "
            "conflict_summary_json, evidence_snapshot_ids_json, decision, "
            "decision_notes, reviewed_by, reviewed_at, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                review_id,
                payload.tenant_id,
                payload.review_type,
                payload.review_status,
                payload.source_customer_id,
                payload.target_customer_id,
                payload.primary_identity_link_id,
                payload.review_reason,
                payload.conflict_summary_json,
                payload.evidence_snapshot_ids_json,
                payload.decision,
                payload.decision_notes,
                payload.reviewed_by,
                payload.reviewed_at,
                now,
                now,
            ),
        )
        await self._db.commit()
        saved = await self.get_merge_review(review_id)
        if saved is None:
            raise RuntimeError("客户合并复核写入后未能读回")
        return saved

    async def update_merge_review_evidence(
        self,
        *,
        review_id: str,
        evidence_snapshot_ids_json: str,
    ) -> CustomerMergeReview:
        """更新复核记录关联的证据快照列表。"""
        await self._db.execute(
            "UPDATE customer_merge_reviews SET evidence_snapshot_ids_json = ?, "
            "updated_at = ? WHERE id = ?",
            (
                evidence_snapshot_ids_json,
                now_str(),
                review_id,
            ),
        )
        await self._db.commit()
        saved = await self.get_merge_review(review_id)
        if saved is None:
            raise RuntimeError("客户合并复核更新后未能读回")
        return saved
