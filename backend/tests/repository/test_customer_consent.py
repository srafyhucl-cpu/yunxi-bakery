"""顾客 consent ledger 与撤回删除合同测试。"""

import pytest

from app.models.customer_profile import CustomerProfileUpsert
from app.repository.customer_profile_repo import CustomerProfileRepo
from app.service.customer_consent import CustomerConsentService


@pytest.mark.asyncio
async def test_revoke_keeps_ledger_and_deletes_profile(db) -> None:
    repo = CustomerProfileRepo(db)
    service = CustomerConsentService(repo)

    assert await service.get_status("miniapp", "user-1") == "unknown"
    assert await service.grant("miniapp", "user-1") == "granted"
    await repo.upsert(
        CustomerProfileUpsert(
            channel="miniapp",
            user_id="user-1",
            display_name="测试用户",
        )
    )
    assert await repo.get("miniapp", "user-1") is not None

    assert await service.revoke("miniapp", "user-1") == "revoked"
    assert await service.get_status("miniapp", "user-1") == "revoked"
    assert await repo.get("miniapp", "user-1") is None
