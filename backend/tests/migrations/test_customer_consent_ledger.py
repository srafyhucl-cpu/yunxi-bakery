"""顾客 consent ledger 迁移合同测试。"""

import pytest
import aiosqlite


@pytest.mark.asyncio
async def test_customer_consent_ledger_has_three_state_contract(db) -> None:
    columns = await db.execute_fetchall("PRAGMA table_info(customer_consent_ledger)")
    column_names = {row["name"] for row in columns}
    assert {"channel", "user_id", "status", "created_at", "updated_at"} <= column_names

    await db.execute(
        "INSERT INTO customer_consent_ledger (channel, user_id, status) VALUES (?, ?, ?)",
        ("miniapp", "migration-user", "granted"),
    )
    with pytest.raises(aiosqlite.IntegrityError):
        await db.execute(
            "INSERT INTO customer_consent_ledger (channel, user_id, status) "
            "VALUES (?, ?, ?)",
            ("miniapp", "migration-user-2", "invalid"),
        )
