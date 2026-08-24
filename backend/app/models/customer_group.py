"""客户群运营领域模型。"""

from dataclasses import dataclass


@dataclass
class CustomerGroup:
    """企业微信客户群绑定信息。"""

    id: str
    chat_id: str
    opengid: str = ""
    name: str = ""
    owner_userid: str = ""
    source: str = ""
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class GroupCampaign:
    """客户群团购或预订批次。"""

    id: str
    group_id: str
    title: str
    status: str = "active"
    starts_at: str = ""
    ends_at: str = ""
    summary_note: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class GroupRegistration:
    """客户提交的群团购登记。"""

    id: str
    campaign_id: str
    group_id: str
    user_id: str
    customer_name: str
    customer_phone: str
    product_name: str
    quantity: int
    fulfillment_method: str = "pickup"
    desired_time: str = ""
    address: str = ""
    remark: str = ""
    status: str = "pending"
    created_at: str = ""
    updated_at: str = ""


__all__ = ["CustomerGroup", "GroupCampaign", "GroupRegistration"]
