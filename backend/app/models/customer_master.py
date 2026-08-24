"""客户主档域数据模型。"""

from dataclasses import dataclass
from enum import Enum


class CustomerMasterStatus(str, Enum):
    """客户主档状态。"""

    ACTIVE = "active"
    MERGED = "merged"
    ARCHIVED = "archived"


class CustomerIdentityType(str, Enum):
    """客户身份类型。"""

    PHONE = "phone"
    YOUZAN_CUSTOMER = "youzan_customer"
    MINIAPP_OPENID = "miniapp_openid"
    WECOM_EXTERNAL_USER = "wecom_external_user"
    WECOM_UNION = "wecom_union"
    MANUAL = "manual"


class CustomerSourceSystem(str, Enum):
    """客户来源系统。"""

    YOUZAN = "youzan"
    MINIAPP = "miniapp"
    WECOM = "wecom"
    IMPORT = "import"
    MANUAL = "manual"


class CustomerIdentityConfidence(str, Enum):
    """客户身份可信度。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CustomerIdentityLinkStatus(str, Enum):
    """客户身份链接状态。"""

    ACTIVE = "active"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"
    MERGED = "merged"


class CustomerIdentityVerificationStatus(str, Enum):
    """客户身份验证状态。"""

    UNVERIFIED = "unverified"
    INFERRED = "inferred"
    VERIFIED = "verified"
    MANUAL_CONFIRMED = "manual_confirmed"


class CustomerSourceObjectType(str, Enum):
    """客户来源对象类型。"""

    CUSTOMER = "customer"
    ORDER_BUYER = "order_buyer"
    MEMBER = "member"
    CONTACT = "contact"


class CustomerMergeReviewType(str, Enum):
    """客户合并复核类型。"""

    IDENTITY_CONFLICT = "identity_conflict"
    CANDIDATE_MERGE = "candidate_merge"
    WEAK_IDENTITY_ENRICHMENT = "weak_identity_enrichment"


class CustomerMergeReviewStatus(str, Enum):
    """客户合并复核状态。"""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    APPROVED_MERGE = "approved_merge"
    REJECTED_MERGE = "rejected_merge"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class CustomerMergeReviewDecision(str, Enum):
    """客户合并复核决策。"""

    MERGE = "merge"
    KEEP_SEPARATE = "keep_separate"
    REJECT_IDENTITY = "reject_identity"
    WAIT = "wait"


@dataclass
class CustomerMaster:
    """一条逻辑客户主档。"""

    id: str
    tenant_id: str
    status: str = CustomerMasterStatus.ACTIVE.value
    merge_into_customer_id: str | None = None
    primary_phone: str = ""
    phone_verified: int = 0
    display_name: str = ""
    gender: str = "unknown"
    birthday: str = ""
    wechat_region: str = ""
    first_seen_at: str = ""
    last_seen_at: str = ""
    first_source: str = ""
    identity_confidence: str = CustomerIdentityConfidence.LOW.value
    has_youzan_identity: int = 0
    has_miniapp_identity: int = 0
    has_wecom_identity: int = 0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CustomerMasterCreate:
    """创建客户主档所需参数。"""

    tenant_id: str
    primary_phone: str = ""
    phone_verified: int = 0
    display_name: str = ""
    gender: str = "unknown"
    birthday: str = ""
    wechat_region: str = ""
    first_seen_at: str = ""
    last_seen_at: str = ""
    first_source: str = ""
    identity_confidence: str = CustomerIdentityConfidence.LOW.value
    has_youzan_identity: int = 0
    has_miniapp_identity: int = 0
    has_wecom_identity: int = 0


@dataclass
class CustomerIdentityLink:
    """一条客户身份链接。"""

    id: str
    tenant_id: str
    customer_id: str
    identity_type: str
    identity_value: str
    identity_value_normalized: str | None = None
    source_system: str = CustomerSourceSystem.MANUAL.value
    source_record_id: str = ""
    source_label: str = ""
    link_status: str = CustomerIdentityLinkStatus.ACTIVE.value
    verification_status: str = CustomerIdentityVerificationStatus.UNVERIFIED.value
    confidence_score: int = 0
    first_seen_at: str = ""
    last_seen_at: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CustomerIdentityLinkCreate:
    """创建客户身份链接所需参数。"""

    customer_id: str
    tenant_id: str
    identity_type: str
    identity_value: str
    identity_value_normalized: str | None = None
    source_system: str = CustomerSourceSystem.MANUAL.value
    source_record_id: str = ""
    source_label: str = ""
    link_status: str = CustomerIdentityLinkStatus.ACTIVE.value
    verification_status: str = CustomerIdentityVerificationStatus.UNVERIFIED.value
    confidence_score: int = 0
    first_seen_at: str = ""
    last_seen_at: str = ""


@dataclass
class CustomerSourceSnapshot:
    """一条客户来源快照。"""

    id: str
    tenant_id: str
    customer_id: str | None = None
    identity_link_id: str | None = None
    source_system: str = CustomerSourceSystem.MANUAL.value
    source_object_type: str = CustomerSourceObjectType.CUSTOMER.value
    source_record_id: str = ""
    source_batch_id: str = ""
    snapshot_json: str = "{}"
    normalized_json: str = "{}"
    field_hash: str = ""
    captured_at: str = ""
    created_at: str = ""


@dataclass
class CustomerSourceSnapshotCreate:
    """创建客户来源快照所需参数。"""

    tenant_id: str
    source_record_id: str
    source_batch_id: str
    snapshot_json: str
    normalized_json: str
    field_hash: str
    captured_at: str
    customer_id: str | None = None
    identity_link_id: str | None = None
    source_system: str = CustomerSourceSystem.MANUAL.value
    source_object_type: str = CustomerSourceObjectType.CUSTOMER.value


@dataclass
class CustomerMergeReview:
    """一条客户合并复核记录。"""

    id: str
    tenant_id: str
    review_type: str
    review_status: str = CustomerMergeReviewStatus.OPEN.value
    source_customer_id: str | None = None
    target_customer_id: str | None = None
    primary_identity_link_id: str | None = None
    review_reason: str = ""
    conflict_summary_json: str = "{}"
    evidence_snapshot_ids_json: str = "[]"
    decision: str = ""
    decision_notes: str = ""
    reviewed_by: str = ""
    reviewed_at: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CustomerMergeReviewCreate:
    """创建客户合并复核所需参数。"""

    tenant_id: str
    review_type: str
    review_reason: str
    conflict_summary_json: str
    evidence_snapshot_ids_json: str = "[]"
    source_customer_id: str | None = None
    target_customer_id: str | None = None
    primary_identity_link_id: str | None = None
    review_status: str = CustomerMergeReviewStatus.OPEN.value
    decision: str = ""
    decision_notes: str = ""
    reviewed_by: str = ""
    reviewed_at: str = ""
