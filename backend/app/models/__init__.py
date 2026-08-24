"""
数据模型导出。

各渠道、各模块共用的数据结构和枚举。
不包含任何业务逻辑，仅定义数据的形状。
"""

from app.models.session import Session, SessionCreate, SessionStatus, Channel
from app.models.message import Message, MessageRole
from app.models.knowledge import KnowledgeEntry, KnowledgeCategory
from app.models.transfer import HumanTransfer, TransferStatus
from app.models.order import Order, OrderStatus
from app.models.customer_profile import (
    CustomerProfile,
    CustomerProfileUpsert,
    MemoryConsentStatus,
)
from app.models.customer_master import (
    CustomerIdentityConfidence,
    CustomerIdentityLink,
    CustomerIdentityLinkCreate,
    CustomerIdentityLinkStatus,
    CustomerIdentityType,
    CustomerIdentityVerificationStatus,
    CustomerMaster,
    CustomerMasterCreate,
    CustomerMasterStatus,
    CustomerMergeReview,
    CustomerMergeReviewCreate,
    CustomerMergeReviewDecision,
    CustomerMergeReviewStatus,
    CustomerMergeReviewType,
    CustomerSourceSystem,
    CustomerSourceObjectType,
    CustomerSourceSnapshot,
    CustomerSourceSnapshotCreate,
)
from app.models.conversation_review import ConversationReview, ConversationReviewCreate
from app.models.knowledge_gap import (
    KnowledgeGap,
    KnowledgeGapCreate,
    KnowledgeGapStatus,
)

__all__ = [
    "Session",
    "SessionCreate",
    "SessionStatus",
    "Channel",
    "Message",
    "MessageRole",
    "KnowledgeEntry",
    "KnowledgeCategory",
    "HumanTransfer",
    "TransferStatus",
    "Order",
    "OrderStatus",
    "CustomerProfile",
    "CustomerProfileUpsert",
    "MemoryConsentStatus",
    "CustomerMaster",
    "CustomerMasterCreate",
    "CustomerMasterStatus",
    "CustomerIdentityType",
    "CustomerSourceSystem",
    "CustomerSourceObjectType",
    "CustomerIdentityConfidence",
    "CustomerIdentityLink",
    "CustomerIdentityLinkCreate",
    "CustomerIdentityLinkStatus",
    "CustomerIdentityVerificationStatus",
    "CustomerSourceSnapshot",
    "CustomerSourceSnapshotCreate",
    "CustomerMergeReview",
    "CustomerMergeReviewCreate",
    "CustomerMergeReviewType",
    "CustomerMergeReviewStatus",
    "CustomerMergeReviewDecision",
    "ConversationReview",
    "ConversationReviewCreate",
    "KnowledgeGap",
    "KnowledgeGapCreate",
    "KnowledgeGapStatus",
]
