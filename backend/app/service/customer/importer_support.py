"""客户试导入辅助能力。"""

from __future__ import annotations

import hashlib
import json
from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from app.repository.customer_master_repo import CustomerMasterRepo
from app.models.customer_master import (
    CustomerIdentityConfidence,
    CustomerIdentityLink,
    CustomerIdentityLinkCreate,
    CustomerIdentityType,
    CustomerIdentityVerificationStatus,
    CustomerMasterCreate,
    CustomerMergeReview,
    CustomerMergeReviewCreate,
    CustomerMergeReviewType,
    CustomerSourceSnapshot,
    CustomerSourceSnapshotCreate,
    CustomerSourceSystem,
)
from app.utils import now_str

if TYPE_CHECKING:
    from app.service.customer.importer import CustomerImportResult


class CustomerImportSupportMixin:
    """客户试导入共享辅助逻辑。"""

    _customer_master_repo: CustomerMasterRepo
    _customer_master_service: Any

    @abstractmethod
    def _build_import_result(
        self,
        *,
        source_record_id: str,
        customer_id: str,
        identity_link_id: str | None,
        snapshot_id: str,
        merge_review_id: str | None,
        resolved_bucket: str,
        action: str,
    ) -> CustomerImportResult: ...

    async def _ensure_pending_review(
        self,
        *,
        customer_id: str,
        primary_identity_link_id: str | None,
        snapshot_id: str,
        payload,
    ) -> CustomerMergeReview:
        existing_review = (
            await self._customer_master_repo.get_latest_merge_review_for_customer(
                source_customer_id=customer_id
            )
        )
        if existing_review is None:
            return await self._customer_master_repo.create_merge_review(
                CustomerMergeReviewCreate(
                    tenant_id=payload.tenant_id,
                    review_type=CustomerMergeReviewType.IDENTITY_CONFLICT.value,
                    source_customer_id=customer_id,
                    primary_identity_link_id=primary_identity_link_id,
                    review_reason="同手机号冲突或证据不足，进入人工复核",
                    conflict_summary_json=json.dumps(
                        {
                            "conflict_flags": list(payload.conflict_flags),
                            "matched_order_phone": payload.matched_order_phone,
                            "source_channel": payload.source_channel,
                            "source_method": payload.source_method,
                        },
                        ensure_ascii=False,
                    ),
                    evidence_snapshot_ids_json=json.dumps(
                        [snapshot_id],
                        ensure_ascii=False,
                    ),
                )
            )
        evidence_snapshot_ids = json.loads(
            existing_review.evidence_snapshot_ids_json or "[]"
        )
        if snapshot_id not in evidence_snapshot_ids:
            evidence_snapshot_ids.append(snapshot_id)
        return await self._customer_master_repo.update_merge_review_evidence(
            review_id=existing_review.id,
            evidence_snapshot_ids_json=json.dumps(
                evidence_snapshot_ids,
                ensure_ascii=False,
            ),
        )

    async def _ensure_phone_identity(
        self,
        *,
        customer_id: str,
        payload,
        link_status: str,
    ) -> CustomerIdentityLink | None:
        if not payload.primary_phone:
            return None
        existing = await self._customer_master_repo.get_identity_by_normalized_value(
            payload.tenant_id,
            CustomerIdentityType.PHONE.value,
            payload.primary_phone,
        )
        if existing is not None:
            return existing
        created = await self._customer_master_repo.create_identity_link(
            CustomerIdentityLinkCreate(
                customer_id=customer_id,
                tenant_id=payload.tenant_id,
                identity_type=CustomerIdentityType.PHONE.value,
                identity_value=payload.primary_phone,
                identity_value_normalized=payload.primary_phone,
                source_system=payload.source_system,
                source_record_id=payload.source_record_id,
                source_label=payload.source_label,
                link_status=link_status,
                verification_status=CustomerIdentityVerificationStatus.VERIFIED.value,
                confidence_score=100,
                first_seen_at=payload.first_seen_at,
                last_seen_at=payload.last_seen_at,
            )
        )
        return created

    async def _ensure_source_identity(
        self,
        *,
        customer_id: str,
        payload,
        link_status: str,
    ) -> CustomerIdentityLink:
        existing = await self._get_source_identity(payload)
        if existing is not None:
            return existing
        created = await self._customer_master_repo.create_identity_link(
            CustomerIdentityLinkCreate(
                customer_id=customer_id,
                tenant_id=payload.tenant_id,
                identity_type=CustomerIdentityType.YOUZAN_CUSTOMER.value,
                identity_value=payload.source_record_id,
                identity_value_normalized=payload.source_record_id,
                source_system=payload.source_system,
                source_record_id=payload.source_record_id,
                source_label=payload.source_label,
                link_status=link_status,
                verification_status=CustomerIdentityVerificationStatus.INFERRED.value,
                confidence_score=90,
                first_seen_at=payload.first_seen_at,
                last_seen_at=payload.last_seen_at,
            )
        )
        return created

    async def _get_source_identity(self, payload) -> CustomerIdentityLink | None:
        return await self._customer_master_repo.get_identity_by_value(
            payload.tenant_id,
            CustomerIdentityType.YOUZAN_CUSTOMER.value,
            payload.source_record_id,
        )

    async def _create_snapshot(
        self,
        payload,
        *,
        customer_id: str | None,
        identity_link_id: str | None,
    ) -> CustomerSourceSnapshot:
        snapshot_payload = payload.snapshot_payload or {}
        normalized_payload = payload.normalized_payload or {}
        snapshot = await self._customer_master_repo.create_source_snapshot(
            CustomerSourceSnapshotCreate(
                tenant_id=payload.tenant_id,
                customer_id=customer_id,
                identity_link_id=identity_link_id,
                source_system=payload.source_system,
                source_object_type=payload.source_object_type,
                source_record_id=payload.source_record_id,
                source_batch_id=payload.source_batch_id,
                snapshot_json=json.dumps(snapshot_payload, ensure_ascii=False),
                normalized_json=json.dumps(normalized_payload, ensure_ascii=False),
                field_hash=self._build_field_hash(snapshot_payload, normalized_payload),
                captured_at=now_str(),
            )
        )
        return snapshot

    def _build_master_create(self, payload) -> CustomerMasterCreate:
        return CustomerMasterCreate(
            tenant_id=payload.tenant_id,
            primary_phone=payload.primary_phone,
            phone_verified=1 if payload.primary_phone else 0,
            display_name=payload.display_name,
            gender=payload.gender or "unknown",
            birthday=payload.birthday,
            wechat_region=payload.wechat_region,
            first_seen_at=payload.first_seen_at,
            last_seen_at=payload.last_seen_at,
            first_source=payload.source_system,
            identity_confidence=self._map_confidence(payload.confidence_level),
            has_youzan_identity=1
            if payload.source_system == CustomerSourceSystem.YOUZAN.value
            else 0,
        )

    @staticmethod
    def _build_field_hash(
        snapshot_payload: dict[str, object],
        normalized_payload: dict[str, object],
    ) -> str:
        encoded = json.dumps(
            {
                "snapshot": snapshot_payload,
                "normalized": normalized_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _map_confidence(confidence_level: str) -> str:
        if confidence_level == "high":
            return CustomerIdentityConfidence.HIGH.value
        if confidence_level == "medium":
            return CustomerIdentityConfidence.MEDIUM.value
        return CustomerIdentityConfidence.LOW.value

    @staticmethod
    def _serialize_snapshot(snapshot) -> dict:
        return {
            "id": snapshot.id,
            "tenantId": snapshot.tenant_id,
            "customerId": snapshot.customer_id,
            "identityLinkId": snapshot.identity_link_id,
            "sourceSystem": snapshot.source_system,
            "sourceObjectType": snapshot.source_object_type,
            "sourceRecordId": snapshot.source_record_id,
            "sourceBatchId": snapshot.source_batch_id,
            "snapshotJson": snapshot.snapshot_json,
            "normalizedJson": snapshot.normalized_json,
            "fieldHash": snapshot.field_hash,
            "capturedAt": snapshot.captured_at,
            "createdAt": snapshot.created_at,
        }

    async def _build_existing_snapshot_result(
        self, snapshot: CustomerSourceSnapshot
    ) -> Any:
        normalized_payload = json.loads(snapshot.normalized_json or "{}")
        resolved_bucket = str(normalized_payload.get("proposed_bucket", "new_master"))
        merge_review_id = None
        if snapshot.customer_id:
            review = (
                await self._customer_master_repo.get_latest_merge_review_for_customer(
                    source_customer_id=snapshot.customer_id
                )
            )
            if review is not None and resolved_bucket == "pending_review":
                merge_review_id = review.id
        return self._build_import_result(
            source_record_id=snapshot.source_record_id,
            customer_id=snapshot.customer_id or "",
            identity_link_id=snapshot.identity_link_id,
            snapshot_id=snapshot.id,
            merge_review_id=merge_review_id,
            resolved_bucket=resolved_bucket,
            action="skip_existing_batch_row",
        )
