"""店员账号仓储测试。"""

import aiosqlite
import pytest

from app.models.staff import StaffAccount
from app.repository.staff_repo import StaffAuditRepo, StaffRepo


def _staff(phone: str = "13800000001") -> StaffAccount:
    return StaffAccount(
        id="",
        tenant_id="yunxi",
        name="测试店员",
        phone=phone,
        role="cashier",
        pin_hash="hash-value",
        pin_salt="salt-value",
        is_active=1,
    )


@pytest.mark.asyncio
async def test_staff_repo_create_query_and_duplicate_phone(
    db: aiosqlite.Connection,
) -> None:
    repo = StaffRepo(db)

    created = await repo.create_staff(_staff())

    assert created.id.startswith("staff_")
    assert created.created_at
    assert created.updated_at
    by_phone = await repo.get_by_phone("yunxi", "13800000001")
    assert by_phone is not None
    assert by_phone.id == created.id
    by_id = await repo.get_by_id(created.id)
    assert by_id is not None
    assert by_id.role == "cashier"

    with pytest.raises(ValueError, match="手机号已存在"):
        await repo.create_staff(_staff())


@pytest.mark.asyncio
async def test_staff_repo_disable_and_list_active(
    db: aiosqlite.Connection,
) -> None:
    repo = StaffRepo(db)
    first = await repo.create_staff(_staff("13800000002"))
    await repo.create_staff(_staff("13800000003"))

    await repo.set_active(first.id, False)

    active = await repo.list_staff("yunxi", active_only=True)
    all_staff = await repo.list_staff("yunxi", active_only=False)
    assert [item.phone for item in active] == ["13800000003"]
    assert len(all_staff) == 2


@pytest.mark.asyncio
async def test_staff_repo_update_login_pin_and_audit(
    db: aiosqlite.Connection,
) -> None:
    repo = StaffRepo(db)
    audit_repo = StaffAuditRepo(db)
    created = await repo.create_staff(_staff("13800000004"))

    await repo.update_last_login(created.id, "2026-10-19 09:00:00")
    await repo.update_pin(created.id, "new-hash", "new-salt")
    await audit_repo.record_audit(
        created.id,
        "login",
        target_type="staff",
        target_id=created.id,
        detail_json='{"phone":"138****0004"}',
    )

    refreshed = await repo.get_by_id(created.id)
    assert refreshed is not None
    assert refreshed.last_login_at == "2026-10-19 09:00:00"
    assert refreshed.pin_hash == "new-hash"
    assert refreshed.pin_salt == "new-salt"

    logs = await audit_repo.list_audit(created.id)
    assert len(logs) == 1
    assert logs[0].action == "login"
    assert logs[0].target_type == "staff"
    assert "138****0004" in logs[0].detail_json
