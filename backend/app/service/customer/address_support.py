"""客户地址领域辅助函数。"""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.models.customer_address import CustomerAddress, CustomerAddressAuditEntry

MAINLAND_PHONE_PATTERN_PREFIXES = tuple(str(prefix) for prefix in range(13, 20))


def build_address(
    payload: dict[str, Any],
    user_id: str,
    *,
    should_default: bool,
) -> CustomerAddress:
    """根据输入载荷构建地址模型。"""
    address_id = str(payload.get("id") or f"addr_{uuid4().hex[:16]}")
    receiver_name = str(payload.get("receiverName", "")).strip()
    receiver_phone = str(payload.get("receiverPhone", "")).strip()
    address = str(payload.get("address", "")).strip()
    validate_address(receiver_name, receiver_phone, address)
    now = utc_now()
    return CustomerAddress(
        id=address_id,
        user_id=user_id,
        receiver_name=receiver_name,
        receiver_phone=receiver_phone,
        address=address,
        is_default=1 if bool(payload.get("isDefault")) or should_default else 0,
        created_at=str(payload.get("createdAt") or now),
        updated_at=now,
    )


def validate_address(receiver_name: str, receiver_phone: str, address: str) -> None:
    """校验地址簿字段。"""
    if not receiver_name:
        raise ValueError("请填写联系人")
    if (
        len(receiver_phone) != 11
        or not receiver_phone.isdigit()
        or receiver_phone[:2] not in MAINLAND_PHONE_PATTERN_PREFIXES
    ):
        raise ValueError("请填写正确的 11 位手机号")
    if not address:
        raise ValueError("请填写收货地址")


def serialize_address(
    item: CustomerAddress,
    *,
    include_user: bool = False,
) -> dict[str, Any]:
    """序列化地址输出。"""
    payload = {
        "id": item.id,
        "receiverName": item.receiver_name,
        "receiverPhone": item.receiver_phone,
        "address": item.address,
        "isDefault": bool(item.is_default),
        "createdAt": item.created_at,
        "updatedAt": item.updated_at,
    }
    if include_user:
        payload["userId"] = item.user_id
    return payload


def serialize_audit(entry: CustomerAddressAuditEntry) -> dict[str, Any]:
    """序列化地址审计日志。"""
    return {
        "id": entry.id,
        "addressId": entry.address_id,
        "userId": entry.user_id,
        "operator": entry.operator,
        "action": entry.action,
        "before": loads_dict(entry.before_json),
        "after": loads_dict(entry.after_json),
        "note": entry.note,
        "createdAt": entry.created_at,
    }


def loads_dict(raw: str) -> dict[str, Any]:
    """把 JSON 文本安全转换为字典。"""
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def dumps_dict(payload: dict[str, Any] | None) -> str:
    """把字典安全转换为 JSON 文本。"""
    return json.dumps(payload or {}, ensure_ascii=False)


def build_audit_entry(
    *,
    action: str,
    address_id: str,
    user_id: str,
    operator: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    note: str,
) -> CustomerAddressAuditEntry:
    """构建地址审计模型。"""
    return CustomerAddressAuditEntry(
        address_id=address_id,
        user_id=user_id,
        operator=operator or "admin",
        action=action,
        before_json=dumps_dict(before),
        after_json=dumps_dict(after),
        note=note,
        created_at=utc_now(),
    )


def utc_now() -> str:
    """返回 UTC ISO 时间。"""
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "build_audit_entry",
    "build_address",
    "dumps_dict",
    "serialize_address",
    "serialize_audit",
    "utc_now",
]
