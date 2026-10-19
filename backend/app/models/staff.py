"""店员账号、会话主体与操作审计模型。"""

from dataclasses import dataclass
from enum import Enum


class StaffRole(str, Enum):
    """店员角色，当前仅区分收银员与店长。"""

    CASHIER = "cashier"
    MANAGER = "manager"


@dataclass
class StaffAccount:
    """一条店员账号记录（含 PIN 派生值，禁止外泄）。"""

    id: str
    tenant_id: str = "yunxi"
    name: str = ""
    phone: str = ""
    role: str = StaffRole.CASHIER.value
    pin_hash: str = ""
    pin_salt: str = ""
    is_active: int = 1
    last_login_at: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class StaffPrincipal:
    """已通过店员会话校验的最小身份主体。"""

    id: str
    name: str = ""
    phone: str = ""
    role: str = StaffRole.CASHIER.value
    tenant_id: str = "yunxi"


@dataclass
class StaffAuditLog:
    """一条店员操作审计记录。"""

    id: int = 0
    staff_id: str = ""
    action: str = ""
    target_type: str = ""
    target_id: str = ""
    detail_json: str = "{}"
    created_at: str = ""


__all__ = [
    "StaffAccount",
    "StaffAuditLog",
    "StaffPrincipal",
    "StaffRole",
]
