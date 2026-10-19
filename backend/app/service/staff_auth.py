"""店员账号认证、会话签发与审计服务。"""

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import JWTError, jwt

from app.config import settings
from app.models.staff import StaffAccount, StaffPrincipal, StaffRole
from app.repository.staff_repo import StaffAuditRepo, StaffRepo
from app.utils import now_str

STAFF_TENANT_ID = "yunxi"
STAFF_SESSION_ALGORITHM = "HS256"
PIN_HASH_ITERATIONS = 200_000
PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 8


def mask_phone(phone: str) -> str:
    """手机号脱敏，审计与日志只保留首尾便于人工核对。"""
    value = str(phone or "").strip()
    if len(value) < 7:
        return "***"
    return f"{value[:3]}****{value[-4:]}"


def _normalize_phone(phone: str) -> str:
    """校验并返回 11 位大陆手机号。"""
    value = str(phone or "").strip()
    if len(value) != 11 or not value.isdigit() or not value.startswith("1"):
        raise ValueError("请输入有效的11位手机号")
    return value


def _normalize_pin(pin: str) -> str:
    """校验并返回 4-8 位纯数字 PIN。"""
    value = str(pin or "").strip()
    if not value.isdigit() or not (PIN_MIN_LENGTH <= len(value) <= PIN_MAX_LENGTH):
        raise ValueError("PIN 必须为 4-8 位数字")
    return value


def hash_pin(pin: str, salt: str) -> str:
    """使用 PBKDF2-HMAC-SHA256 派生 PIN 校验值。"""
    return hashlib.pbkdf2_hmac(
        "sha256",
        str(pin).encode("utf-8"),
        str(salt).encode("utf-8"),
        PIN_HASH_ITERATIONS,
    ).hex()


class StaffAuthService:
    """店员登录、会话校验与账号管理。"""

    def __init__(
        self,
        staff_repo: StaffRepo,
        audit_repo: StaffRepo | StaffAuditRepo | None = None,
        tenant_id: str = STAFF_TENANT_ID,
    ) -> None:
        self._staff_repo = staff_repo
        # 审计仓储与账号仓储分离时显式注入；未注入时复用账号仓库。
        self._audit_repo = audit_repo or staff_repo
        self._tenant_id = tenant_id

    async def create_staff(
        self,
        name: str,
        phone: str,
        role: str,
        pin: str,
    ) -> StaffAccount:
        """创建店员账号，返回不含明文 PIN 的账号记录。"""
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("店员姓名不能为空")
        clean_phone = _normalize_phone(phone)
        clean_pin = _normalize_pin(pin)
        role_value = (
            role.value if isinstance(role, StaffRole) else str(role or "").strip()
        )
        try:
            clean_role = StaffRole(role_value).value
        except ValueError as exc:
            raise ValueError("店员角色无效") from exc

        salt = secrets.token_hex(16)
        now = now_str()
        account = StaffAccount(
            id=f"staff_{uuid4().hex}",
            tenant_id=self._tenant_id,
            name=clean_name,
            phone=clean_phone,
            role=clean_role,
            pin_hash=hash_pin(clean_pin, salt),
            pin_salt=salt,
            is_active=1,
            created_at=now,
            updated_at=now,
        )
        saved = await self._staff_repo.create_staff(account)
        await self._audit_repo.record_audit(
            saved.id,
            "create_staff",
            target_type="staff",
            target_id=saved.id,
            detail_json=json.dumps(
                {"phone": mask_phone(clean_phone), "role": clean_role},
                ensure_ascii=False,
            ),
        )
        return saved

    async def login(self, phone: str, pin: str) -> StaffPrincipal:
        """校验手机号 + PIN，成功后更新登录时间并写审计。"""
        clean_phone = _normalize_phone(phone)
        clean_pin = str(pin or "").strip()
        staff = await self._staff_repo.get_by_phone(self._tenant_id, clean_phone)
        if staff is None or not staff.is_active:
            raise ValueError("手机号或 PIN 不正确")
        expected_hash = hash_pin(clean_pin, staff.pin_salt)
        if not hmac.compare_digest(expected_hash, staff.pin_hash):
            raise ValueError("手机号或 PIN 不正确")

        logged_in_at = now_str()
        await self._staff_repo.update_last_login(staff.id, logged_in_at)
        await self._audit_repo.record_audit(
            staff.id,
            "login",
            target_type="staff",
            target_id=staff.id,
            detail_json=json.dumps(
                {"phone": mask_phone(clean_phone), "role": staff.role},
                ensure_ascii=False,
            ),
        )
        return StaffPrincipal(
            id=staff.id,
            name=staff.name,
            phone=staff.phone,
            role=staff.role,
            tenant_id=staff.tenant_id,
        )

    async def list_staff(self, active_only: bool = True) -> list[StaffAccount]:
        """列出当前租户店员账号。"""
        return await self._staff_repo.list_staff(self._tenant_id, active_only)

    async def disable_staff(self, phone: str) -> StaffAccount:
        """按手机号停用店员账号并写审计。"""
        staff = await self._require_staff_by_phone(phone)
        await self._staff_repo.set_active(staff.id, False)
        await self._audit_repo.record_audit(
            staff.id,
            "disable_staff",
            target_type="staff",
            target_id=staff.id,
            detail_json=json.dumps(
                {"phone": mask_phone(staff.phone)}, ensure_ascii=False
            ),
        )
        updated = await self._staff_repo.get_by_id(staff.id)
        if updated is None:
            raise RuntimeError("店员账号停用后未能读回")
        return updated

    async def reset_pin(self, phone: str, pin: str) -> StaffAccount:
        """重置店员 PIN 并写审计，绝不把 PIN 写入审计明细。"""
        clean_pin = _normalize_pin(pin)
        staff = await self._require_staff_by_phone(phone)
        salt = secrets.token_hex(16)
        await self._staff_repo.update_pin(staff.id, hash_pin(clean_pin, salt), salt)
        await self._audit_repo.record_audit(
            staff.id,
            "reset_pin",
            target_type="staff",
            target_id=staff.id,
            detail_json=json.dumps(
                {"phone": mask_phone(staff.phone)}, ensure_ascii=False
            ),
        )
        updated = await self._staff_repo.get_by_id(staff.id)
        if updated is None:
            raise RuntimeError("店员 PIN 重置后未能读回")
        return updated

    def issue_session_token(self, principal: StaffPrincipal) -> str:
        """使用独立店员密钥签发 8 小时班次会话。"""
        secret = settings.STAFF_SESSION_SECRET.strip()
        if not secret:
            raise ValueError("店员会话密钥未配置")
        now = datetime.now(timezone.utc)
        payload = {
            "sub": f"staff:{principal.id}",
            "name": principal.name,
            "role": principal.role,
            "tenant_id": principal.tenant_id,
            "iat": int(now.timestamp()),
            "exp": int(
                (
                    now + timedelta(seconds=settings.STAFF_SESSION_TTL_SECONDS)
                ).timestamp()
            ),
        }
        return jwt.encode(payload, secret, algorithm=STAFF_SESSION_ALGORITHM)

    async def verify_session_token(self, token: str) -> StaffPrincipal:
        """校验店员会话，并确认账号当前仍处于启用状态。"""
        secret = settings.STAFF_SESSION_SECRET.strip()
        if not secret:
            raise ValueError("店员会话密钥未配置")
        if not token:
            raise ValueError("未登录或登录已过期")
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[STAFF_SESSION_ALGORITHM],
            )
        except JWTError as exc:
            raise ValueError("店员会话无效或已过期") from exc
        subject = str(payload.get("sub", "")).strip()
        if not subject.startswith("staff:"):
            raise ValueError("店员会话无效或已过期")
        staff_id = subject.removeprefix("staff:").strip()
        if not staff_id:
            raise ValueError("店员会话无效或已过期")
        staff = await self._staff_repo.get_by_id(staff_id)
        if staff is None or not staff.is_active:
            raise ValueError("店员账号已停用，请重新登录")
        if staff.tenant_id != str(payload.get("tenant_id", staff.tenant_id)):
            raise ValueError("店员会话租户不匹配")
        return StaffPrincipal(
            id=staff.id,
            name=staff.name,
            phone=staff.phone,
            role=staff.role,
            tenant_id=staff.tenant_id,
        )

    async def _require_staff_by_phone(self, phone: str) -> StaffAccount:
        clean_phone = _normalize_phone(phone)
        staff = await self._staff_repo.get_by_phone(self._tenant_id, clean_phone)
        if staff is None:
            raise ValueError("未找到该店员")
        return staff


__all__ = [
    "StaffAuthService",
    "hash_pin",
    "mask_phone",
]
