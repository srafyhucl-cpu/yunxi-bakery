"""
数据访问层统一导出。

各模块通过 Repo 实例操作数据库，不直接拼接 SQL。
"""

from app.repository.session_repo import SessionRepo
from app.repository.message_repo import MessageRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.transfer_repo import TransferRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.customer_profile_repo import CustomerProfileRepo
from app.repository.conversation_review_repo import ConversationReviewRepo
from app.repository.knowledge_gap_repo import KnowledgeGapRepo
from app.repository.offline_session_repo import OfflineSessionRepo
from app.repository.privacy_repo import PrivacyRepo

__all__ = [
    "SessionRepo",
    "MessageRepo",
    "KnowledgeRepo",
    "TransferRepo",
    "CustomerMasterRepo",
    "CustomerProfileRepo",
    "ConversationReviewRepo",
    "KnowledgeGapRepo",
    "OfflineSessionRepo",
    "PrivacyRepo",
]
