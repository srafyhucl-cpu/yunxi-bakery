"""客户主档领域服务。"""

from typing import Any

from app.models.customer_master import (
    CustomerIdentityLinkCreate,
    CustomerIdentityType,
    CustomerIdentityVerificationStatus,
    CustomerMasterCreate,
)
from app.repository.customer_master_repo import CustomerMasterRepo


class CustomerMasterService:
    """客户主档最小应用服务。"""

    def __init__(self, customer_master_repo: CustomerMasterRepo) -> None:
        self._customer_master_repo = customer_master_repo

    async def create_customer(
        self,
        payload: CustomerMasterCreate,
    ) -> dict[str, Any]:
        """创建客户主档并返回序列化结果。"""
        customer = await self._customer_master_repo.create_master(payload)
        return self._serialize_customer(customer)

    async def get_customer(self, customer_id: str) -> dict[str, Any]:
        """读取客户主档。"""
        customer = await self._customer_master_repo.get_master(customer_id)
        if customer is None:
            raise ValueError("客户不存在")
        return self._serialize_customer(customer)

    async def attach_identity(
        self,
        payload: CustomerIdentityLinkCreate,
    ) -> dict[str, Any]:
        """给客户主档挂一条身份链接。"""
        customer = await self._customer_master_repo.get_master(payload.customer_id)
        if customer is None:
            raise ValueError("客户不存在")
        identity = await self._customer_master_repo.create_identity_link(payload)
        return self._serialize_identity(identity)

    async def list_customer_identities(self, customer_id: str) -> list[dict[str, Any]]:
        """列出某客户的身份链接。"""
        customer = await self._customer_master_repo.get_master(customer_id)
        if customer is None:
            raise ValueError("客户不存在")
        items = await self._customer_master_repo.list_identity_links(customer_id)
        return [self._serialize_identity(item) for item in items]

    async def list_customer_snapshots(self, customer_id: str) -> list[dict[str, Any]]:
        """列出某客户的来源快照。"""
        customer = await self._customer_master_repo.get_master(customer_id)
        if customer is None:
            raise ValueError("客户不存在")
        items = await self._customer_master_repo.list_source_snapshots(
            customer_id=customer_id
        )
        return [self._serialize_snapshot(item) for item in items]

    async def list_batch_snapshots(self, source_batch_id: str) -> list[dict[str, Any]]:
        """按批次列出来源快照。"""
        items = await self._customer_master_repo.list_source_snapshots(
            source_batch_id=source_batch_id
        )
        return [self._serialize_snapshot(item) for item in items]

    async def list_merge_reviews(
        self,
        *,
        tenant_id: str = "",
        review_status: str = "",
    ) -> list[dict[str, Any]]:
        """列出客户合并复核队列。"""
        items = await self._customer_master_repo.list_merge_reviews(
            tenant_id=tenant_id,
            review_status=review_status,
        )
        return [self._serialize_merge_review(item) for item in items]

    async def find_customer_by_phone(
        self,
        tenant_id: str,
        phone: str,
    ) -> list[dict[str, Any]]:
        """按手机号查客户主档。"""
        if not phone.strip():
            return []
        items = await self._customer_master_repo.get_by_phone(tenant_id, phone)
        return [self._serialize_customer(item) for item in items]

    @staticmethod
    def build_phone_identity(
        *,
        customer_id: str,
        tenant_id: str,
        phone: str,
        source_system: str,
        source_record_id: str = "",
    ) -> CustomerIdentityLinkCreate:
        """生成手机号身份链接参数。"""
        return CustomerIdentityLinkCreate(
            customer_id=customer_id,
            tenant_id=tenant_id,
            identity_type=CustomerIdentityType.PHONE.value,
            identity_value=phone,
            identity_value_normalized=phone,
            source_system=source_system,
            source_record_id=source_record_id,
            confidence_score=100,
            verification_status="verified",
        )

    @staticmethod
    def build_miniapp_openid_identity(
        *,
        customer_id: str,
        tenant_id: str,
        openid: str,
        source_system: str,
    ) -> CustomerIdentityLinkCreate:
        """生成小程序 openid 身份链接参数。"""
        return CustomerIdentityLinkCreate(
            customer_id=customer_id,
            tenant_id=tenant_id,
            identity_type=CustomerIdentityType.MINIAPP_OPENID.value,
            identity_value=openid,
            identity_value_normalized=openid,
            source_system=source_system,
            verification_status=CustomerIdentityVerificationStatus.VERIFIED.value,
            confidence_score=100,
        )

    @staticmethod
    def _serialize_customer(customer) -> dict[str, Any]:
        return {
            "id": customer.id,
            "tenantId": customer.tenant_id,
            "status": customer.status,
            "mergeIntoCustomerId": customer.merge_into_customer_id,
            "primaryPhone": customer.primary_phone,
            "phoneVerified": bool(customer.phone_verified),
            "displayName": customer.display_name,
            "gender": customer.gender,
            "birthday": customer.birthday,
            "wechatRegion": customer.wechat_region,
            "firstSeenAt": customer.first_seen_at,
            "lastSeenAt": customer.last_seen_at,
            "firstSource": customer.first_source,
            "identityConfidence": customer.identity_confidence,
            "hasYouzanIdentity": bool(customer.has_youzan_identity),
            "hasMiniappIdentity": bool(customer.has_miniapp_identity),
            "hasWecomIdentity": bool(customer.has_wecom_identity),
            "createdAt": customer.created_at,
            "updatedAt": customer.updated_at,
        }

    @staticmethod
    def _serialize_identity(identity) -> dict[str, Any]:
        return {
            "id": identity.id,
            "tenantId": identity.tenant_id,
            "customerId": identity.customer_id,
            "identityType": identity.identity_type,
            "identityValue": identity.identity_value,
            "identityValueNormalized": identity.identity_value_normalized,
            "sourceSystem": identity.source_system,
            "sourceRecordId": identity.source_record_id,
            "sourceLabel": identity.source_label,
            "linkStatus": identity.link_status,
            "verificationStatus": identity.verification_status,
            "confidenceScore": identity.confidence_score,
            "firstSeenAt": identity.first_seen_at,
            "lastSeenAt": identity.last_seen_at,
            "createdAt": identity.created_at,
            "updatedAt": identity.updated_at,
        }

    @staticmethod
    def _serialize_snapshot(snapshot) -> dict[str, Any]:
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

    @staticmethod
    def _serialize_merge_review(review) -> dict[str, Any]:
        return {
            "id": review.id,
            "tenantId": review.tenant_id,
            "reviewType": review.review_type,
            "reviewStatus": review.review_status,
            "sourceCustomerId": review.source_customer_id,
            "targetCustomerId": review.target_customer_id,
            "primaryIdentityLinkId": review.primary_identity_link_id,
            "reviewReason": review.review_reason,
            "conflictSummaryJson": review.conflict_summary_json,
            "evidenceSnapshotIdsJson": review.evidence_snapshot_ids_json,
            "decision": review.decision,
            "decisionNotes": review.decision_notes,
            "reviewedBy": review.reviewed_by,
            "reviewedAt": review.reviewed_at,
            "createdAt": review.created_at,
            "updatedAt": review.updated_at,
        }
