"""店员账号与操作审计数据访问层。"""

from uuid import uuid4

import aiosqlite

from app.models.staff import StaffAccount, StaffAuditLog
from app.repository.base import BaseRepository, DatabaseHandle
from app.utils import now_str

# 显式字段列表，避免 SELECT * 把 PIN 派生字段扩散到非必要查询。
STAFF_COLUMNS = (
    "id, tenant_id, name, phone, role, pin_hash, pin_salt, "
    "is_active, last_login_at, created_at, updated_at"
)
AUDIT_COLUMNS = "id, staff_id, action, target_type, target_id, detail_json, created_at"


class StaffAuditMixin:
    """店员操作审计读写能力。"""

    _db: DatabaseHandle

    async def record_audit(
        self,
        staff_id: str,
        action: str,
        target_type: str = "",
        target_id: str = "",
        detail_json: str = "{}",
    ) -> None:
        """写入一条店员操作审计，不自行提交事务。"""
        await self._db.execute(
            "INSERT INTO staff_audit_logs (staff_id, action, target_type, "
            "target_id, detail_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                staff_id,
                action,
                target_type,
                target_id,
                detail_json or "{}",
                now_str(),
            ),
        )

    async def list_audit(
        self,
        staff_id: str,
        limit: int = 50,
    ) -> list[StaffAuditLog]:
        """按店员倒序读取最近审计记录。"""
        safe_limit = max(1, min(int(limit), 500))
        rows = await self._db.execute_fetchall(
            "SELECT " + AUDIT_COLUMNS + " FROM staff_audit_logs "
            "WHERE staff_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (staff_id, safe_limit),
        )
        return [StaffAuditLog(**dict(row)) for row in rows]


class StaffRepo(StaffAuditMixin, BaseRepository):
    """店员账号仓储，同时暴露审计写入能力供服务层统一调用。"""

    async def create_staff(self, staff: StaffAccount) -> StaffAccount:
        """创建店员账号，手机号在租户内唯一。"""
        staff_id = staff.id.strip() or f"staff_{uuid4().hex}"
        now = now_str()
        created_at = staff.created_at or now
        updated_at = staff.updated_at or now
        try:
            await self._db.execute(
                "INSERT INTO staff_accounts (id, tenant_id, name, phone, role, "
                "pin_hash, pin_salt, is_active, last_login_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    staff_id,
                    staff.tenant_id,
                    staff.name,
                    staff.phone,
                    staff.role,
                    staff.pin_hash,
                    staff.pin_salt,
                    staff.is_active,
                    staff.last_login_at,
                    created_at,
                    updated_at,
                ),
            )
        except aiosqlite.IntegrityError as exc:
            raise ValueError("该手机号已存在店员账号") from exc
        saved = await self.get_by_id(staff_id)
        if saved is None:
            raise RuntimeError("店员账号写入后未能读回")
        return saved

    async def get_by_phone(
        self,
        tenant_id: str,
        phone: str,
    ) -> StaffAccount | None:
        """按租户和手机号读取店员账号。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + STAFF_COLUMNS + " FROM staff_accounts "
            "WHERE tenant_id = ? AND phone = ? LIMIT 1",
            (tenant_id, phone),
        )
        return StaffAccount(**dict(rows[0])) if rows else None

    async def get_by_id(self, staff_id: str) -> StaffAccount | None:
        """按店员 ID 读取账号。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + STAFF_COLUMNS + " FROM staff_accounts WHERE id = ? LIMIT 1",
            (staff_id,),
        )
        return StaffAccount(**dict(rows[0])) if rows else None

    async def list_staff(
        self,
        tenant_id: str,
        active_only: bool = True,
    ) -> list[StaffAccount]:
        """按租户列出店员，默认只返回启用账号。"""
        sql = "SELECT " + STAFF_COLUMNS + " FROM staff_accounts WHERE tenant_id = ?"
        params: list[object] = [tenant_id]
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY created_at ASC, id ASC"
        rows = await self._db.execute_fetchall(sql, tuple(params))
        return [StaffAccount(**dict(row)) for row in rows]

    async def update_last_login(self, staff_id: str, at: str) -> None:
        """更新最近登录时间。"""
        await self._db.execute(
            "UPDATE staff_accounts SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (at, now_str(), staff_id),
        )

    async def set_active(self, staff_id: str, active: bool) -> None:
        """启用或停用店员账号。"""
        await self._db.execute(
            "UPDATE staff_accounts SET is_active = ?, updated_at = ? WHERE id = ?",
            (1 if active else 0, now_str(), staff_id),
        )

    async def update_pin(self, staff_id: str, pin_hash: str, pin_salt: str) -> None:
        """更新 PIN 派生值与盐。"""
        await self._db.execute(
            "UPDATE staff_accounts SET pin_hash = ?, pin_salt = ?, updated_at = ? "
            "WHERE id = ?",
            (pin_hash, pin_salt, now_str(), staff_id),
        )


class StaffAuditRepo(StaffAuditMixin, BaseRepository):
    """店员操作审计独立仓储，供服务装配时显式注入。"""
