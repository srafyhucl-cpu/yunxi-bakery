"""客户主档试导入编排服务。"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.customer_master import (
    CustomerIdentityLinkStatus,
    CustomerSourceObjectType,
)
from app.repository.customer_master_repo import CustomerMasterRepo
from app.service.customer.importer_support import CustomerImportSupportMixin
from app.service.customer.master import CustomerMasterService


@dataclass(frozen=True)
class CustomerImportPayload:
    """单条客户试导入记录。"""

    tenant_id: str
    source_record_id: str
    source_batch_id: str
    proposed_bucket: str
    confidence_level: str
    source_system: str
    source_channel: str
    source_method: str
    primary_phone: str = ""
    display_name: str = ""
    birthday: str = ""
    gender: str = "unknown"
    wechat_region: str = ""
    first_seen_at: str = ""
    last_seen_at: str = ""
    source_label: str = ""
    source_object_type: str = CustomerSourceObjectType.CUSTOMER.value
    conflict_flags: tuple[str, ...] = ()
    matched_order_phone: str = ""
    snapshot_payload: dict[str, object] | None = None
    normalized_payload: dict[str, object] | None = None


@dataclass(frozen=True)
class CustomerImportResult:
    """单条客户试导入结果。"""

    source_record_id: str
    customer_id: str
    identity_link_id: str | None
    snapshot_id: str
    merge_review_id: str | None
    resolved_bucket: str
    action: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "source_record_id": self.source_record_id,
            "customer_id": self.customer_id,
            "identity_link_id": self.identity_link_id,
            "snapshot_id": self.snapshot_id,
            "merge_review_id": self.merge_review_id,
            "resolved_bucket": self.resolved_bucket,
            "action": self.action,
        }


class CustomerImportService(CustomerImportSupportMixin):
    """客户主档试导入编排服务。"""

    @staticmethod
    def _build_import_result(
        *,
        source_record_id: str,
        customer_id: str,
        identity_link_id: str | None,
        snapshot_id: str,
        merge_review_id: str | None,
        resolved_bucket: str,
        action: str,
    ) -> CustomerImportResult:
        return CustomerImportResult(
            source_record_id=source_record_id,
            customer_id=customer_id,
            identity_link_id=identity_link_id,
            snapshot_id=snapshot_id,
            merge_review_id=merge_review_id,
            resolved_bucket=resolved_bucket,
            action=action,
        )

    def __init__(
        self,
        customer_master_repo: CustomerMasterRepo,
        customer_master_service: CustomerMasterService | None = None,
    ) -> None:
        self._customer_master_repo = customer_master_repo
        self._customer_master_service = (
            customer_master_service or CustomerMasterService(customer_master_repo)
        )

    async def import_record(
        self, payload: CustomerImportPayload
    ) -> CustomerImportResult:
        """按审计分流结果试导入一条客户记录。"""
        existing_snapshot = (
            await self._customer_master_repo.get_source_snapshot_by_source_key(
                tenant_id=payload.tenant_id,
                source_system=payload.source_system,
                source_object_type=payload.source_object_type,
                source_record_id=payload.source_record_id,
                source_batch_id=payload.source_batch_id,
            )
        )
        if existing_snapshot is not None:
            result: CustomerImportResult = await self._build_existing_snapshot_result(
                existing_snapshot
            )
            return result
        if payload.proposed_bucket == "pending_review":
            return await self._import_pending_review(payload)
        if payload.proposed_bucket == "new_master":
            return await self._import_new_master(payload)
        return await self._import_auto_merge(payload)

    async def _import_auto_merge(
        self,
        payload: CustomerImportPayload,
    ) -> CustomerImportResult:
        existing_customers = await self._customer_master_repo.get_by_phone(
            payload.tenant_id,
            payload.primary_phone,
        )
        if len(existing_customers) > 1:
            pending_payload = CustomerImportPayload(
                **{
                    **payload.__dict__,
                    "proposed_bucket": "pending_review",
                    "conflict_flags": payload.conflict_flags
                    + ("duplicate_phone_existing_master",),
                }
            )
            return await self._import_pending_review(pending_payload)

        source_identity = await self._get_source_identity(payload)
        if source_identity is not None:
            customer = await self._customer_master_repo.get_master(
                source_identity.customer_id
            )
            if customer is None:
                raise RuntimeError("来源身份存在但客户主档缺失")
            action = "reuse_source_identity"
        elif existing_customers:
            customer = existing_customers[0]
            action = "attach_existing_master"
        else:
            customer = await self._customer_master_repo.create_master(
                self._build_master_create(payload)
            )
            action = "create_master"
        source_identity_result = await self._ensure_source_identity(
            customer_id=customer.id,
            payload=payload,
            link_status=CustomerIdentityLinkStatus.ACTIVE.value,
        )
        identity = await self._ensure_phone_identity(
            customer_id=customer.id,
            payload=payload,
            link_status=CustomerIdentityLinkStatus.ACTIVE.value,
        )
        snapshot = await self._create_snapshot(
            payload,
            customer_id=customer.id,
            identity_link_id=(
                source_identity_result.id
                if source_identity_result is not None
                else (identity.id if identity else None)
            ),
        )
        return self._build_import_result(
            source_record_id=payload.source_record_id,
            customer_id=customer.id,
            identity_link_id=(
                source_identity_result.id
                if source_identity_result is not None
                else (identity.id if identity else None)
            ),
            snapshot_id=snapshot.id,
            merge_review_id=None,
            resolved_bucket="auto_merge",
            action=action,
        )

    async def _import_new_master(
        self,
        payload: CustomerImportPayload,
    ) -> CustomerImportResult:
        source_identity = await self._get_source_identity(payload)
        if source_identity is not None:
            customer = await self._customer_master_repo.get_master(
                source_identity.customer_id
            )
            if customer is None:
                raise RuntimeError("来源身份存在但客户主档缺失")
            action = "reuse_source_identity"
        else:
            customer = await self._customer_master_repo.create_master(
                self._build_master_create(payload)
            )
            action = "create_weak_master"
        source_identity_result = await self._ensure_source_identity(
            customer_id=customer.id,
            payload=payload,
            link_status=CustomerIdentityLinkStatus.ACTIVE.value,
        )
        identity = None
        if payload.primary_phone:
            identity = await self._ensure_phone_identity(
                customer_id=customer.id,
                payload=payload,
                link_status=CustomerIdentityLinkStatus.ACTIVE.value,
            )
        snapshot = await self._create_snapshot(
            payload,
            customer_id=customer.id,
            identity_link_id=(
                source_identity_result.id
                if source_identity_result is not None
                else (identity.id if identity else None)
            ),
        )
        return self._build_import_result(
            source_record_id=payload.source_record_id,
            customer_id=customer.id,
            identity_link_id=(
                source_identity_result.id
                if source_identity_result is not None
                else (identity.id if identity else None)
            ),
            snapshot_id=snapshot.id,
            merge_review_id=None,
            resolved_bucket="new_master",
            action=action,
        )

    async def _import_pending_review(
        self,
        payload: CustomerImportPayload,
    ) -> CustomerImportResult:
        source_identity = await self._get_source_identity(payload)
        if source_identity is not None:
            customer = await self._customer_master_repo.get_master(
                source_identity.customer_id
            )
            if customer is None:
                raise RuntimeError("来源身份存在但客户主档缺失")
            action = "reuse_review_customer"
        else:
            customer = await self._customer_master_repo.create_master(
                self._build_master_create(payload)
            )
            action = "create_review_queue"
        source_identity_result = await self._ensure_source_identity(
            customer_id=customer.id,
            payload=payload,
            link_status=CustomerIdentityLinkStatus.PENDING_REVIEW.value,
        )
        identity = None
        if payload.primary_phone:
            identity = await self._ensure_phone_identity(
                customer_id=customer.id,
                payload=payload,
                link_status=CustomerIdentityLinkStatus.PENDING_REVIEW.value,
            )
        snapshot = await self._create_snapshot(
            payload,
            customer_id=customer.id,
            identity_link_id=(
                source_identity_result.id
                if source_identity_result is not None
                else (identity.id if identity else None)
            ),
        )
        review = await self._ensure_pending_review(
            customer_id=customer.id,
            primary_identity_link_id=identity.id if identity else None,
            snapshot_id=snapshot.id,
            payload=payload,
        )
        return self._build_import_result(
            source_record_id=payload.source_record_id,
            customer_id=customer.id,
            identity_link_id=(
                source_identity_result.id
                if source_identity_result is not None
                else (identity.id if identity else None)
            ),
            snapshot_id=snapshot.id,
            merge_review_id=review.id,
            resolved_bucket="pending_review",
            action=action,
        )
