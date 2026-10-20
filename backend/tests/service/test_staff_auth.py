"""店员认证服务测试。"""

import aiosqlite
import pytest

from app.config import settings
from app.repository.staff_repo import StaffAuditRepo, StaffRepo
from app.service.staff_auth import StaffAuthService, hash_pin


def _service(db: aiosqlite.Connection) -> StaffAuthService:
    return StaffAuthService(
        staff_repo=StaffRepo(db),
        audit_repo=StaffAuditRepo(db),
    )


@pytest.mark.asyncio
async def test_create_staff_hashes_pin_and_login_updates_state(
    db: aiosqlite.Connection,
) -> None:
    service = _service(db)

    account = await service.create_staff(
        name="小王",
        phone="13800000001",
        role="cashier",
        pin="2468",
    )

    assert account.pin_salt
    assert account.pin_hash != "2468"
    assert account.pin_hash == hash_pin("2468", account.pin_salt)
    assert len(account.pin_hash) == 64

    principal = await service.login("13800000001", "2468")

    assert principal.id == account.id
    assert principal.name == "小王"
    assert principal.role == "cashier"
    refreshed = await StaffRepo(db).get_by_id(account.id)
    assert refreshed is not None
    assert refreshed.last_login_at != ""

    logs = await StaffAuditRepo(db).list_audit(account.id)
    actions = [log.action for log in logs]
    assert "create_staff" in actions
    assert "login" in actions
    login_log = next(log for log in logs if log.action == "login")
    assert "13800000001" not in login_log.detail_json
    assert "138****0001" in login_log.detail_json


@pytest.mark.asyncio
async def test_login_rejects_wrong_pin_and_disabled_staff(
    db: aiosqlite.Connection,
) -> None:
    service = _service(db)
    await service.create_staff("小李", "13800000002", "manager", "1357")

    with pytest.raises(ValueError, match="手机号或 PIN 不正确"):
        await service.login("13800000002", "0000")
    with pytest.raises(ValueError, match="手机号或 PIN 不正确"):
        await service.login("13900000000", "1357")

    await service.disable_staff("13800000002")
    with pytest.raises(ValueError, match="手机号或 PIN 不正确"):
        await service.login("13800000002", "1357")


@pytest.mark.asyncio
async def test_create_staff_validates_phone_pin_and_role(
    db: aiosqlite.Connection,
) -> None:
    service = _service(db)

    with pytest.raises(ValueError, match="11位手机号"):
        await service.create_staff("错误手机", "1380000", "cashier", "1234")
    with pytest.raises(ValueError, match="4-8 位数字"):
        await service.create_staff("错误PIN", "13800000003", "cashier", "12")
    with pytest.raises(ValueError, match="角色无效"):
        await service.create_staff("错误角色", "13800000004", "owner", "1234")


@pytest.mark.asyncio
async def test_session_token_roundtrip_expiry_and_tamper(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(db)
    account = await service.create_staff("小张", "13800000005", "cashier", "1234")
    principal = await service.login("13800000005", "1234")

    token = service.issue_session_token(principal)
    verified = await service.verify_session_token(token)

    assert verified.id == account.id
    assert verified.phone == "13800000005"

    tampered = token[:-2] + "xx"
    with pytest.raises(ValueError, match="无效或已过期"):
        await service.verify_session_token(tampered)

    monkeypatch.setattr(settings, "STAFF_SESSION_TTL_SECONDS", -1)
    expired = service.issue_session_token(principal)
    with pytest.raises(ValueError, match="无效或已过期"):
        await service.verify_session_token(expired)


@pytest.mark.asyncio
async def test_session_token_rejects_disabled_staff(
    db: aiosqlite.Connection,
) -> None:
    service = _service(db)
    await service.create_staff("小赵", "13800000006", "cashier", "4321")
    principal = await service.login("13800000006", "4321")
    token = service.issue_session_token(principal)

    await service.disable_staff("13800000006")

    with pytest.raises(ValueError, match="账号已停用"):
        await service.verify_session_token(token)


@pytest.mark.asyncio
async def test_reset_pin_rotates_salt_and_fails_closed_without_secret(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(db)
    account = await service.create_staff("小陈", "13800000007", "cashier", "1111")

    reset = await service.reset_pin("13800000007", "2222")

    assert reset.pin_salt != account.pin_salt
    assert reset.pin_hash == hash_pin("2222", reset.pin_salt)
    with pytest.raises(ValueError, match="手机号或 PIN 不正确"):
        await service.login("13800000007", "1111")
    await service.login("13800000007", "2222")

    monkeypatch.setattr(settings, "STAFF_SESSION_SECRET", "")
    principal = await service.login("13800000007", "2222")
    with pytest.raises(ValueError, match="会话密钥未配置"):
        service.issue_session_token(principal)
    with pytest.raises(ValueError, match="会话密钥未配置"):
        await service.verify_session_token("any-token")
