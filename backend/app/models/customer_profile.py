"""顾客长期记忆数据模型。"""

from dataclasses import dataclass
from enum import Enum


class MemoryConsentStatus(str, Enum):
    """记忆留存同意状态。"""

    UNKNOWN = "unknown"
    GRANTED = "granted"
    REVOKED = "revoked"


@dataclass
class CustomerProfile:
    """一条顾客画像记录。"""

    id: str
    channel: str
    user_id: str
    display_name: str = ""
    preferences_json: str = "{}"
    order_summary_json: str = "{}"
    special_dates_json: str = "[]"
    allergens_json: str = "[]"
    consent_status: str = MemoryConsentStatus.UNKNOWN.value
    source_evidence_json: str = "{}"
    last_interaction_at: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CustomerProfileUpsert:
    """冷路径写入顾客画像所需参数。"""

    channel: str
    user_id: str
    display_name: str = ""
    preferences_json: str = "{}"
    order_summary_json: str = "{}"
    special_dates_json: str = "[]"
    allergens_json: str = "[]"
    consent_status: str = MemoryConsentStatus.UNKNOWN.value
    source_evidence_json: str = "{}"
    last_interaction_at: str = ""
