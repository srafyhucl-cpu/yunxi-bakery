"""客户群团购登记与汇总服务。"""

from collections import defaultdict
from typing import Any
from uuid import uuid4

from app.models.customer_group import CustomerGroup
from app.models.customer_group import GroupCampaign
from app.models.customer_group import GroupRegistration
from app.repository.customer_group_repo import CustomerGroupRepo
from app.utils import now_str

DEFAULT_GROUP_NAME = "未命名客户群"


class CustomerGroupOperationsService:
    """客户群运营一期应用服务。"""

    def __init__(self, repo: CustomerGroupRepo) -> None:
        self._repo = repo

    async def bind_group(self, payload: dict[str, Any]) -> dict[str, Any]:
        chat_id = _required_text(payload, "chatId", "请填写客户群 chat_id")
        now = now_str()
        existing = await self._repo.get_group_by_chat_id(chat_id)
        group_id = existing.id if existing else f"cg_{uuid4().hex}"
        group = CustomerGroup(
            id=group_id,
            chat_id=chat_id,
            opengid=str(payload.get("opengid", "")).strip(),
            name=str(payload.get("name", "")).strip() or DEFAULT_GROUP_NAME,
            owner_userid=str(payload.get("ownerUserid", "")).strip(),
            source=str(payload.get("source", "")).strip(),
            status="active",
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        await self._repo.upsert_group(group)
        return _serialize_group(group)

    async def list_groups(self, *, keyword: str = "") -> list[dict[str, Any]]:
        groups = await self._repo.list_groups(keyword=keyword.strip())
        return [_serialize_group(group) for group in groups]

    async def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        group_id = _required_text(payload, "groupId", "请填写客户群")
        group = await self._repo.get_group(group_id)
        if group is None:
            raise ValueError("客户群不存在")
        title = _required_text(payload, "title", "请填写活动标题")
        now = now_str()
        campaign = GroupCampaign(
            id=str(payload.get("id", "")).strip() or f"gcp_{uuid4().hex}",
            group_id=group_id,
            title=title,
            status="active",
            starts_at=str(payload.get("startsAt", "")).strip(),
            ends_at=str(payload.get("endsAt", "")).strip(),
            summary_note=str(payload.get("summaryNote", "")).strip(),
            created_at=now,
            updated_at=now,
        )
        await self._repo.insert_campaign(campaign)
        return _serialize_campaign(campaign)

    async def list_campaigns(
        self,
        *,
        group_id: str = "",
        status: str = "",
    ) -> list[dict[str, Any]]:
        campaigns = await self._repo.list_campaigns(
            group_id=group_id.strip(),
            status=status.strip(),
        )
        return [_serialize_campaign(campaign) for campaign in campaigns]

    async def submit_registration(
        self,
        payload: dict[str, Any],
        *,
        user_id: str,
    ) -> dict[str, Any]:
        campaign_id = _required_text(payload, "campaignId", "请填写活动批次")
        campaign = await self._repo.get_campaign(campaign_id)
        if campaign is None or campaign.status != "active":
            raise ValueError("活动批次不存在或已结束")
        customer_name = _required_text(payload, "customerName", "请填写联系人")
        customer_phone = _required_phone(payload)
        product_name = _required_text(payload, "productName", "请填写商品")
        quantity = _required_quantity(payload)
        fulfillment_method = str(payload.get("fulfillmentMethod", "pickup")).strip()
        if fulfillment_method not in ("pickup", "delivery"):
            raise ValueError("请选择正确的履约方式")
        if (
            fulfillment_method == "delivery"
            and not str(payload.get("address", "")).strip()
        ):
            raise ValueError("配送请填写地址")
        now = now_str()
        registration = GroupRegistration(
            id=str(payload.get("id", "")).strip() or f"gr_{uuid4().hex}",
            campaign_id=campaign.id,
            group_id=campaign.group_id,
            user_id=user_id.strip(),
            customer_name=customer_name,
            customer_phone=customer_phone,
            product_name=product_name,
            quantity=quantity,
            fulfillment_method=fulfillment_method,
            desired_time=str(payload.get("desiredTime", "")).strip(),
            address=str(payload.get("address", "")).strip(),
            remark=str(payload.get("remark", "")).strip(),
            status="pending",
            created_at=now,
            updated_at=now,
        )
        await self._repo.insert_registration(registration)
        return _serialize_registration(registration)

    async def update_registration_status(
        self,
        registration_id: str,
        status: str,
    ) -> dict[str, Any]:
        normalized_status = status.strip()
        if normalized_status not in ("pending", "confirmed", "cancelled"):
            raise ValueError("登记状态不支持")
        registration = await self._repo.update_registration_status(
            registration_id,
            normalized_status,
            now_str(),
        )
        if registration is None:
            raise ValueError("登记不存在")
        return _serialize_registration(registration)

    async def get_campaign_summary(self, campaign_id: str) -> dict[str, Any]:
        campaign = await self._repo.get_campaign(campaign_id)
        if campaign is None:
            raise ValueError("活动批次不存在")
        group = await self._repo.get_group(campaign.group_id)
        registrations = await self._repo.list_registrations(campaign_id=campaign_id)
        return _build_summary(campaign, group, registrations)

    async def list_my_registrations(self, *, user_id: str) -> list[dict[str, Any]]:
        registrations = await self._repo.list_registrations(user_id=user_id.strip())
        return [_serialize_registration(item) for item in registrations]


def _required_text(payload: dict[str, Any], key: str, message: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(message)
    return value


def _required_phone(payload: dict[str, Any]) -> str:
    phone = str(payload.get("customerPhone", "")).strip()
    if len(phone) != 11 or not phone.isdigit():
        raise ValueError("请填写正确的 11 位手机号")
    return phone


def _required_quantity(payload: dict[str, Any]) -> int:
    try:
        quantity = int(payload.get("quantity", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("请填写正确的数量") from exc
    if quantity <= 0:
        raise ValueError("请填写正确的数量")
    return quantity


def _serialize_group(group: CustomerGroup) -> dict[str, Any]:
    return {
        "id": group.id,
        "chatId": group.chat_id,
        "opengid": group.opengid,
        "name": group.name,
        "ownerUserid": group.owner_userid,
        "source": group.source,
        "status": group.status,
        "createdAt": group.created_at,
        "updatedAt": group.updated_at,
    }


def _serialize_campaign(campaign: GroupCampaign) -> dict[str, Any]:
    return {
        "id": campaign.id,
        "groupId": campaign.group_id,
        "title": campaign.title,
        "status": campaign.status,
        "startsAt": campaign.starts_at,
        "endsAt": campaign.ends_at,
        "summaryNote": campaign.summary_note,
        "createdAt": campaign.created_at,
        "updatedAt": campaign.updated_at,
    }


def _serialize_registration(item: GroupRegistration) -> dict[str, Any]:
    return {
        "id": item.id,
        "campaignId": item.campaign_id,
        "groupId": item.group_id,
        "userId": item.user_id,
        "customerName": item.customer_name,
        "customerPhone": item.customer_phone,
        "productName": item.product_name,
        "quantity": item.quantity,
        "fulfillmentMethod": item.fulfillment_method,
        "desiredTime": item.desired_time,
        "address": item.address,
        "remark": item.remark,
        "status": item.status,
        "createdAt": item.created_at,
        "updatedAt": item.updated_at,
    }


def _build_summary(
    campaign: GroupCampaign,
    group: CustomerGroup | None,
    registrations: list[GroupRegistration],
) -> dict[str, Any]:
    product_totals: dict[str, int] = defaultdict(int)
    status_counts: dict[str, int] = defaultdict(int)
    fulfillment_counts: dict[str, int] = defaultdict(int)
    pending_followups: list[dict[str, Any]] = []

    for item in registrations:
        product_totals[item.product_name] += item.quantity
        status_counts[item.status] += 1
        fulfillment_counts[item.fulfillment_method] += 1
        if item.status == "pending":
            pending_followups.append(_serialize_registration(item))

    product_rows = [
        {"productName": product_name, "quantity": quantity}
        for product_name, quantity in sorted(product_totals.items())
    ]
    summary_text = _build_summary_text(campaign.title, product_rows, pending_followups)
    return {
        "campaign": _serialize_campaign(campaign),
        "group": _serialize_group(group) if group else None,
        "totalRegistrations": len(registrations),
        "totalQuantity": sum(product_totals.values()),
        "statusCounts": dict(status_counts),
        "fulfillmentCounts": dict(fulfillment_counts),
        "productTotals": product_rows,
        "pendingFollowups": pending_followups,
        "registrations": [_serialize_registration(item) for item in registrations],
        "summaryText": summary_text,
    }


def _build_summary_text(
    title: str,
    product_rows: list[dict[str, Any]],
    pending_followups: list[dict[str, Any]],
) -> str:
    lines = [f"{title}登记汇总：", ""]
    if product_rows:
        for index, row in enumerate(product_rows, start=1):
            lines.append(f"{index}. {row['productName']}：{row['quantity']}份")
    else:
        lines.append("暂无登记")
    if pending_followups:
        lines.extend(["", "待确认："])
        for item in pending_followups[:10]:
            lines.append(
                f"- {item['customerName']}：{item['productName']} x {item['quantity']}"
            )
    lines.extend(["", "还没登记的朋友可以点小程序卡片填写。"])
    return "\n".join(lines)


__all__ = ["CustomerGroupOperationsService"]
